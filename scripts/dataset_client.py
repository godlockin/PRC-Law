#!/usr/bin/env python3
"""
dataset_client.py — PRC-Law 调用 prc-law-data 客户端

支持 3 种对接模式 (按优先级自动探测):
1. **Submodule 本地路径**: `vendor/prc-law-data/data/statutes/<slug>.json`
2. **环境变量 PRC_LAW_DATA_DIR**: 自定义路径
3. **HTTP 远程**: `PRC_LAW_DATA_URL` 环境变量, 如 http://localhost:8765
4. **None**: 返回 None, 让上层 fallback 链继续

用法:
    from scripts.dataset_client import DatasetClient
    client = DatasetClient()
    hit = client.lookup(law="民法典", article="577")
    if hit:
        print(hit.content)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# 模式探测优先级 (W8.4 — 禁止硬编码绝对路径)
CANDIDATE_DIRS: list[Path] = []
# 1. 环境变量 (优先级最高, 律师可显式指定)
_env_dir = os.environ.get("PRC_LAW_DATA_DIR", "").strip()
if _env_dir:
    CANDIDATE_DIRS.append(Path(_env_dir))
# 2. Submodule 路径 (git submodule add vendor/prc-law-data)
CANDIDATE_DIRS.append(ROOT / "vendor" / "prc-law-data" / "data")
# 3. sibling 路径 (同级仓库布局)
CANDIDATE_DIRS.append(ROOT.parent / "prc-law-data" / "data")
# 4. 默认相对路径 (假设 scripts/dataset_client.py 在 PRC-Law/scripts/)
#     不写绝对路径, 自动从 ROOT 推导

CN_DIGITS = "零一二三四五六七八九"
CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _cn_to_int(cn: str) -> Optional[int]:
    """中文数字 → 阿拉伯数字 (与 prc-law-data import.py 保持一致)"""
    if not cn:
        return None
    if cn.isdigit():
        return int(cn)
    if cn == "十":
        return 10
    if all(c in CN_DIGITS or c in CN_UNITS for c in cn):
        if "亿" in cn or "万" in cn:
            return None
        total = 0
        current = 0
        for c in cn:
            if c in CN_DIGITS:
                current = CN_DIGITS.index(c)
            else:
                unit = CN_UNITS[c]
                if current == 0:
                    current = 1
                total += current * unit
                current = 0
        total += current
        return total
    return None


@dataclass
class DatasetHit:
    law: str
    slug: str
    article: str
    content: str
    source: str           # "prc-law-data" (本地) / "prc-law-data-http" (远程)
    source_detail: str    # upstream via (e.g. "laws-data")
    fetched_at: str
    article_count: int

    @property
    def label(self) -> str:
        return f"[已确认: prc-law-data 离线数据集 {self.fetched_at[:10]}]"


class DatasetClient:
    """PRC-Law 数据集客户端 — 自动探测本地/远程/未配置"""

    def __init__(self):
        self.mode = "none"
        self.data_dir: Optional[Path] = None
        self.http_url: Optional[str] = None
        self._index_cache: Optional[dict[str, dict]] = None
        self._slug_map_cache: Optional[dict[str, str]] = None

        # 探测优先级
        # 1. 环境变量 PRC_LAW_DATA_DIR
        env_dir = os.environ.get("PRC_LAW_DATA_DIR", "").strip()
        if env_dir:
            p = Path(env_dir)
            if (p / "statutes").exists():
                self.mode = "local"
                self.data_dir = p
                return

        # 2. 环境变量 PRC_LAW_DATA_URL (HTTP)
        env_url = os.environ.get("PRC_LAW_DATA_URL", "").strip()
        if env_url:
            self.mode = "http"
            self.http_url = env_url.rstrip("/")
            return

        # 3. 探测候选路径
        for cand in CANDIDATE_DIRS:
            if (cand / "statutes").exists():
                self.mode = "local"
                self.data_dir = cand
                return

    def is_available(self) -> bool:
        return self.mode != "none"

    def describe(self) -> str:
        if self.mode == "local":
            n = len(list((self.data_dir / "statutes").glob("*.json")))
            return f"local ({n} laws @ {self.data_dir})"
        if self.mode == "http":
            return f"http ({self.http_url})"
        return "none (未配置 prc-law-data)"

    # === 索引 (本地) ===
    def _load_index(self) -> dict[str, dict]:
        if self._index_cache is not None:
            return self._index_cache
        if self.mode != "local":
            return {}
        idx_path = self.data_dir / "index" / "laws.jsonl"
        if not idx_path.exists():
            return {}
        items = {}
        for line in idx_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                items[e["id"]] = e
            except Exception:
                pass
        self._index_cache = items
        return items

    def _load_slug_map(self) -> dict[str, str]:
        if self._slug_map_cache is not None:
            return self._slug_map_cache
        if self.mode != "local":
            return {}
        map_path = self.data_dir / "index" / "slug-map.json"
        if not map_path.exists():
            return {}
        self._slug_map_cache = json.loads(map_path.read_text(encoding="utf-8"))
        return self._slug_map_cache

    # === 主入口 ===
    def lookup(self, law: str, article: Optional[str] = None,
               keyword: Optional[str] = None) -> Optional[DatasetHit]:
        if self.mode == "none":
            return None

        # 解析 slug
        slug_map = self._load_slug_map()
        slug = slug_map.get(law) or slug_map.get(law.replace("中华人民共和国", ""))
        if not slug:
            return None

        if self.mode == "local":
            return self._lookup_local(slug, law, article, keyword)
        if self.mode == "http":
            return self._lookup_http(slug, law, article, keyword)
        return None

    def _lookup_local(self, slug: str, law: str, article: Optional[str],
                      keyword: Optional[str]) -> Optional[DatasetHit]:
        path = self.data_dir / "statutes" / f"{slug}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        arts_by_int = data.get("articles_by_int", {})
        arts_cn = data.get("articles", {})
        article_count = data.get("article_count", len(arts_cn))

        # 按 article 查找
        if article:
            # article 可能是 "577" 或 "第577条" 或 "五百七十七"
            art_num = article.replace("第", "").replace("条", "").strip()
            text = arts_by_int.get(art_num)
            if not text:
                # 尝试中文转阿拉伯
                n = _cn_to_int(art_num)
                if n is not None:
                    text = arts_by_int.get(str(n))
            if not text:
                text = arts_cn.get(art_num)
            if text:
                return DatasetHit(
                    law=data["name"], slug=slug, article=art_num,
                    content=text, source="prc-law-data",
                    source_detail=data.get("source", {}).get("via", ""),
                    fetched_at=data.get("source", {}).get("fetched_at", ""),
                    article_count=article_count,
                )
            return None

        # 按 keyword 模糊匹配 (中文条号也能匹配)
        if keyword:
            for art_num, text in arts_by_int.items():
                if keyword in text:
                    return DatasetHit(
                        law=data["name"], slug=slug, article=str(art_num),
                        content=text, source="prc-law-data",
                        source_detail=data.get("source", {}).get("via", ""),
                        fetched_at=data.get("source", {}).get("fetched_at", ""),
                        article_count=article_count,
                    )
            return None

        # 无 article/keyword: 返回法律全文第一条 (作为 fallback 元数据)
        first_art = next(iter(arts_by_int.items()), None)
        if first_art:
            return DatasetHit(
                law=data["name"], slug=slug, article=str(first_art[0]),
                content=first_art[1], source="prc-law-data",
                source_detail=data.get("source", {}).get("via", ""),
                fetched_at=data.get("source", {}).get("fetched_at", ""),
                article_count=article_count,
            )
        return None

    def _lookup_http(self, slug: str, law: str, article: Optional[str],
                     keyword: Optional[str]) -> Optional[DatasetHit]:
        try:
            if article:
                art_num = article.replace("第", "").replace("条", "").strip()
                n = _cn_to_int(art_num) or art_num
                url = f"{self.http_url}/v1/statute/{slug}/article/{n}"
            else:
                url = f"{self.http_url}/v1/laws/{slug}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if "error" in payload:
                return None
            if article:
                return DatasetHit(
                    law=payload.get("law", law), slug=slug, article=art_num,
                    content=payload.get("content", ""), source="prc-law-data-http",
                    source_detail=payload.get("source", ""),
                    fetched_at=payload.get("fetched_at", ""),
                    article_count=0,
                )
            return None
        except (urllib.error.URLError, json.JSONDecodeError, KeyError):
            return None


# === 快速命令行测试 ===
if __name__ == "__main__":
    client = DatasetClient()
    print(f"mode: {client.mode}")
    print(f"describe: {client.describe()}")
    if not client.is_available():
        print("❌ prc-law-data 不可用")
        print("设置方法:")
        print("  1. git submodule: 把 prc-law-data 放到 vendor/prc-law-data/")
        print("  2. 环境变量: export PRC_LAW_DATA_DIR=/path/to/prc-law-data/data")
        print("  3. 远程 HTTP: export PRC_LAW_DATA_URL=http://localhost:8765")
        raise SystemExit(2)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--law", required=True)
    parser.add_argument("--article")
    parser.add_argument("--keyword")
    args = parser.parse_args()

    hit = client.lookup(args.law, args.article, args.keyword)
    if hit:
        print(f"✅ 命中")
        print(f"   法律: {hit.law}")
        print(f"   条: {hit.article}")
        print(f"   标签: {hit.label}")
        print(f"   源: {hit.source} ({hit.source_detail})")
        print(f"\n{hit.content[:500]}")
    else:
        print(f"❌ 未命中")
        raise SystemExit(1)