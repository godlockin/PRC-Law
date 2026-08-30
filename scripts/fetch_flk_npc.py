#!/usr/bin/env python3
"""
fetch_flk_npc.py — 从国家法律法规数据库 (flk.npc.gov.cn) 拉取法律正文

真实 endpoint (从官方 Vue SPA JS bundle 反解, 2026-08):
    POST https://flk.npc.gov.cn/law-search/search/list          (列表/搜索)
    POST https://flk.npc.gov.cn/law-search/search/flfgDetails   (法律法规详情)
    GET  https://flk.npc.gov.cn/law-search/amazonFile/previewLink (预览直链)

请求特征:
    - X-Requested-With: XMLHttpRequest (AJAX 标识)
    - X-XSRF-TOKEN: 从初始 cookie 读 (需要先 GET 主页拿到)
    - Content-Type: application/x-www-form-urlencoded (默认 form, JSON 不工作)

设计:
    - 零成本: 公开 API, 不消耗任何第三方 credit
    - 失败容忍: 单部失败只 warn, 不阻塞整批
    - 增量: 7 天内拉过 → 跳过
    - 官方权威: source label = [已确认: 国家法律法规数据库]

用法:
    python3 scripts/fetch_flk_npc.py
    python3 scripts/fetch_flk_npc.py --law 民法典
    python3 scripts/fetch_flk_npc.py --list
    python3 scripts/fetch_flk_npc.py --force
    python3 scripts/fetch_flk_npc.py --dry-run
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
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.cookiejar import CookieJar
from pathlib import Path

# --- 配置 ---
BASE_URL = "https://flk.npc.gov.cn"
ENDPOINT_LIST = f"{BASE_URL}/law-search/search/list"
ENDPOINT_DETAIL = f"{BASE_URL}/law-search/search/flfgDetails"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
RATE_LIMIT_SEC = float(os.environ.get("PRC_LAW_RATE_LIMIT", "0.5"))
MAX_RETRIES = 3

ROOT = Path(__file__).resolve().parent.parent
LAW_DIR = ROOT / "references" / "laws"
LAW_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = LAW_DIR / ".manifest.json"

HIGH_FREQ_LAWS = [
    "民法典", "刑法", "民事诉讼法", "刑事诉讼法", "行政诉讼法",
    "公司法", "数据安全法", "个人信息保护法", "网络安全法",
    "劳动合同法", "劳动法", "社会保险法",
    "行政处罚法", "行政复议法", "行政许可法", "行政强制法",
    "商标法", "专利法", "著作权法", "反不正当竞争法",
    "消费者权益保护法", "产品质量法", "广告法",
    "合同法", "物权法",
]

# Slug 映射 — 与 retrieval_router.py 保持一致
SLUG_MAP = {
    "民法典": "civil-code", "刑法": "criminal-law",
    "民事诉讼法": "civil-procedure-law", "刑事诉讼法": "criminal-procedure-law",
    "行政诉讼法": "administrative-litigation-law", "公司法": "company-law",
    "数据安全法": "data-security-law", "个人信息保护法": "personal-information-protection-law",
    "网络安全法": "cyber-security-law", "劳动合同法": "labor-contract-law",
    "劳动法": "labor-law", "社会保险法": "social-insurance-law",
    "行政处罚法": "administrative-penalty-law", "行政复议法": "administrative-reconsideration-law",
    "行政许可法": "administrative-licensing-law", "行政强制法": "administrative-coercion-law",
    "商标法": "trademark-law", "专利法": "patent-law", "著作权法": "copyright-law",
    "反不正当竞争法": "anti-unfair-competition-law",
    "消费者权益保护法": "consumer-protection-law", "产品质量法": "product-quality-law",
    "广告法": "advertising-law", "合同法": "contract-law", "物权法": "property-law",
}


def slugify(name: str) -> str:
    return SLUG_MAP.get(name, name.replace("/", "-"))


def log(msg: str) -> None:
    try:
        with (LAW_DIR / ".fetch.log").open("a") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


class NPCSession:
    """带 cookie jar + XSRF token 的会话"""
    def __init__(self):
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.xsrf: str = ""
        # 不主动 warm — 直接 post, 服务端通常容忍空 XSRF
        # 失败时再 warm

    def _warm(self):
        """首次 GET 主页拿 XSRF cookie"""
        try:
            req = urllib.request.Request(f"{BASE_URL}/", headers={"User-Agent": USER_AGENT})
            with self.opener.open(req, timeout=10) as resp:
                _ = resp.read()
            for c in self.cookie_jar:
                if c.name.upper() == "XSRF-TOKEN":
                    self.xsrf = urllib.parse.unquote(c.value)
                    break
        except Exception as e:
            log(f"warm failed: {e}")

    def post(self, url: str, data: dict, retries: int = MAX_RETRIES) -> dict | None:
        # 国法库要求 application/json (实测 2026-08: form-urlencoded 返 500)
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(url, data=body, method="POST", headers={
                    "User-Agent": USER_AGENT,
                    "X-Requested-With": "XMLHttpRequest",
                    "X-XSRF-TOKEN": self.xsrf,
                    "Content-Type": "application/json; charset=UTF-8",
                    "Accept": "application/json, text/plain, */*",
                    "Origin": BASE_URL,
                    "Referer": f"{BASE_URL}/",
                })
                with self.opener.open(req, timeout=20) as resp:
                    ct = resp.headers.get("Content-Type", "")
                    raw = resp.read()
                    if "json" in ct:
                        return json.loads(raw)
                    log(f"post {url}: non-json ct={ct} body[:300]={raw[:300]!r}")
                    return None
            except urllib.error.HTTPError as e:
                # 服务端可能要求 XSRF, 触发 warm 重试
                if e.code in (419, 403) and not self.xsrf:
                    log(f"post {url}: HTTP {e.code} — try warm XSRF")
                    self._warm()
                else:
                    log(f"post {url} attempt {attempt}: HTTP {e.code} {e.reason}")
            except (urllib.error.URLError, TimeoutError) as e:
                log(f"post {url} attempt {attempt}: {type(e).__name__} {e}")
            except json.JSONDecodeError as e:
                log(f"post {url} attempt {attempt}: JSON decode {e}")
            if attempt < retries:
                time.sleep(RATE_LIMIT_SEC * attempt)
        return None


def search_law(sess: NPCSession, name: str) -> dict | None:
    """搜索法律, 返回第一条匹配的元数据 (含 id/标题)"""
    data = {
        "pageNum": 1,
        "pageSize": 10,
        "sortField": "0",
        "keyword": name,
        "searchType": "1",
        "isDeleted": "false",
    }
    r = sess.post(ENDPOINT_LIST, data)
    if not r:
        log(f"search {name}: empty response")
        return None
    log(f"search {name}: keys={list(r.keys()) if isinstance(r, dict) else type(r).__name__}")
    if isinstance(r, dict) and r.get("code") in (200, "200", 0):
        items = r.get("data", {}).get("list", []) if isinstance(r.get("data"), dict) else []
        log(f"search {name}: {len(items)} items")
        for item in items:
            title = item.get("title") or item.get("lawTitle") or ""
            if name in title:
                return item
        if items:
            return items[0]
    log(f"search {name}: no match, code={r.get('code') if isinstance(r, dict) else '?'}")
    return None


def fetch_detail(sess: NPCSession, item: dict) -> dict | None:
    """拉详情 — 一般列表已经返回完整正文"""
    # flk.npc.gov.cn 列表接口通常返回 {title, content, office, ...} 直接可用
    # 如果内容缺失, 才走详情 endpoint
    if item.get("content") or item.get("fulltext"):
        return item
    law_id = item.get("id") or item.get("uid") or item.get("lawId")
    if not law_id:
        return None
    r = sess.post(ENDPOINT_DETAIL, {"id": str(law_id)})
    if r and isinstance(r, dict):
        return r.get("data") or r
    return None


def normalize_markdown(detail: dict, law_name: str) -> tuple[str, dict]:
    """转 markdown, 同时返回 manifest metadata"""
    title = detail.get("title") or law_name
    office = detail.get("office") or detail.get("publishOrg") or ""
    effect = detail.get("effectLevel") or detail.get("status") or "现行有效"
    pub_date = detail.get("publishDate") or detail.get("publishdate") or ""
    eff_date = detail.get("effectDate") or detail.get("effectiveDate") or ""
    content_html = detail.get("content") or detail.get("fulltext") or detail.get("body") or ""

    # HTML → 简化 markdown
    text = re.sub(r"<script[^>]*>.*?</script>", "", content_html, flags=re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S)
    # 把段落/换行转为 markdown
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n\n", text)
    text = re.sub(r"</?p[^>]*>", "", text)
    text = re.sub(r"<h(\d)[^>]*>(.*?)</h\1>", lambda m: f"\n{'#'*int(m.group(1))} {m.group(2)}\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    md = [
        f"# {title}",
        "",
        f"> **来源**: 国家法律法规数据库 (flk.npc.gov.cn)",
        f"> **效力**: {effect}",
        f"> **制定机关**: {office}",
        f"> **发布日期**: {pub_date}",
        f"> **生效日期**: {eff_date}",
        f"> **抓取时间**: {datetime.now(timezone(timedelta(hours=8))).isoformat()}",
        "",
        "---",
        "",
        text,
    ]
    return "\n".join(md), {
        "title": title,
        "office": office,
        "status": effect,
        "publish_date": pub_date,
        "effective_date": eff_date,
    }


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except Exception:
            pass
    return {"laws": {}, "last_run": None}


def save_manifest(m: dict) -> None:
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2))
    tmp.replace(MANIFEST_PATH)


def should_skip(slug: str, manifest: dict, force: bool, max_age_days: int = 7) -> bool:
    if force:
        return False
    entry = manifest.get("laws", {}).get(slug)
    md_path = LAW_DIR / f"{slug}.md"
    if not entry or not md_path.exists():
        return False
    last = entry.get("last_fetched", "")
    if not last:
        return False
    try:
        return (datetime.now() - datetime.fromisoformat(last)).days < max_age_days
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--law", help="单部法律(中文名)")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.list:
        print(f"# 高频法律清单 ({len(HIGH_FREQ_LAWS)} 部)")
        for n in HIGH_FREQ_LAWS:
            print(f"  - {n}  →  {slugify(n)}")
        return 0

    targets = [args.law] if args.law else HIGH_FREQ_LAWS
    manifest = load_manifest()
    manifest.setdefault("laws", {})
    sess = NPCSession()
    print(f"🔐 session: xsrf={'✓' if sess.xsrf else '✗'}")

    succeeded, skipped, failed = 0, 0, 0

    for name in targets:
        slug = slugify(name)
        if should_skip(slug, manifest, args.force):
            print(f"⏭ {name}  (recent)")
            skipped += 1
            continue
        if args.dry_run:
            print(f"📥 {name} → {slug}.md")
            continue
        print(f"📥 {name}...", end=" ", flush=True)
        time.sleep(RATE_LIMIT_SEC)
        meta = search_law(sess, name)
        if not meta:
            print("⚠ search fail")
            failed += 1
            continue
        detail = fetch_detail(sess, meta)
        if not detail:
            print("⚠ detail fail")
            failed += 1
            continue
        try:
            md, info = normalize_markdown(detail, name)
            md_path = LAW_DIR / f"{slug}.md"
            md_path.write_text(md, encoding="utf-8")
            sha = hashlib.sha256(md.encode()).hexdigest()[:16]
            manifest["laws"][slug] = {
                **info,
                "last_fetched": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                "source": "flk.npc.gov.cn",
                "sha256_16": sha,
            }
            print(f"✓ {len(md)} chars")
            succeeded += 1
        except Exception as e:
            print(f"⚠ write: {e}")
            failed += 1

    manifest["last_run"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
    save_manifest(manifest)
    print(f"\n📊 done: {succeeded} ok / {skipped} skip / {failed} fail")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)