#!/usr/bin/env python3
"""
fetch_court_guides.py — 拉最高法/最高检指导性案例 + 公报案例

数据源:
    https://www.court.gov.cn   (最高法官网, 指导案例栏目)
    https://www.spp.gov.cn     (最高检官网, 指导案例栏目)
    公开访问, 无需 key

输出:
    data/cases/guides/<year>-<seq>.md   — 单篇案例 markdown
    data/cases/guides/.manifest.json   — 索引

设计原则与 fetch_flk_npc.py 完全一致:
- 零成本 + 失败容忍 + 增量 + resumable + 官方权威

用法:
    python3 scripts/fetch_court_guides.py
    python3 scripts/fetch_court_guides.py --source court   # 仅最高法
    python3 scripts/fetch_court_guides.py --year 2024
    python3 scripts/fetch_court_guides.py --list
    python3 scripts/fetch_court_guides.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- 配置 ---
COURT_URL = "https://www.court.gov.cn"
SPP_URL = "https://www.spp.gov.cn"
USER_AGENT = "prc-law-fetcher/1.0 (+https://github.com/godlockin/PRC-Law)"
RATE_LIMIT_SEC = float(os.environ.get("PRC_LAW_RATE_LIMIT", "0.5"))
MAX_RETRIES = 3

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "cases" / "guides"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = OUT_DIR / ".manifest.json"

# 指导案例栏目(精确路径需根据官网调整, 留好接口)
COURT_GUIDE_PATHS = [
    "/fabu/gengduo/15/",   # 指导案例栏目(候选路径)
    "/fabuduanbai/",      # 公报案例(候选)
]


def log(msg: str) -> None:
    try:
        with (OUT_DIR / ".fetch.log").open("a") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except Exception:
            pass
    return {"guides": {}, "last_run": None}


def save_manifest(m: dict) -> None:
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2))
    tmp.replace(MANIFEST_PATH)


def http_get(url: str) -> bytes | None:
    if params_qs := re.search(r"\?(.+)$", url):
        pass  # already encoded
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            log(f"GET {url} attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RATE_LIMIT_SEC * attempt)
    return None


def list_guides(source: str) -> list[dict]:
    """
    列出某来源的指导案例索引
    返回 [{"title", "url", "date", "seq"}]
    实际解析需根据官网 HTML 调整, 这里留好接口签名
    """
    base = COURT_URL if source == "court" else SPP_URL
    for path in COURT_GUIDE_PATHS:
        url = f"{base}{path}"
        html = http_get(url)
        if not html:
            continue
        try:
            text = html.decode("utf-8", errors="ignore")
        except Exception:
            continue
        # 启发式: 找所有包含 "指导案例" 或 "检例" 的 <a> 链接
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*(?:指导案例|检例|典型案例)[^<]*)</a>', text)
        return [{"url": u if u.startswith("http") else f"{base}{u}", "title": t.strip()} for u, t in links[:20]]
    return []


def fetch_guide(url: str) -> dict | None:
    """拉单篇案例详情"""
    html = http_get(url)
    if not html:
        return None
    try:
        text = html.decode("utf-8", errors="ignore")
    except Exception:
        return None
    # 去 HTML 标签
    plain = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S)
    plain = re.sub(r"<style[^>]*>.*?</style>", "", plain, flags=re.S)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    # 启发式截取正文
    m = re.search(r"((?:指导案例|检例|典型案例).{200,5000}?(?=相关推荐|相关报道|版权所有|$))", plain)
    body = m.group(1) if m else plain[:3000]
    return {"url": url, "text": body, "fetched_at": datetime.now(timezone(timedelta(hours=8))).isoformat()}


def guid_from_url(url: str) -> str:
    """URL → 文件名友好的 id"""
    h = hashlib.sha1(url.encode()).hexdigest()[:12]
    return h


def should_skip(gid: str, manifest: dict, force: bool, max_age_days: int = 14) -> bool:
    if force:
        return False
    entry = manifest.get("guides", {}).get(gid)
    if not entry:
        return False
    md_path = OUT_DIR / f"{gid}.md"
    if not md_path.exists():
        return False
    last = entry.get("last_fetched", "")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now() - last_dt).days < max_age_days
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["court", "spp", "all"], default="all")
    parser.add_argument("--year", help="只拉某年的(如 2024)")
    parser.add_argument("--list", action="store_true", help="只列出 index 链接, 不下载")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sources = (["court", "spp"] if args.source == "all" else [args.source])

    manifest = load_manifest()
    manifest.setdefault("guides", {})

    succeeded, skipped, failed = 0, 0, 0

    for src in sources:
        print(f"📂 列表: {src}...")
        indexes = list_guides(src)
        print(f"   found {len(indexes)} guides")
        for ix in indexes:
            gid = guid_from_url(ix["url"])
            if should_skip(gid, manifest, args.force):
                skipped += 1
                if not args.dry_run:
                    print(f"⏭ {ix['title']}  (recent)")
                continue
            if args.list or args.dry_run:
                print(f"  - {ix['title']}  →  {ix['url']}")
                continue
            print(f"📥 {ix['title']}...", end=" ", flush=True)
            time.sleep(RATE_LIMIT_SEC)
            content = fetch_guide(ix["url"])
            if not content:
                print("⚠ failed")
                failed += 1
                continue
            md = (
                f"# {ix['title']}\n\n"
                f"> **来源**: {'最高法' if src == 'court' else '最高检'} 官网\n"
                f"> **URL**: {ix['url']}\n"
                f"> **抓取时间**: {content['fetched_at']}\n\n"
                f"---\n\n{content['text']}\n"
            )
            try:
                (OUT_DIR / f"{gid}.md").write_text(md, encoding="utf-8")
                manifest["guides"][gid] = {
                    "title": ix["title"],
                    "url": ix["url"],
                    "source": src,
                    "last_fetched": content["fetched_at"],
                }
                print(f"✓")
                succeeded += 1
            except Exception as e:
                print(f"⚠ write: {e}")
                failed += 1

    manifest["last_run"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
    save_manifest(manifest)

    print(f"\n📊 done: {succeeded} ok / {skipped} skip / {failed} fail")
    log(f"run done: {succeeded} ok / {skipped} skip / {failed} fail")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)