#!/usr/bin/env python3
"""PRC-Law 批量缓存填充 — 从元典 MCP 一次拉取多条法条原文并写入缓存。

用法:
  python3 scripts/fill_cache_batch.py --law 民法典 --start 1 --end 100
  python3 scripts/fill_cache_batch.py --law 劳动合同法 --all
  python3 scripts/fill_cache_batch.py --priority 1    # 填充所有 priority=1 的法律
  python3 scripts/fill_cache_batch.py --dry-run        # 仅显示将要填充的条款，不实际拉取

依赖:
  - 需要配置 yuandian MCP 连接器（.mcp.json 中 YUANDIAN_API_KEY 环境变量）
  - 或通过 --file 参数从 JSONL 文件批量导入
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from subprocess import run, PIPE

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "references" / ".cache" / "statutes.json"

# Priority-1 + Priority-2 laws with their article ranges
LAWS = {
    "民法典": {"articles": 1260, "priority": 1},
    "民事诉讼法": {"articles": 306, "priority": 1},
    "公司法": {"articles": 266, "priority": 1},
    "刑法": {"articles": 452, "priority": 1},
    "劳动合同法": {"articles": 98, "priority": 1},
    "个人信息保护法": {"articles": 74, "priority": 1},
    "数据安全法": {"articles": 55, "priority": 1},
    "商标法": {"articles": 73, "priority": 2},
    "专利法": {"articles": 82, "priority": 2},
    "著作权法": {"articles": 67, "priority": 2},
    "行政处罚法": {"articles": 86, "priority": 2},
    "行政诉讼法": {"articles": 103, "priority": 2},
    "反不正当竞争法": {"articles": 33, "priority": 2},
    "广告法": {"articles": 75, "priority": 2},
    "消费者权益保护法": {"articles": 63, "priority": 2},
}


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def fill_from_file(filepath: str):
    """从 JSONL 文件批量导入。每行: {"law":"民法典","article":"第585条","text":"..."}"""
    cache = load_cache()
    added = 0
    path = Path(filepath)
    if not path.exists():
        print(f"Error: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    lines = path.read_text().strip().split("\n")
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            law = row["law"]
            article = row["article"]
            text = row["text"]
        except (KeyError, json.JSONDecodeError) as e:
            print(f"  SKIP: {e} — {line[:80]}...", file=sys.stderr)
            continue

        if law not in cache:
            print(f"  SKIP: {law} not in cache index. Run 'statute_cache.py pull' first.", file=sys.stderr)
            continue

        cache[law].setdefault("articles", {})[article] = text
        added += 1

    # Update status
    for law_name, law_data in cache.items():
        n = len(law_data.get("articles", {}))
        expected = law_data.get("expected_articles", 0)
        if expected > 0 and n >= expected * 0.8:
            law_data["status"] = "ready"
        elif n > 0:
            law_data["status"] = "partial"
        law_data["last_filled"] = datetime.now().isoformat()[:10]

    save_cache(cache)

    total = sum(len(v.get("articles", {})) for v in cache.values())
    expected_total = sum(v.get("expected_articles", 0) for v in cache.values())
    print(f"Added {added} articles. Cache now: {total}/{expected_total} ({100*total//expected_total}%)")


def fill_from_api(law_name: str, article_range: str = "all", dry_run: bool = False):
    """通过 MCP API 拉取法条原文。

    实际执行方式:
      1. 在 Claude Code 中调用 cn-legal-retrieval
      2. 检索结果中的法条文本通过 statute_cache.py fill 逐条写入缓存
    本函数打印将要填充的条款列表作为指引。
    """
    cache = load_cache()
    if law_name not in cache:
        print(f"Error: {law_name} not in cache. Run pull first.", file=sys.stderr)
        sys.exit(1)

    existing = set(cache[law_name].get("articles", {}).keys())
    total = cache[law_name].get("expected_articles", 0)

    if article_range == "all":
        targets = [f"第{i}条" for i in range(1, total + 1)]
    else:
        parts = article_range.split("-")
        start = int(parts[0])
        end = int(parts[1]) if len(parts) > 1 else start
        targets = [f"第{i}条" for i in range(start, end + 1)]

    missing = [a for a in targets if a not in existing]

    if dry_run:
        print(f"[DRY RUN] {law_name}: {len(missing)} articles to fill")
        for a in missing[:20]:
            print(f"  {law_name} {a}")
        if len(missing) > 20:
            print(f"  ... and {len(missing)-20} more")
        return

    print(f"{law_name}: {len(missing)} articles needed ({len(targets)} total, {len(existing)} cached)")
    print("\n填充方式:")
    print(f"  1. 在 Claude Code 中运行: /cn-legal-retrieval \"{law_name}\"")
    print(f"  2. 对检索到的每条法条，调用: python3 scripts/statute_cache.py fill \\")
    print(f"       \"{law_name}\" \"<条款号>\" \"<法条原文>\"")
    print(f"  3. 或准备 JSONL 文件后运行: python3 scripts/fill_cache_batch.py --file <input.jsonl>")
    print(f"\nJSONL 格式: {{\"law\": \"{law_name}\", \"article\": \"第X条\", \"text\": \"...\"}}")


def main():
    args = sys.argv[1:]

    if "--file" in args:
        idx = args.index("--file") + 1
        if idx >= len(args):
            print("Error: --file requires a path", file=sys.stderr)
            sys.exit(1)
        fill_from_file(args[idx])
        return

    law_name = None
    article_range = "all"
    dry_run = "--dry-run" in args
    priority_filter = None

    if "--law" in args:
        idx = args.index("--law") + 1
        if idx >= len(args):
            print("Error: --law requires a law name", file=sys.stderr)
            sys.exit(1)
        law_name = args[idx]

    if "--start" in args:
        sidx = args.index("--start") + 1
        eidx = args.index("--end") + 1 if "--end" in args else -1
        start = int(args[sidx]) if sidx < len(args) else 1
        end = int(args[eidx]) if eidx > 0 and eidx < len(args) else start
        article_range = f"{start}-{end}"

    if "--all" in args:
        article_range = "all"

    if "--priority" in args:
        idx = args.index("--priority") + 1
        if idx >= len(args):
            print("Error: --priority requires a number", file=sys.stderr)
            sys.exit(1)
        priority_filter = int(args[idx])

    if priority_filter:
        for name, meta in LAWS.items():
            if meta["priority"] == priority_filter:
                fill_from_api(name, "all", dry_run)
    elif law_name:
        fill_from_api(law_name, article_range, dry_run)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
