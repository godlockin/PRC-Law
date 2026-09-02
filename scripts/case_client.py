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
# 2026 扩展: 接入 2023+ 新发布数据集, 优先 Apache-2.0/MIT
HF_DATASETS = {
    "cail2018": {
        "repo": "china-ai-law-challenge/cail2018",
        "splits": ["first_stage_train", "first_stage_test", "second_stage_train", "validation"],
        "size_hint": "267 万刑事判决",
        "fields": ["fact", "relevant_articles", "accusation", "imprisonment",
                   "punish_of_money", "criminals", "death_penalty", "life_imprisonment"],
        "license": "未声明 (学术免费)",
        "year": 2018,
        "type": "刑事",
    },
    # 2024 新增: 北大 ChatLaw 多案由 (民事/刑事/行政)
    "chatlaw": {
        "repo": "MunanNing/Chatlaw_Datasets",
        "size_hint": "217 MB, 混合案由",
        "fields": ["tag", "instruction", "input", "output", "cases_precedents"],
        "license": "MIT",
        "year": 2024,
        "type": "混合 (民事/刑事/行政)",
        "note": "北大 ChatLaw 项目, 民事纠纷/劳动/婚姻/交通事故",
    },
    # 2025 新增: CAIL2018 清洗版 (用于替代原版)
    "refined-cld": {
        "repo": "zhjdong/Refined-Chinese-Legal-Dataset",
        "size_hint": "170K 条 (Train/Val/Test)",
        "fields": ["fact", "meta"],
        "license": "CC-BY-NC-SA-4.0 (NC 限制)",
        "year": 2025,
        "type": "刑事 (故意伤害/盗窃/...)",
        "note": "仅学术/非商用, 替代 cail2018",
    },
    # W24 新增: 民事案由分类 (劳动/合同/侵权/婚姻/房产)
    "clcc": {
        "repo": "gehits/Chinese-Legal-Case-Classification-Dataset",
        "size_hint": "56K 条, 124 MB",
        "fields": ["instruction", "answer"],
        "license": "CC BY-NC 4.0",
        "year": 2024,
        "type": "民事 (劳动/合同/消费/侵权/婚姻/房产)",
        "note": "民事咨询多选分类, instruction 字段含案情+法条引用, 关键词检索",
    },
    # W24 新增: 民事法律 QA (含婚姻/合同/房产/信用卡/旅游)
    "legal-sft": {
        "repo": "noah248/chinese-legal-sft",
        "size_hint": "19,332 Q&A, 13.8 MB",
        "fields": ["instruction", "input", "output", "complexity"],
        "license": "CC BY-NC 4.0",
        "year": 2024,
        "type": "民事 (婚姻/合同/房产/信用卡)",
        "note": "Alpaca 格式 QA, 律师视角输出, 含 complexity 质量分数",
    },
}

# 类案检索专项数据集 (MTEB 标准)
HF_LECARD_DATASETS = {
    "lecardv2": {
        "repo": "mteb/LeCaRDv2",
        "size_hint": "159 查询 + 3,795 文档",
        "fields": ["query-id", "corpus-id", "score"],
        "license": "MIT",
        "year": 2023,
        "type": "类案检索",
        "note": "MTEB 法律检索基准, 含正负例标注",
    },
}

# 排除说明: chinese-legal-sft (CC-BY-NC-4.0 NC 限制), Law-Case (刑事), LawBench (评测基准非数据)
# 元典 API (商业付费) 通过 MCP bridge 处理, 不在此处

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
    source: str           # "cail2018" / "lawgpt" / "disc-lawllm" / "chatlaw" / "lecardv2" / "refined-cld"
    fact: str             # 案情描述
    accusation: list[str] = field(default_factory=list)   # 罪名
    relevant_articles: list[int] = field(default_factory=list)  # 引用法条
    imprisonment: float = 0.0         # 刑期 (月)
    punish_of_money: float = 0.0      # 罚金
    criminals: list[str] = field(default_factory=list)
    death_penalty: bool = False
    life_imprisonment: bool = False
    # 2024+ 新字段
    case_type: str = ""          # 案由 (民事/刑事/行政/劳动/婚姻/...)
    case_id: str = ""            # 案件 ID
    title: str = ""              # 案件标题
    instruction: str = ""        # QA 任务指令
    score: float = 0.0           # 类案相关性分数 (LeCaRDv2)

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
        self._has_datasets = False  # 显式初始化
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
        m = sum(1 for src in HF_LECARD_DATASETS.values())
        return f"hf ({n + m} datasets) + github ({len(GITHUB_DATASETS)} repos)"

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
            raise ValueError(
                f"source={source!r} 不支持. "
                f"cail2018 用 search(source='cail2018'); "
                f"其他源用专用方法: search_chatlaw / search_clcc / search_legal_sft / search_lecardv2"
            )
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

    # === 2024+ 新数据源 ===

    def search_chatlaw(self,
                       case_type: Optional[str] = None,
                       query: Optional[str] = None,
                       limit: int = 10) -> Iterator[CaseHit]:
        """ChatLaw 数据集检索 (2024, MIT, 民事/刑事/行政混合)

        适用: 民事案由类案检索 (合同/劳动/婚姻/交通/侵权)
        Args:
            case_type: 案由过滤 (如 "合同纠纷", "劳动争议")
            query: 关键词 (匹配 instruction/input/output)
            limit: 最多返回
        """
        if "chatlaw" not in self._datasets_loaded:
            try:
                from datasets import load_dataset
                self._datasets_loaded["chatlaw"] = load_dataset(
                    "MunanNing/Chatlaw_Datasets",
                    split="train",
                    streaming=True,
                )
            except Exception as e:
                print(f"⚠ Chatlaw 加载失败: {e}", file=sys.stderr)
                return
        ds = self._datasets_loaded["chatlaw"]
        count = 0
        for item in ds:
            if count >= limit:
                break
            tag = item.get("tag", "")
            if case_type and case_type not in str(tag):
                continue
            if query:
                blob = str(item.get("instruction", "")) + str(item.get("input", ""))
                if query not in blob:
                    continue
            yield CaseHit(
                source="chatlaw",
                fact=item.get("input", "")[:500],
                case_type=str(tag),
                case_id=str(item.get("id", "")),
                instruction=item.get("instruction", ""),
                title=f"[ChatLaw {tag}]",
            )
            count += 1

    def search_clcc(self,
                    case_type: Optional[str] = None,
                    query: Optional[str] = None,
                    limit: int = 10) -> Iterator[CaseHit]:
        """Chinese-Legal-Case-Classification-Dataset (W24 新增)

        适用: 民事选择题 QA — 劳动/合同/消费/侵权/婚姻/房产
        注意: 这是选择题格式, answer 是 ABCD, 案由从 input 字段提取
        Args:
            case_type: 案由过滤 (如 "合同", "劳动", "婚姻")
            query: 关键词 (匹配 input)
            limit: 最多返回
        """
        if "clcc" not in self._datasets_loaded:
            try:
                from datasets import load_dataset
                self._datasets_loaded["clcc"] = load_dataset(
                    "gehits/Chinese-Legal-Case-Classification-Dataset",
                    split="train",
                    streaming=True,
                )
            except Exception as e:
                print(f"⚠ CLCC 加载失败: {e}", file=sys.stderr)
                return
        ds = self._datasets_loaded["clcc"]
        count = 0
        for item in ds:
            if count >= limit:
                break
            inp = str(item.get("input", ""))
            if case_type and case_type not in inp:
                continue
            if query and query not in inp:
                continue
            yield CaseHit(
                source="clcc",
                fact=inp[:500],
                case_type=case_type or "民事",
                instruction=str(item.get("instruction", ""))[:200],
                title=f"[CLCC {case_type or '民事'}]",
            )
            count += 1

    def search_legal_sft(self,
                         query: Optional[str] = None,
                         complexity: Optional[str] = None,
                         limit: int = 10) -> Iterator[CaseHit]:
        """Chinese Legal SFT Dataset (W24 新增, 民事 QA)

        适用: 民事律师视角 QA — 婚姻/合同/房产/信用卡/旅游纠纷
        Args:
            query: 关键词 (匹配 instruction/input)
            complexity: 复杂度过滤 (low/medium/high)
            limit: 最多返回
        """
        if "legal-sft" not in self._datasets_loaded:
            try:
                from datasets import load_dataset
                self._datasets_loaded["legal-sft"] = load_dataset(
                    "noah248/chinese-legal-sft",
                    split="train",
                    streaming=True,
                )
            except Exception as e:
                print(f"⚠ legal-sft 加载失败: {e}", file=sys.stderr)
                return
        ds = self._datasets_loaded["legal-sft"]
        count = 0
        for item in ds:
            if count >= limit:
                break
            instruction = str(item.get("instruction", ""))
            inp = str(item.get("input", ""))
            output = str(item.get("output", ""))
            comp = str(item.get("complexity", ""))
            if complexity and comp != complexity:
                continue
            blob = instruction + inp
            if query and query not in blob:
                continue
            yield CaseHit(
                source="legal-sft",
                fact=inp[:500] if inp else instruction[:500],
                case_type=instruction[:60],
                instruction=instruction,
                title=f"[LegalSFT {comp}]",
            )
            count += 1

    def search_lecardv2(self,
                        query: str,
                        limit: int = 5,
                        threshold: float = 0.5) -> Iterator[CaseHit]:
        """LeCaRDv2 类案检索 (2023, MIT, MTEB 基准)

        适用: 类案检索 (刑事+民事混合), 与查询案例相似的历史案例
        Args:
            query: 查询文本 (案情描述)
            limit: 最多返回
            threshold: 相关性分数阈值 (0-1)
        """
        if not query:
            return
        if "lecardv2" not in self._datasets_loaded:
            try:
                from datasets import load_dataset
                # LeCaRDv2 是检索数据集, 需要 queries + corpus
                self._datasets_loaded["lecardv2_queries"] = load_dataset(
                    "mteb/LeCaRDv2", "queries",
                    streaming=True,
                )
                self._datasets_loaded["lecardv2_corpus"] = load_dataset(
                    "mteb/LeCaRDv2", "corpus",
                    streaming=True,
                )
            except Exception as e:
                print(f"⚠ LeCaRDv2 加载失败: {e}", file=sys.stderr)
                return
        # 简化: 关键词匹配 + 简单余弦近似
        # 真实场景应接 sentence-transformers
        try:
            from datasets import load_dataset
            # 直接读取 corpus, 关键词匹配 query
            corpus = load_dataset("mteb/LeCaRDv2", "corpus", streaming=True)
            count = 0
            query_tokens = set(query.lower().split())
            for item in corpus:
                if count >= limit:
                    break
                doc_text = item.get("text", "") or item.get("content", "")
                if not doc_text:
                    continue
                # 简单 token 重叠率作为相关性分数
                doc_tokens = set(doc_text.lower().split())
                if not query_tokens:
                    continue
                overlap = len(query_tokens & doc_tokens) / len(query_tokens | doc_tokens)
                if overlap >= threshold:
                    yield CaseHit(
                        source="lecardv2",
                        fact=str(doc_text)[:500],
                        case_id=str(item.get("id", item.get("corpus-id", ""))),
                        title=f"[LeCaRDv2 类案]",
                        score=overlap,
                    )
                    count += 1
        except Exception as e:
            print(f"⚠ LeCaRDv2 检索失败: {e}", file=sys.stderr)
            return

    def list_sources(self) -> list[dict]:
        """列出所有可用数据源 (用于 SKILL.md 自动生成)"""
        result = []
        for name, meta in HF_DATASETS.items():
            result.append({
                "name": name,
                "source": "HF",
                "year": meta.get("year"),
                "type": meta.get("type"),
                "license": meta.get("license"),
                "size": meta.get("size_hint"),
            })
        for name, meta in HF_LECARD_DATASETS.items():
            result.append({
                "name": name,
                "source": "HF",
                "year": meta.get("year"),
                "type": meta.get("type"),
                "license": meta.get("license"),
                "size": meta.get("size_hint"),
            })
        for name, meta in GITHUB_DATASETS.items():
            result.append({
                "name": name,
                "source": "GitHub",
                "license": meta.get("license"),
                "size": meta.get("size_hint"),
            })
        return result


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