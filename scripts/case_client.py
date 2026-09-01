#!/usr/bin/env python3
"""
case_client.py — PRC-Law 案例库客户端 (v8.3.0+)

数据源:
1. ca]2018 (HF) — 刑事判决 267 万条 (1.17 GB, streaming/全量)
2. LaWGPT (GitHub) — 50 万判决 + 35 万 QA
3. DISC-LawLLM (GitHub) — 403K 法律 QA

不在 git 仓库内; 首次调用时按需从 HF/GitHub 下载/streaming。

设计目标:
- 零预下载 (streaming=True)
- 与 dataset_client.py 同接口风格 (lookup/search)
- 不污染现有架构 (独立可选客户端)
- 不依赖 prc-law-data (可独立运行)

用法:
    from scripts.case_client import CaseClient
    client = CaseClient()
    hit = client.search(accusation="盗窃", imprisonment_max=12)
    if hit:
        print(hit.fact[:200])
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

ROOT = Path(__file__).resolve().parent.parent

# --- 数据源配置 ---
HF_DATASETS = {
    "cail2018": {
        "repo": "china-ai-law-challenge/cail2018",
        "splits": ["first_stage_train", "first_stage_test", "second_stage_train", "validation"],
        "size_hint": "267 万刑事判决",
        "fields": ["fact", "relevant_articles", "accusation", "imprisonment",
                   "punish_of_money", "criminals", "death_penalty", "life_imprisonment"],
        "license": "未声明 (学术免费)",
    },
}

GITHUB_DATASETS = {
    "lawgpt": {
        "url": "https://github.com/pengxiao-song/LaWGPT",
        "size_hint": "~50 万判决 + 35 万 QA",
        "license": "GPL-3.0",
        "note": "Git LFS, 需安装 git-lfs",
    },
    "disc-lawllm": {
        "url": "https://github.com/FudanDISC/DISC-LawLLM",
        "size_hint": "~403K 法律 QA",
        "license": "Apache-2.0",
        "files": ["DISC-Law-SFT-Pair-QA-released.jsonl", "DISC-Law-SFT-Triplet-QA-released.jsonl"],
    },
}


@dataclass
class CaseHit:
    """案例命中"""
    source: str           # "cail2018" / "lawgpt" / "disc-lawllm"
    fact: str             # 案情描述
    accusation: list[str] = field(default_factory=list)   # 罪名
    relevant_articles: list[int] = field(default_factory=list)  # 引用法条
    imprisonment: float = 0.0         # 刑期 (月)
    punish_of_money: float = 0.0      # 罚金
    criminals: list[str] = field(default_factory=list)
    death_penalty: bool = False
    life_imprisonment: bool = False

    @property
    def label(self) -> str:
        return f"[已确认: {self.source} 案例库]"


class CaseClient:
    """案例库客户端

    特点:
    - streaming 模式: 不预下载, 按需拉取
    - 多数据源聚合: ca]2018 + LaWGPT + DISC-LawLLM
    - 字段标准化: 所有源映射到统一 dataclass
    """

    def __init__(self, offline: bool = None):
        # 自动检测离线模式 (无网络 / 强制 PRC_LAW_OFFLINE)
        if offline is None:
            offline = bool(os.environ.get("PRC_LAW_OFFLINE"))
        self.offline = offline
        self._datasets_loaded: dict[str, object] = {}
        self._check_datasets()

    def _check_datasets(self) -> None:
        """检查 datasets 库是否可用"""
        if self.offline:
            return
        try:
            import datasets  # noqa: F401
            self._has_datasets = True
        except ImportError:
            self._has_datasets = False
            print("⚠ datasets 库不可用, pip install datasets 后重试",
                  file=sys.stderr)

    def is_available(self) -> bool:
        return self._has_datasets and not self.offline

    def describe(self) -> str:
        if not self.is_available():
            return "unavailable (install datasets + HF reachable)"
        n = sum(1 for src in HF_DATASETS.values())
        return f"hf ({n} datasets) + github ({len(GITHUB_DATASETS)} repos)"

    # --- 主入口: 按罪名搜 ---
    def search(self,
               accusation: Optional[str] = None,
               article: Optional[int] = None,
               imprisonment_max: Optional[float] = None,
               imprisonment_min: Optional[float] = None,
               limit: int = 10,
               source: str = "cail2018") -> Iterator[CaseHit]:
        """流式检索案例

        Args:
            accusation: 罪名 (中文/英文) — "盗窃" / "抢劫" / "强奸"
            article: 法条号 (刑法) — 264 (盗窃罪) / 236 (强奸罪)
            imprisonment_max: 刑期上限 (月)
            imprisonment_min: 刑期下限 (月)
            limit: 最多返回多少条
            source: 数据源 (默认 cail2018)

        Yields:
            CaseHit 对象
        """
        if source != "cail2018":
            raise NotImplementedError(f"Source {source} not yet implemented, only cail2018")
        if not self.is_available():
            return
        from datasets import load_dataset
        if "cail2018" not in self._datasets_loaded:
            # streaming=True 关键: 不预下载, 按需读取
            self._datasets_loaded["cail2018"] = load_dataset(
                "china-ai-law-challenge/cail2018",
                split="first_stage_train",
                streaming=True,
            )
        ds = self._datasets_loaded["cail2018"]
        count = 0
        for item in ds:
            # 过滤
            if accusation:
                accs = item.get("accusation", []) or []
                if not any(accusation in str(a) for a in accs):
                    continue
            if article is not None:
                arts = item.get("relevant_articles", []) or []
                if article not in arts:
                    continue
            impr = item.get("imprisonment", 0) or 0
            if imprisonment_max is not None and impr > imprisonment_max:
                continue
            if imprisonment_min is not None and impr < imprisonment_min:
                continue
            yield CaseHit(
                source="cail2018",
                fact=item.get("fact", ""),
                accusation=list(item.get("accusation") or []),
                relevant_articles=list(item.get("relevant_articles") or []),
                imprisonment=float(impr),
                punish_of_money=float(item.get("punish_of_money", 0) or 0),
                criminals=list(item.get("criminals") or []),
                death_penalty=bool(item.get("death_penalty", False)),
                life_imprisonment=bool(item.get("life_imprisonment", False)),
            )
            count += 1
            if count >= limit:
                break

    # --- 快捷: 按法条号找案例 ---
    def cases_by_article(self, article: int, limit: int = 5) -> list[CaseHit]:
        """按刑法条号找引用该条的案例"""
        return list(self.search(article=article, limit=limit))

    # --- 快捷: 按罪名统计 ---
    def stats_by_accusation(self, sample: int = 1000) -> dict[str, int]:
        """统计样本中各罪名的频次 (用于评估数据分布)"""
        from collections import Counter
        counter = Counter()
        for hit in self.search(limit=sample):
            for acc in hit.accusation:
                counter[acc] += 1
        return dict(counter.most_common())


# === CLI 测试 ===
if __name__ == "__main__":
    client = CaseClient()
    print(f"describe: {client.describe()}")
    if not client.is_available():
        raise SystemExit(2)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--accusation", help="如 '盗窃'")
    parser.add_argument("--article", type=int, help="刑法条号")
    parser.add_argument("--max-imp", type=float, help="刑期上限 (月)")
    parser.add_argument("--min-imp", type=float, help="刑期下限 (月)")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--stats", action="store_true", help="统计罪名分布")
    args = parser.parse_args()

    if args.stats:
        stats = client.stats_by_accusation(sample=args.limit * 100)
        print(f"罪名分布 (前 {args.limit}):")
        for acc, n in list(stats.items())[:args.limit]:
            print(f"  {acc}: {n}")
    else:
        hits = list(client.search(
            accusation=args.accusation,
            article=args.article,
            imprisonment_max=args.max_imp,
            imprisonment_min=args.min_imp,
            limit=args.limit,
        ))
        print(f"命中: {len(hits)} 条\n")
        for i, h in enumerate(hits, 1):
            print(f"=== 第 {i} 条 ===")
            print(f"  罪名: {h.accusation}")
            print(f"  法条: {h.relevant_articles}")
            print(f"  刑期: {h.imprisonment} 月" + (" (死刑)" if h.death_penalty else ""))
            print(f"  罚金: ¥{h.punish_of_money}")
            print(f"  事实: {h.fact[:200]}...")
            print()