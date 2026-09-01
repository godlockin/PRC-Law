#!/usr/bin/env python3
"""
prcclaw_init.py — 律师工作目录初始化引导 (W16.2)

律师首次使用 PRC-Law 时运行: /prcclaw-init

流程:
  1. 检测客户端 (Claude Code / Trae / WorkBuddy)
  2. 检查是否已初始化
  3. 询问律师 4 个问题:
     a. 有无已有案例库? (是/否)
     b. 已有库路径 (若 a=是) → 分析结构
     c. 工作目录 (默认 ~/lawyer-work, 可改)
     d. 执业领域 / 主要管辖地
  4. 创建工作目录布局 (matters/ alerts/ cases.db .lawyer_profile)
  5. 写入配置到 ~/.config/prc-law/workspace.json
  6. 建议导入策略 (基于已有库分析)
  7. 写 WELCOME.md (律师使用教程)

非交互模式: --non-interactive + --existing /path/to/old/cases
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 允许从 PRC-Law/scripts/ 加载 workspace
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from workspace import (
    Workspace,
    analyze_existing_dir,
    ExistingDirAnalysis,
    CONFIG_PATH,
)


WELCOME_TEMPLATE = """# 律师工作目录使用指南

> 欢迎使用 PRC-Law 律师副驾驶 (v9.0.0+)
> 生成时间: __CREATED_AT__
> 客户端: __CLIENT__

## 目录结构

```
__WORKSPACE_DIR__/
├── .initialized              # 初始化标记 (勿删)
├── .lawyer_profile           # 律师画像 (执业领域/管辖地)
├── cases.db                  # 本地案件库 (SQLite + FTS5)
├── matters/                  # 在办案件 (每案件一个目录)
│   ├── M-2026-001/
│   │   ├── intake.json       # 接案记录
│   │   ├── timeline.json     # 时间线 (W14 自动算时效)
│   │   ├── strategy.md       # 调解策略
│   │   ├── statute.json      # 法条检索
│   │   ├── pleading.docx     # 文书 (Word)
│   │   └── notes.md          # 律师批注
│   └── M-2026-002/
└── alerts/                   # cron 提醒输出
```

## 律师日常 5 步操作

### Step 1: 接案评估
在 __CLIENT__ 中输入:
> 我接到一个新案件: 张三诉李四借款 50 万, 我证据强对方弱

系统自动:
- 提取案件要素 (当事人/标的/证据)
- 写入 `matters/M-2026-XXX/intake.json`
- 生成时间线到 `timeline.json`

### Step 2: 调解策略
> 这个案子调解策略给我看看

系统自动:
- 读你本地校准 (历史胜诉率)
- 输出让幅区间 / 胜诉率 / 风险弱点

策略单写到 `matters/M-2026-XXX/strategy.md`

### Step 3: 法条检索
> 查民法典第 577 条

系统自动从 6 级降级源中找 (本地 → prc-law-data → 元典 → flk_npc → gov.cn → 案例库)。

### Step 4: 文书起草
> 起草一份律师函

系统自动:
- 选律师函模板
- 从你前面说的事实抽取字段
- 输出 Word 到 `matters/M-2026-XXX/lawyer-letter.docx`

### Step 5: 时效管理

每天 9 点系统自动跑 (cron 调度):
- 从所有 matters/*.json 算时效
- 临近/已过期时效写入 `alerts/deadline-*.md`
- 客户端会在你打开时主动推送提醒

你也可以说: "看下本周时效" 立即触发。

## 已有案例库导入 (若有)

若你有历史案例库目录 (例如 D:\律师\案例\):

在 __CLIENT__ 中说:
> 导入我的旧案例库, 路径是 D:\律师\案例

系统会:
1. **只读** 分析你原目录结构 (文件类型 / 年度 / 案号分布)
2. 建议导入策略 (不修改原文件)
3. 落到本地 cases.db 索引 (本地检索用)

你的原文件**永远不会被动**。

## 配置文件

律师工作目录配置存于:
```
~/.config/prc-law/workspace.json
```

无需手动编辑 — 系统自动维护, 你也可在 __CLIENT__ 中说 "改工作目录" 调整。

## 客户端兼容性

支持的 AI 客户端:
- ✅ Claude Code (Anthropic 原生)
- ✅ Trae (字节跳动)
- ✅ WorkBuddy (腾讯工作台)
- ⚠️ 其他 (Cursor / Cline / Continue): 通过 Claude Code 协议兼容

## 常见问题

### Q: 我的律师工作目录在哪里?
A: 默认 `~/lawyer-work` (Windows 下为 `C:/Users/你的名字/lawyer-work`).
    系统引导时让你确认或调整, 之后可在客户端说 "改工作目录" 修改.

### Q: 我不会敲命令, 怎么用?
A: 不用敲. 你只要在 __CLIENT__ 窗口用自然语言说, 例如 "我接到一个新案件" / "调解策略给我看看".
    所有命令系统自动跑, 你看不到代码.

### Q: 已有案例库会被修改吗?
A: 不会. PRC-Law **只读**访问你指定的已有目录, 不修改原文件. 仅导入索引到本地 cases.db.

### Q: 案件数据会不会上传?
A: 不会. 所有案件数据本地存储, 不上传到任何云端.
    LLM 调用建议用境内 (Qwen/DeepSeek) 满足 PIPL 合规.

### Q: 团队协作怎么搞?
A: 当前版本: 单律师使用. 团队版 (网盘挂载 + 权限管理) 在规划中.

---

> ⚠️ **律师审阅闸**: 本指南由 PRC-Law 生成, 不构成法律意见.
> 任何对外法律行为前必须经执业律师书面确认.
"""


def prompt(question: str, default: str = "") -> str:
    """交互式提问"""
    if default:
        prompt_str = f"{question} [{default}]: "
    else:
        prompt_str = f"{question}: "
    try:
        return input(prompt_str).strip() or default
    except EOFError:
        return default


def detect_client_label(client: str) -> str:
    """客户端显示名"""
    labels = {
        "claude-code": "Claude Code",
        "trae": "Trae",
        "workbuddy": "WorkBuddy (腾讯工作台)",
        "unknown": "未知 AI 客户端",
    }
    return labels.get(client, client)


def init_workflow(non_interactive: bool = False,
                  existing: Optional[str] = None) -> int:
    """初始化工作流"""
    print("=" * 60)
    print(" PRC-Law 律师工作目录初始化 (v9.0.0+)")
    print("=" * 60)
    print()

    # === 1. 检测客户端 ===
    ws = Workspace.load(env_existing=existing)
    client_label = detect_client_label(ws.client)
    print(f"✓ 检测客户端: {client_label}")

    # === 2. 检查是否已初始化 ===
    if ws.is_initialized():
        print(f"⚠ 工作目录已初始化: {ws.workspace_dir}")
        if not non_interactive:
            ans = prompt("  重新初始化? (将清空配置, 但不删除数据) [y/N]", "N")
            if ans.lower() != "y":
                print("已取消.")
                return 0

    # === 3. 询问已有案例目录 ===
    if non_interactive:
        existing_str = existing or ""
    else:
        print()
        print("步骤 1/4: 是否有**已有案例库目录**?")
        print("  (如有, 系统会**只读**分析, 不修改原文件)")
        has_existing = prompt("  是/否 [否]", "否")
        existing_str = ""
        if has_existing.startswith(("y", "Y", "是")):
            existing_str = prompt("  已有目录路径", "")

    # === 4. 工作目录 ===
    if non_interactive:
        ws_dir_str = os.environ.get("PRC_LAW_WORKSPACE", str(Path.home() / "lawyer-work"))
    else:
        print()
        print("步骤 2/4: 工作目录")
        default_ws = str(Path.home() / "lawyer-work")
        ws_dir_str = prompt(f"  路径 [{default_ws}]", default_ws)
    ws_dir = Path(ws_dir_str).expanduser().resolve()

    # === 5. 律师画像 ===
    if non_interactive:
        practice_area = os.environ.get("PRC_LAW_PRACTICE_AREA", "综合")
        jurisdiction = os.environ.get("PRC_LAW_JURISDICTION", "未指定")
    else:
        print()
        print("步骤 3/4: 律师画像")
        practice_area = prompt("  执业领域 [综合]", "综合")
        jurisdiction = prompt("  主要管辖地 [未指定]", "未指定")

    # === 6. 重建 ws 对象 (用新参数) ===
    ws = Workspace.load(env_existing=existing_str if existing_str else None)
    ws.workspace_dir = ws_dir
    ws.existing_dir = Path(existing_str).expanduser().resolve() if existing_str else None
    ws.lawyer_profile = ws_dir / ".lawyer_profile"
    ws.cases_db = ws_dir / "cases.db"
    ws.matters_dir = ws_dir / "matters"
    ws.alerts_dir = ws_dir / "alerts"
    ws.calibration_path = ws_dir / ".calibration.json"
    ws.intake_dir = ws.existing_dir

    # === 7. 创建目录 ===
    print()
    print(f"步骤 4/4: 创建工作目录 {ws.workspace_dir}")
    ws.ensure_layout()
    print(f"  ✓ matters/    {ws.matters_dir}")
    print(f"  ✓ alerts/    {ws.alerts_dir}")
    print(f"  ✓ cases.db (待用)  {ws.cases_db}")

    # === 8. 写律师画像 ===
    profile = {
        "lawyer_id": f"lawyer-{datetime.now().strftime('%Y%m%d')}",
        "practice_area": practice_area,
        "jurisdiction": jurisdiction,
        "client": ws.client,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "version": "v9.0.0",
    }
    ws.lawyer_profile.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"  ✓ .lawyer_profile  {ws.lawyer_profile}")

    # === 9. 写配置 ===
    ws.save_config()
    print(f"  ✓ 配置  {CONFIG_PATH}")

    # === 10. 写 WELCOME.md ===
    welcome = (
        WELCOME_TEMPLATE
        .replace("__CREATED_AT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
        .replace("__CLIENT__", client_label)
        .replace("__WORKSPACE_DIR__", str(ws.workspace_dir))
    )
    welcome_path = ws.workspace_dir / "WELCOME.md"
    welcome_path.write_text(welcome, encoding="utf-8")
    print(f"  ✓ WELCOME.md  {welcome_path}")

    # === 11. 已有目录分析 (若有) ===
    if ws.existing_dir:
        print()
        print("=" * 60)
        print(f" 已有目录分析 (只读): {ws.existing_dir}")
        print("=" * 60)
        try:
            analysis = analyze_existing_dir(ws.existing_dir)
            print(f"  总文件: {analysis.total_files}")
            print(f"  总目录: {analysis.total_dirs}")
            print(f"  估计案件数 (按顶层子目录): {analysis.estimated_cases}")
            print(f"  文件类型: {analysis.file_types}")
            if analysis.year_distribution:
                print(f"  年度分布 (从文件名提取):")
                for year, count in sorted(analysis.year_distribution.items()):
                    print(f"    {year}: {count} 个文件")
            if analysis.type_distribution:
                print(f"  案号类型分布:")
                for typ, count in sorted(analysis.type_distribution.items(), key=lambda x: -x[1]):
                    print(f"    {typ}: {count} 个")
            print()
            print("  建议导入策略:")
            print(f"    {analysis.suggested_mapping['建议']}")
            print()
            print("  律师操作: 在 __CLIENT__ 中说")
            print(f'    "导入 {ws.existing_dir} 到本地案例库"')
            print("    系统自动跑索引, 落到本地 cases.db")
        except Exception as e:
            print(f"  ⚠ 分析失败: {e}")

    # === 12. 总结 ===
    print()
    print("=" * 60)
    print(" ✅ 初始化完成!")
    print("=" * 60)
    print()
    print(f" 工作目录:  {ws.workspace_dir}")
    print(f" 客户端:   {client_label}")
    print(f" 已有目录 (只读): {ws.existing_dir or '(未指定)'}")
    print()
    print(" 下一步 (律师在 __CLIENT__ 中):")
    print(f"   1. 阅读 {welcome_path}")
    print('   2. 说: "我接到一个新案件"')
    print(f'   3. 已有案例库 (若有): 说"导入 {ws.existing_dir}"')
    print()
    print(f" 配置: {CONFIG_PATH}")
    print()

    return 0


import os  # noqa: E402  (放在 init_workflow 后避免循环)


def main():
    parser = argparse.ArgumentParser(
        description="PRC-Law 律师工作目录初始化 (W16.2)")
    parser.add_argument("--existing", help="指定已有案例目录 (只读)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="非交互模式 (使用环境变量)")
    args = parser.parse_args()
    sys.exit(init_workflow(
        non_interactive=args.non_interactive,
        existing=args.existing,
    ))


if __name__ == "__main__":
    main()