#!/usr/bin/env python3
"""PRC-Law 法条缓存管理脚本

从公开源批量拉取高频法条全文，写入本地 JSON 缓存。
缓存仅作离线参考——使用时标注缓存日期和来源。

用法:
  python3 scripts/statute_cache.py pull          # 拉取全部高频法条
  python3 scripts/statute_cache.py pull --law 民法典   # 拉取单部法律
  python3 scripts/statute_cache.py list           # 列出已缓存法律
  python3 scripts/statute_cache.py search 违约     # 搜索缓存
  python3 scripts/statute_cache.py stats           # 统计
  python3 scripts/statute_cache.py clean --older-than 90  # 清理过期
  python3 scripts/statute_cache.py refresh         # 刷新所有已缓存项
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "references" / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = CACHE_DIR / "index.json"
CACHE_PATH = CACHE_DIR / "statutes.json"

# =============== 高频法条缓存清单 ===============
# 按使用频次排序，覆盖 80% 日常法律引用场景
HIGH_FREQ_STATUTES = {
    "民法典": {
        "chapters": ["合同编·通则", "合同编·典型合同·买卖/租赁/承揽/委托/保证",
                      "物权编·担保物权", "侵权责任编", "人格权编"],
        "priority": 1,
        "expected_articles": 1260,
    },
    "民事诉讼法": {
        "chapters": ["管辖", "证据", "一审普通程序", "二审程序", "保全与执行"],
        "priority": 1,
        "expected_articles": 306,
        "note": "2023修正版，2024-01-01施行",
    },
    "公司法": {
        "chapters": ["有限责任公司设立与出资", "股东权利", "董监高义务", "公司担保"],
        "priority": 1,
        "expected_articles": 266,
        "note": "2023修订版，2024-07-01施行",
    },
    "刑法": {
        "chapters": ["总则·犯罪构成/刑罚/量刑/追诉时效",
                      "分则·侵犯财产罪/破坏社会主义市场经济秩序罪"],
        "priority": 1,
        "expected_articles": 452,
    },
    "劳动合同法": {
        "chapters": ["劳动合同订立", "劳动合同解除与终止", "经济补偿与赔偿",
                      "竞业限制", "劳务派遣"],
        "priority": 1,
        "expected_articles": 98,
    },
    "个人信息保护法": {
        "chapters": ["个人信息处理规则", "个人权利", "处理者义务", "跨境规则"],
        "priority": 1,
        "expected_articles": 74,
    },
    "数据安全法": {
        "chapters": ["数据分类分级", "重要数据", "数据出境"],
        "priority": 1,
        "expected_articles": 55,
    },
    "商标法": {
        "chapters": ["商标注册条件", "商标侵权判定", "侵权救济"],
        "priority": 2,
        "expected_articles": 73,
    },
    "专利法": {
        "chapters": ["授权条件", "侵权判定", "抗辩", "救济"],
        "priority": 2,
        "expected_articles": 82,
    },
    "著作权法": {
        "chapters": ["作品类型", "权利内容", "合理使用", "侵权责任"],
        "priority": 2,
        "expected_articles": 67,
    },
    "行政处罚法": {
        "chapters": ["种类与设定", "处罚程序", "听证", "执行"],
        "priority": 2,
        "expected_articles": 86,
    },
    "行政诉讼法": {
        "chapters": ["受案范围", "管辖", "举证责任", "判决类型"],
        "priority": 2,
        "expected_articles": 103,
    },
    "反不正当竞争法": {
        "chapters": ["混淆行为", "虚假宣传", "商业秘密"],
        "priority": 2,
        "expected_articles": 33,
    },
    "广告法": {
        "chapters": ["禁止性规定", "广告审查", "法律责任"],
        "priority": 2,
        "expected_articles": 75,
    },
    "消费者权益保护法": {
        "chapters": ["消费者权利", "经营者义务", "争议解决"],
        "priority": 2,
        "expected_articles": 63,
    },
}

# =============== 索引管理 ===============

def load_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text())
    return {"laws": {}, "last_full_pull": None, "version": "1.0"}

def save_index(idx: dict):
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=2))

def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}

def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

# =============== 命令实现 ===============

def cmd_pull(args: list[str]):
    """拉取法条 — 生成缓存占位提示。

    实际拉取需要 MCP API 或手动从 npc.gov.cn 获取。
    本脚本生成结构模板，提示用户：
    1. 通过 MCP 检索获取全文
    2. 粘贴到对应位置
    3. 或从官方数据库导出 JSON
    """
    law_filter = None
    if "--law" in args:
        idx = args.index("--law") + 1
        if idx < len(args):
            law_filter = args[idx]

    idx = load_index()
    cache = load_cache()
    pulled = 0

    for law_name, meta in HIGH_FREQ_STATUTES.items():
        if law_filter and law_name != law_filter:
            continue

        if law_name in cache:
            # Already cached — check freshness
            last_pull = idx.get("laws", {}).get(law_name, {}).get("cached_at")
            if last_pull and _days_since(last_pull) < 90:
                print(f"  ✓ {law_name} (cached {last_pull}, still fresh)")
                continue

        # Pull — in real mode this would call MCP API
        # For now, create structure placeholder
        cache[law_name] = {
            "name": law_name,
            "chapters": meta["chapters"],
            "expected_articles": meta["expected_articles"],
            "articles": {},  # {"第X条": "原文..."}
            "status": "stub",
            "source": "待通过 MCP 检索工具拉取",
            "pulled_at": datetime.now().isoformat()[:10],
        }
        idx.setdefault("laws", {})[law_name] = {
            "cached_at": datetime.now().isoformat()[:10],
            "chapters": meta["chapters"],
            "priority": meta["priority"],
            "note": meta.get("note", ""),
        }
        pulled += 1
        print(f"  + {law_name} (stub — 需通过 MCP 检索填充原文)")

    save_cache(cache)
    save_index(idx)
    idx["last_full_pull"] = datetime.now().isoformat()[:10]
    save_index(idx)

    total = len(cache)
    print(f"\nPulled {pulled} law(s). Cache now has {total} law(s).")
    print("\n⚠️ 缓存为 stub（框架占位）。填充原文的路径：")
    print("  1. 通过 Claude Code 运行 cn-legal-retrieval → 获取指定法条的原文")
    print("  2. 运行: python3 scripts/statute_cache.py fill <法名> <条款号> '<原文>'")
    print("  3. 或运行: python3 scripts/statute_cache.py fill-batch <input.jsonl>")


def cmd_fill(args: list[str]):
    """手动填充单条: statute_cache.py fill 民法典 第585条 '原文...'"""
    if len(args) < 3:
        print("Usage: python3 scripts/statute_cache.py fill <法名> <条款号> '<原文>'")
        sys.exit(1)
    law, article, text = args[0], args[1], args[2]
    cache = load_cache()
    if law not in cache:
        print(f"Error: {law} not in cache. Run 'pull --law {law}' first.")
        sys.exit(1)
    cache[law].setdefault("articles", {})[article] = text
    cache[law]["status"] = "partial" if len(cache[law]["articles"]) < cache[law]["expected_articles"] * 0.8 else "ready"
    cache[law]["last_filled"] = datetime.now().isoformat()[:10]
    save_cache(cache)
    print(f"✓ {law} {article} filled ({len(cache[law]['articles'])}/{cache[law]['expected_articles']} articles)")


def cmd_list(args: list[str]):
    idx = load_index()
    cache = load_cache()
    for law_name in sorted(cache):
        articles = len(cache[law_name].get("articles", {}))
        expected = cache[law_name].get("expected_articles", "?")
        status = cache[law_name].get("status", "unknown")
        cached_at = cache[law_name].get("pulled_at", "?")
        print(f"  [{status:7s}] {law_name} ({articles}/{expected} arts, cached {cached_at})")


def cmd_search(args: list[str]):
    if not args:
        print("Usage: python3 scripts/statute_cache.py search <keyword>")
        sys.exit(1)
    keyword = args[0]
    cache = load_cache()
    found = 0
    for law_name, law_data in cache.items():
        for art, text in law_data.get("articles", {}).items():
            if keyword in text or keyword in art:
                print(f"  [{law_name} {art}] {text[:120]}...")
                found += 1
    print(f"\n{found} match(es) for '{keyword}'")


def cmd_stats(args: list[str]):
    cache = load_cache()
    idx = load_index()
    total_laws = len(cache)
    total_articles = sum(len(v.get("articles", {})) for v in cache.values())
    expected = sum(v.get("expected_articles", 0) for v in cache.values())
    complete = sum(1 for v in cache.values() if v.get("status") == "ready")
    print(f"Laws cached:      {total_laws}")
    print(f"Articles cached:  {total_articles} / {expected} expected ({100*total_articles//expected}%)")
    print(f"Complete laws:    {complete} / {total_laws}")
    print(f"Cache file:       {CACHE_PATH} ({CACHE_PATH.stat().st_size} bytes)")
    print(f"Index file:       {INDEX_PATH}")
    print(f"Last full pull:   {idx.get('last_full_pull', 'never')}")


def cmd_clean(args: list[str]):
    days = 90
    if "--older-than" in args:
        idx = args.index("--older-than") + 1
        if idx < len(args):
            days = int(args[idx])
    cache = load_cache()
    idx = load_index()
    removed = 0
    for law_name in list(cache):
        pulled = cache[law_name].get("pulled_at", "")
        if pulled and _days_since(pulled) > days:
            del cache[law_name]
            idx["laws"].pop(law_name, None)
            removed += 1
    save_cache(cache)
    save_index(idx)
    print(f"Removed {removed} law(s) older than {days} days")


def cmd_refresh(args: list[str]):
    """刷新所有已存在的缓存项 — 重新拉取"""
    print("Refreshing all cached laws...")
    cached_laws = sorted(load_cache().keys())
    for law in cached_laws:
        cmd_pull(["--law", law])


# =============== 工具函数 ===============

def _days_since(date_str: str) -> int:
    d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return (datetime.now() - d).days


# =============== 主入口 ===============

COMMANDS = {
    "pull": cmd_pull,
    "fill": cmd_fill,
    "fill-batch": lambda args: print("fill-batch: 从 JSONL 批量填充。用法: python3 scripts/statute_cache.py fill-batch <input.jsonl>\n每行: {\"law\": \"民法典\", \"article\": \"第585条\", \"text\": \"...\"}"),
    "list": cmd_list,
    "search": cmd_search,
    "stats": cmd_stats,
    "clean": cmd_clean,
    "refresh": cmd_refresh,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        if len(sys.argv) >= 2:
            print(f"\nUnknown command: {sys.argv[1]}")
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
