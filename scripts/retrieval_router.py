#!/usr/bin/env python3
"""
retrieval_router.py — 统一检索路由器

封装 6 级 fallback 链, 输出标准化 source-label 标注:

    1. 元典/法宝 MCP          (商业权威, 消耗 credit)
    2. prc-law-data 数据集    (本地/HTTP 离线, 零 credit)  [v8.3.0+]
    3. 本地 cache             (statutes.json, 离线可用)
    4. 爬虫结果                (references/laws/*.md)
    5. 政府公开源              (spp.gov.cn / gov.cn/zhengce/) [v8.3.0+]
    6. source-label           (返回 None, 让上层标 [待检索])

用法:
    python3 scripts/retrieval_router.py --law 民法典 --article 577
    python3 scripts/retrieval_router.py --law 民法典 --keyword 违约责任
    python3 scripts/retrieval_router.py --json        # JSON 输出
    python3 scripts/retrieval_router.py --explain     # 显示每级 fallback 决策

返回结构:
    {
      "found": True,
      "source_chain": ["yuandian", "prc_law_data", ...],
      "selected_level": 2,
      "label": "[已确认: prc-law-data 离线数据集 YYYY-MM-DD]",
      "content": "...",
      "metadata": {...}
    }
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = ROOT / "references" / ".cache" / "statutes.json"
LAW_DIR = ROOT / "references" / "laws"

# --- 标签映射 (与 cn-source-label 体系对齐) ---
LABEL_BY_LEVEL = {
    1: "[已确认: 元典+北大法宝 {date}]",         # MCP 多源 (商业)
    2: "[已确认: prc-law-data 离线数据集 {date}]", # 本地/HTTP 数据集 (零 credit)
    3: "[本地缓存 {date}—需运行时核验]",           # 本地 cache
    4: "[已确认: 国家法律法规数据库 {date}]",     # flk.npc.gov.cn 爬虫
    5: "[已确认: 最高人民检察院/国务院 {date}]",   # 政府公开源
    6: "[待检索—所有源均不可用]",
}


def _now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def try_yuandian_pkulaw(law: str, article: Optional[str], keyword: Optional[str]) -> dict | None:
    """
    L1: 元典/法宝 MCP
    调用方式:
    - 调 yuandian_mcp_bridge.py (stdio) 或 HTTP(SSE)
    - 调用 pkulaw MCP
    这里留好签名, 实际接入需 .mcp.json 配置
    """
    # 检查 MCP 可用性
    mcp_json = ROOT / ".mcp.json"
    if not mcp_json.exists():
        return None
    try:
        config = json.loads(mcp_json.read_text())
    except Exception:
        return None
    yuandian_cfg = config.get("mcpServers", {}).get("yuandian") or config.get("yuandian")
    pkulaw_cfg = config.get("mcpServers", {}).get("pkulaw") or config.get("pkulaw")
    # API key 缺失 → 跳过 L1
    yuandian_key = os.environ.get("YUANDIAN_API_KEY", "")
    if not yuandian_key and not yuandian_cfg:
        return None
    # 实际调 MCP — 这里需要 stdio 调用或 HTTP, 简化: 留 marker
    # 真接入参考 yuandian_mcp_bridge.py
    try:
        # 尝试调本地 bridge
        bridge = ROOT / "scripts" / "yuandian_mcp_bridge.py"
        if bridge.exists() and yuandian_key:
            import subprocess
            payload = json.dumps({
                "method": "law.search",
                "params": {"law": law, "article": article, "keyword": keyword},
            }, ensure_ascii=False)
            r = subprocess.run(
                ["python3", str(bridge)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                try:
                    parsed = json.loads(r.stdout)
                    # JSON-RPC error 协议: {"jsonrpc":"2.0","id":N,"error":{...}}
                    # 这种不算 L1 命中, 应该让 fallback 链继续
                    if isinstance(parsed, dict) and "error" in parsed:
                        return None
                    # 业务层 result=null 也算 miss
                    if isinstance(parsed, dict) and parsed.get("result") is None:
                        return None
                    return parsed
                except json.JSONDecodeError:
                    return None
    except Exception:
        pass
    return None


def try_prc_law_data(law: str, article: Optional[str], keyword: Optional[str]) -> dict | None:
    """L2: prc-law-data 数据集 (vendor submodule / 环境变量路径 / HTTP API)

    优先于本地 cache (因为数据更全 + 法条结构化 + 零 credit).
    """
    try:
        # 延迟 import, 避免 dataset_client 不可用时整个模块挂掉
        from dataset_client import DatasetClient
    except ImportError:
        return None
    client = DatasetClient()
    if not client.is_available():
        return None
    hit = client.lookup(law, article, keyword)
    if not hit:
        return None
    return {
        "content": hit.content,
        "law": hit.law,
        "article": hit.article,
        "source": "prc_law_data",
        "source_detail": hit.source_detail,
        "fetched_at": hit.fetched_at,
        "article_count": hit.article_count,
        "client_mode": client.mode,
    }


def try_local_cache(law: str, article: Optional[str], keyword: Optional[str]) -> dict | None:
    """L2: 本地 cache (references/.cache/statutes.json)
    Schema: root 是 dict{name: {expected_articles, articles, status, pulled_at}}
    """
    if not CACHE_FILE.exists():
        return None
    try:
        cache = json.loads(CACHE_FILE.read_text())
    except Exception:
        return None
    # 容错: 兼容 list[dict] 旧 schema
    if isinstance(cache, list):
        items = cache
    elif isinstance(cache, dict):
        items = []
        for name, data in cache.items():
            if isinstance(data, dict):
                data.setdefault("name", name)
                items.append(data)
    else:
        return None

    for entry in items:
        if entry.get("name") != law:
            continue
        arts = entry.get("articles", {}) or {}
        if article and article in arts:
            return {
                "content": arts[article],
                "law": law,
                "article": article,
                "source": "cache",
                "pulled_at": entry.get("pulled_at", ""),
                "status": entry.get("status", "unknown"),
            }
        if keyword:
            for art_id, text in arts.items():
                if keyword in (text or "") or keyword in art_id:
                    return {
                        "content": text,
                        "law": law,
                        "article": art_id,
                        "source": "cache",
                        "pulled_at": entry.get("pulled_at", ""),
                        "status": entry.get("status", "unknown"),
                    }
    return None


def try_flk_npc(law: str, article: Optional[str], keyword: Optional[str]) -> dict | None:
    """L3: 爬虫结果 (references/laws/<slug>.md)"""
    # slugify 与 fetch_flk_npc.py 保持一致 — 实际应抽公共, 此处简化
    SLUG_MAP = {
        "民法典": "civil-code",
        "刑法": "criminal-law",
        "民事诉讼法": "civil-procedure-law",
        "公司法": "company-law",
        "数据安全法": "data-security-law",
        "个人信息保护法": "personal-information-protection-law",
        "网络安全法": "cyber-security-law",
        "劳动合同法": "labor-contract-law",
        "行政处罚法": "administrative-penalty-law",
        "商标法": "trademark-law",
        "专利法": "patent-law",
        "著作权法": "copyright-law",
        "反不正当竞争法": "anti-unfair-competition-law",
    }
    slug = SLUG_MAP.get(law)
    if not slug:
        return None
    md_path = LAW_DIR / f"{slug}.md"
    if not md_path.exists():
        return None
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return None
    # 截取 frontmatter
    m = re.search(r"^---\n(.*?)\n---", text, flags=re.S | re.M)
    meta: dict = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    # 找条文
    body = text[m.end():] if m else text
    if article:
        # 第 X 条
        art_num = article.replace("第", "").replace("条", "")
        pat = re.compile(rf"## 第{re.escape(art_num)}条\s*\n+(.*?)(?=\n## |\Z)", re.S)
        mm = pat.search(body)
        if mm:
            return {
                "content": mm.group(1).strip(),
                "law": law,
                "article": article,
                "source": "flk_npc",
                "fetched_at": meta.get("抓取时间", ""),
                "status": meta.get("效力", "现行有效"),
            }
    if keyword:
        mm = re.search(rf"## 第(\d+)条[^\n]*\n+(.{{0,500}}{re.escape(keyword)}.{{0,500}})", body, re.S)
        if mm:
            return {
                "content": mm.group(2).strip(),
                "law": law,
                "article": f"第{mm.group(1)}条",
                "source": "flk_npc",
                "fetched_at": meta.get("抓取时间", ""),
                "status": meta.get("效力", "现行有效"),
            }
    return None


def try_gov_cn(law: str, article: Optional[str], keyword: Optional[str]) -> dict | None:
    """L5: 政府公开源 (spp.gov.cn + gov.cn/zhengce/) — 实时补丁
    仅作为 L4 都失败后的兜底. 调用 fetch_gov_cn.py (v8.3.0+)
    """
    # 暂存 marker, 真正实现见 fetch_gov_cn.py
    gov_script = ROOT / "scripts" / "fetch_gov_cn.py"
    if not gov_script.exists():
        return None
    try:
        import subprocess
        payload = json.dumps({"law": law, "article": article, "keyword": keyword})
        r = subprocess.run(
            ["python3", str(gov_script), "--query", "--json"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                parsed = json.loads(r.stdout)
                if parsed.get("found"):
                    parsed["source"] = "gov_cn"
                    return parsed
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    return None


def retrieve(law: str, article: Optional[str] = None, keyword: Optional[str] = None,
             explain: bool = False) -> dict:
    """统一检索接口, 按 L1→L6 依次尝试"""
    chain = []
    selected = None
    selected_level = 6
    # L1
    res = try_yuandian_pkulaw(law, article, keyword)
    if res:
        chain.append("yuandian_pkulaw")
        selected = res
        selected_level = 1
    else:
        # L2: prc-law-data 数据集
        res = try_prc_law_data(law, article, keyword)
        if res:
            chain.append("prc_law_data")
            selected = res
            selected_level = 2
        else:
            # L3: 本地 cache
            res = try_local_cache(law, article, keyword)
            if res:
                chain.append("cache")
                selected = res
                selected_level = 3
            else:
                # L4: 爬虫结果 (flk_npc)
                res = try_flk_npc(law, article, keyword)
                if res:
                    chain.append("flk_npc")
                    selected = res
                    selected_level = 4
                else:
                    # L5: 政府公开源
                    res = try_gov_cn(law, article, keyword)
                    if res:
                        chain.append("gov_cn")
                        selected = res
                        selected_level = 5
                    else:
                        chain.append("none")

    label = LABEL_BY_LEVEL[selected_level].format(date=_now_date())
    if selected:
        return {
            "found": True,
            "selected_level": selected_level,
            "source_chain": chain,
            "label": label,
            "content": selected.get("content", ""),
            "law": selected.get("law", law),
            "article": selected.get("article", article),
            "metadata": {k: v for k, v in selected.items() if k not in ("content",)},
            "explain": {
                "L1_yuandian_pkulaw": "checked" if "yuandian_pkulaw" in chain else "skipped (no key or no result)",
                "L2_prc_law_data": "checked" if "prc_law_data" in chain else "skipped (unavailable or no hit)",
                "L3_cache": "checked" if "cache" in chain else "skipped (no hit)",
                "L4_flk_npc": "checked" if "flk_npc" in chain else "skipped (no file)",
                "L5_gov_cn": "checked" if "gov_cn" in chain else "skipped (no response)",
                "L6_fallback": "reached" if selected_level == 6 else "not reached",
            } if explain else "none",
        }
    return {
        "found": False,
        "selected_level": 6,
        "source_chain": chain,
        "label": LABEL_BY_LEVEL[6],
        "explain": {
            "L1_yuandian_pkulaw": "skipped (no key or no result)",
            "L2_prc_law_data": "skipped (unavailable or no hit)",
            "L3_cache": "skipped (no hit)",
            "L4_flk_npc": "skipped (no file)",
            "L5_gov_cn": "skipped (no response)",
            "L6_fallback": "reached — [待检索]",
        } if explain else "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--law", required=True)
    parser.add_argument("--article", help="如 '577' 或 '第577条'")
    parser.add_argument("--keyword", help="模糊匹配")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--explain", action="store_true")
    args = parser.parse_args()

    result = retrieve(args.law, args.article, args.keyword, explain=args.explain)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["found"]:
            print(f"✅ 找到 (L{result['selected_level']})")
            print(f"   来源链: {' → '.join(result['source_chain'])}")
            print(f"   标签: {result['label']}")
            print(f"   法律: {result['law']} {result['article']}")
            print(f"\n{result['content'][:500]}")
            if args.explain:
                print(f"\n📊 决策明细:")
                for k, v in result["explain"].items():
                    print(f"   {k}: {v}")
        else:
            print(f"❌ 未找到 (L4 fallback)")
            print(f"   标签: {result['label']}")
            if args.explain:
                for k, v in result["explain"].items():
                    print(f"   {k}: {v}")
    return 0 if result["found"] else 2


if __name__ == "__main__":
    sys.exit(main())