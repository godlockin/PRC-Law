#!/usr/bin/env python3
"""
md2template_docx.py — cn-pleading-templates 专用 Word 导出器

复用 scripts/md2docx.py 核心功能, 额外处理:
  1. [占位符] 自动高亮 (黄色背景, 律师一眼看到要填的字段)
  2. 自动插入 AI 标识头 + 律师审阅闸
  3. 模板文件: cn-pleading-templates/templates/*.md

用法:
  python3 scripts/md2template_docx.py <template.md> [-o output.docx]
  python3 scripts/md2template_docx.py templates/civil-defense.md -o 答辩状-张三案.docx
  python3 scripts/md2template_docx.py --fill 字段表.json -o filled.docx  # 自动填充

占位符格式: [字段名] (Markdown 模板里这样写)
填充格式: --fill 时传入 {"字段名": "实际值"}
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

# 复用现有 md2docx
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from md2docx import parse_and_convert
except ImportError as e:
    print(f"⚠ 导入 scripts/md2docx.py 失败: {e}", file=sys.stderr)
    print(f"   请确保 scripts/md2docx.py 存在", file=sys.stderr)
    sys.exit(2)

# === 占位符高亮 ===
# 匹配 [字段], 但排除:
#   1. 空内容 [] [ ]
#   2. Markdown 链接 [text](url) — 这种会被 [^\[\]]+? 排除
#   3. 核验清单里的 [ ] 复选框
PLACEHOLDER_RE = re.compile(r"\[(\S[^\[\]]*?)\]")


def highlight_placeholders(md_text: str) -> str:
    """占位符 [字段名] → ⟨字段名⟩

    使用角括号而非方括号, 避免与 Markdown 链接语法 [text](url) 冲突,
    也避免 md2docx 把 [XXX] 当成脚注/链接引用.
    """
    return PLACEHOLDER_RE.sub(
        lambda m: f"⟨{m.group(1)}⟩",
        md_text
    )


def fill_placeholders(md_text: str, values: dict) -> str:
    """替换 [占位符] 为实际值. 没找到的占位符保留为 ⟨XXX⟩ 形式提醒律师."""
    def _replace(m):
        key = m.group(1).strip()
        if key in values:
            return str(values[key])
        # 保留提醒
        return f"⟨{key}⟩"
    return PLACEHOLDER_RE.sub(_replace, md_text)


# === LLM 自动抽取字段 (W7.4) ===
def extract_fields_from_text(
    case_text: str,
    template_placeholders: list[str],
    llm_base_url: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
) -> dict:
    """从案件文本自动抽取模板字段值

    Args:
        case_text: 案件原文 (起诉状/答辩状/事实摘要)
        template_placeholders: 模板占位符列表 (从模板解析)
        llm_base_url/api_key/model: LLM 配置 (默认读环境变量 PRC_LAW_LLM_*)

    Returns:
        {字段名: 字段值} 字典
    """
    import os
    import json as _json
    import re as _re
    import urllib.request

    base_url = llm_base_url or os.environ.get("PRC_LAW_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = llm_api_key or os.environ.get("PRC_LAW_LLM_API_KEY", "")
    model = llm_model or os.environ.get("PRC_LAW_LLM_MODEL", "qwen-max")

    if not api_key:
        print("⚠ 未配置 LLM API key, 无法自动填充. "
              "请设置环境变量 PRC_LAW_LLM_API_KEY", file=sys.stderr)
        return {}

    # SSRF 防护: 校验 base_url
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    allowed_hosts = {
        "dashscope.aliyuncs.com", "open.bigmodel.cn",
        "api.deepseek.com", "api.moonshot.cn",
        "api.spark.xfyun.cn", "api.baichuan-ai.com",
        "api.stepfun.com", "aip.baidubce.com",
        "api.anthropic.com", "api.openai.com",
    }
    if parsed.hostname not in allowed_hosts:
        print(f"❌ LLM 端点不在白名单: {parsed.hostname}", file=sys.stderr)
        return {}

    # 构造 prompt
    prompt = f"""从以下案件文本中, 抽取每个占位符字段对应的值.
如果文本中找不到该字段, 返回 null.

占位符:
{_json.dumps(template_placeholders, ensure_ascii=False)}

案件文本:
---
{case_text[:3000]}
---

输出 JSON 格式, 严格按占位符列表顺序:
```json
{{"字段1": "值1", "字段2": null, ...}}
```
"""

    req_body = _json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "你是法律文书抽取助手. 严格输出 JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=req_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        no_redirect = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler
        )
        with no_redirect.open(req, timeout=30) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"⚠ LLM 调用失败: {e}", file=sys.stderr)
        return {}

    # 解析 JSON (可能被 ```json 包裹)
    json_match = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, _re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = content.strip()

    try:
        return _json.loads(json_str)
    except _json.JSONDecodeError:
        print(f"⚠ LLM 输出非 JSON: {content[:200]}", file=sys.stderr)
        return {}


def extract_placeholders_from_template(md_text: str) -> list[str]:
    """从模板 Markdown 提取所有占位符名 (去重)"""
    return list(dict.fromkeys(
        m.group(1).strip()
        for m in PLACEHOLDER_RE.finditer(md_text)
    ))


def highlight_docx_placeholders(doc) -> int:
    """给 docx 中所有 ⟨字段名⟩ run 加黄色背景高亮

    在 parse_and_convert 生成 doc 之后调用.
    返回高亮的 run 数.
    """
    count = 0
    # WD_COLOR_INDEX 在 docx.enum.text, 这里手动用 7 (YELLOW)
    YELLOW = 7

    def _process_paragraph(para):
        nonlocal count
        # 把段落里所有 run 的 text 拼接, 找出 ⟨...⟩ 区间
        full = "".join(r.text for r in para.runs)
        if "⟨" not in full:
            return
        # 简单策略: 逐 run 检查是否包含 ⟨ 或 ⟩
        # 找到 start run / end run, 给中间所有 run 上黄
        in_placeholder = False
        for run in para.runs:
            text = run.text
            if "⟨" in text and "⟩" in text and text.find("⟨") < text.find("⟩"):
                # 完整占位符在一个 run 里
                run.font.highlight_color = YELLOW
                count += 1
                continue
            if "⟨" in text:
                in_placeholder = True
                run.font.highlight_color = YELLOW
                count += 1
                if "⟩" in text:
                    in_placeholder = False
                continue
            if "⟩" in text:
                in_placeholder = False
                run.font.highlight_color = YELLOW
                count += 1
                continue
            if in_placeholder:
                run.font.highlight_color = YELLOW
                count += 1

    for para in doc.paragraphs:
        _process_paragraph(para)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _process_paragraph(para)
    return count


# === AI 标识头 ===
AI_DISCLAIMER = """
> ⚠️ **AI 辅助生成 — 律师审阅后使用** (上海律协指引 2025-08 §13)
> 本文书由 PRC-Law (大模型 + skills 自动加载) 起草, **仅供律师参考**.
> 律师提交前必须完成以下核验:
> - [ ] 全部法条引用现行有效 (cn-norm-verify)
> - [ ] 当事人信息完整准确
> - [ ] 诉讼请求具体明确
> - [ ] 事实时间线完整
> - [ ] 管辖正确
> - [ ] 诉讼时效未过期
> - [ ] 律师复核签名
>
> 引用: PRC-Law v9.0.0 · https://github.com/godlockin/PRC-Law

---

"""


def inject_disclaimer(md_text: str) -> str:
    """在 frontmatter 之后插入 AI 标识头"""
    if "AI 辅助生成" in md_text:
        return md_text  # 已注入
    lines = md_text.split("\n")
    insert_idx = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                insert_idx = i + 1
                break
    return "\n".join(lines[:insert_idx]) + "\n\n" + AI_DISCLAIMER + "\n".join(lines[insert_idx:])


# === 主入口 ===
def main():
    parser = argparse.ArgumentParser(
        description="cn-pleading-templates 专用 Word 导出器")
    parser.add_argument("template", help="模板 .md 文件路径")
    parser.add_argument("-o", "--output", default=None,
                        help="输出 .docx 路径 (默认: 同目录同名.docx)")
    parser.add_argument("--fill", help="JSON 字段表, 自动填充占位符")
    parser.add_argument("--auto-fill", help="案件文本文件路径, LLM 自动抽取字段")
    parser.add_argument("--no-disclaimer", action="store_true",
                        help="不插入 AI 标识头 (默认插入)")
    args = parser.parse_args()

    src = Path(args.template)
    if not src.exists():
        print(f"❌ 模板不存在: {src}", file=sys.stderr)
        sys.exit(1)

    md_text = src.read_text(encoding="utf-8")

    # 1. 填充占位符 (可选)
    if args.fill:
        fill_path = Path(args.fill)
        if not fill_path.exists():
            print(f"❌ 字段表不存在: {fill_path}", file=sys.stderr)
            sys.exit(1)
        try:
            values = json.loads(fill_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
            sys.exit(1)
        md_text = fill_placeholders(md_text, values)
        print(f"✓ 已填充 {len(values)} 个字段 (手动 JSON)")
    elif args.auto_fill:
        # W7.4 LLM 自动抽取字段
        case_path = Path(args.auto_fill)
        if not case_path.exists():
            print(f"❌ 案件文本不存在: {case_path}", file=sys.stderr)
            sys.exit(1)
        case_text = case_path.read_text(encoding="utf-8")
        placeholders = extract_placeholders_from_template(md_text)
        if not placeholders:
            print("⚠ 模板无占位符, 无需 LLM 抽取", file=sys.stderr)
        else:
            print(f"⏳ LLM 抽取 {len(placeholders)} 个字段...", file=sys.stderr)
            values = extract_fields_from_text(
                case_text, placeholders)
            if not values:
                print("❌ LLM 抽取失败, 回退到高亮模式", file=sys.stderr)
                md_text = highlight_placeholders(md_text)
            else:
                # 仅填充非 null 字段
                filled = {k: v for k, v in values.items() if v}
                md_text = fill_placeholders(md_text, filled)
                null_count = len(placeholders) - len(filled)
                print(f"✓ 已抽取 {len(filled)} 字段, {null_count} 未找到", file=sys.stderr)
                if null_count:
                    print(f"   未填充字段: {[k for k,v in values.items() if not v]}",
                          file=sys.stderr)
    else:
        # 2. 高亮占位符 (律师填字段前使用)
        md_text = highlight_placeholders(md_text)

    # 3. 插入 AI 标识头
    if not args.no_disclaimer:
        md_text = inject_disclaimer(md_text)

    # 4. 输出路径
    out = Path(args.output) if args.output else src.with_suffix(".docx")

    # 5. 复用 md2docx 生成 Word
    print(f"📄 生成: {out}")
    try:
        # 提取标题
        title = None
        for line in md_text.split("\n"):
            m = re.match(r"^#\s+(.+)$", line.strip())
            if m:
                title = m.group(1)
                break
        doc = parse_and_convert(md_text, title or "律鉴法律文书")
        # 6. 高亮 ⟨占位符⟩
        if not args.fill:
            n = highlight_docx_placeholders(doc)
            if n:
                print(f"🎨 已高亮 {n} 处占位符 (黄色背景)")
        doc.save(str(out))
        print(f"✅ 完成: {out}")
        # 提醒律师
        if not args.fill:
            print()
            print("⚠️  提示: 模板里有 ⟨字段名⟩ 待填 (黄色高亮)")
            print("   1) 直接在 Word 里手动替换, 或")
            print("   2) 用 --fill fields.json 自动填充")
    except Exception as e:
        print(f"❌ 生成失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()