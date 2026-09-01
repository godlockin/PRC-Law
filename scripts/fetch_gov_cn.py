#!/usr/bin/env python3
"""
fetch_gov_cn.py — 中国政府公开源实时 fetcher

支持两种源:
1. 最高人民检察院 spp.gov.cn (指导性案例 + 典型案例)
2. 国务院政策文件库 gov.cn/zhengce/ (行政法规 + 规范性文件)

作为 PRC-Law retrieval_router L5 fallback,补充离线数据集的时效性.

用法:
    # 列模式
    python3 fetch_gov_cn.py --list spp
    python3 fetch_gov_cn.py --list gov

    # 检索模式 (供 retrieval_router L5 调用)
    python3 fetch_gov_cn.py --query '{...}' --json

    # 健康检查
    python3 fetch_gov_cn.py --health
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "references" / ".cache" / "gov_cn"

UA = "Mozilla/5.0 (PRC-Law/8.3.0; +https://github.com/your-org/PRC-Law) AppleWebKit/537.36"
SPP_BASE = "https://www.spp.gov.cn"
GOV_BASE = "https://www.gov.cn"

# 最高检 已知栏目 (实测可达)
SPP_SECTIONS = [
    ("指导性案例", "/spp/jczdal/index.shtml"),
    ("典型案例", "/spp/zdgz/index.shtml"),
    ("检察业务文件", "/spp/zcyjd/index.shtml"),
]

# 国务院 已知栏目 (首页列政策文件 + 列表页)
GOV_SECTIONS = [
    ("最新政策", "/zhengce/index.htm"),
    ("行政法规", "/zhengce/xxgkwj/index.htm"),
    ("部门规章", "/zhengce/bumenjianbao/index.htm"),
]


def _http_get(url: str, encoding: str = "utf-8") -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            return data.decode(encoding, errors="ignore")
    except Exception as e:
        return None


def _http_get_gbk(url: str) -> Optional[str]:
    """兼容 GBK 编码页面"""
    return _http_get(url, encoding="gbk")


def _decode(data: bytes) -> str:
    """智能检测: 优先 UTF-8, 失败回退 GBK"""
    for enc in ("utf-8", "gbk", "gb2312"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def fetch_spp_list(section_name: str, path: str, max_pages: int = 3) -> list[dict]:
    """拉取最高检某栏目列表 + 链接 (实测 UTF-8)"""
    items = []
    for page in range(1, max_pages + 1):
        url = f"{SPP_BASE}{path}" if page == 1 else f"{SPP_BASE}{path.rsplit('/', 1)[0]}/index_{page}.shtml"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
        except Exception:
            break
        html = _decode(raw)
        if not html:
            break
        # 提取案例链接: /spp/jczdal/202508/t20250815_xxxxxx.shtml
        pattern = re.compile(r'href="(/spp/[^"]+t\d{8}_\d+\.shtml)"[^>]*>([^<]+)</a>')
        for m in pattern.finditer(html):
            href, title = m.group(1), m.group(2).strip()
            if title and len(title) > 4:
                items.append({
                    "source": "spp.gov.cn",
                    "section": section_name,
                    "title": title,
                    "url": SPP_BASE + href,
                    "fetched_at": _now_iso(),
                })
    return items


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_gov_list(section_name: str, path: str, max_pages: int = 3) -> list[dict]:
    """拉取国务院某栏目列表 + 链接 (gov.cn 链接是完整 URL)"""
    items = []
    for page in range(1, max_pages + 1):
        url = f"{GOV_BASE}{path}" if page == 1 else f"{GOV_BASE}{path.rsplit('.', 1)[0]}_{page}.htm"
        html = _http_get(url)
        if not html:
            break
        # gov.cn 链接是绝对 URL: https://www.gov.cn/zhengce/content/...
        # 但首页用 ../相对路径, 展开为完整 URL
        pattern = re.compile(r'href="(https?://www\.gov\.cn/zhengce/[^"]+\.htm|/\.\./[^"]+\.htm|/zhengce/[^"]+\.htm)"[^>]*>([^<]+)</a>')
        for m in pattern.finditer(html):
            href, title = m.group(1), m.group(2).strip()
            if not title or len(title) <= 4:
                continue
            # 标准化为绝对 URL
            if href.startswith("/../"):
                full_url = "https://www.gov.cn" + href[3:]
            elif href.startswith("/"):
                full_url = "https://www.gov.cn" + href
            else:
                full_url = href
            items.append({
                "source": "gov.cn",
                "section": section_name,
                "title": title,
                "url": full_url,
                "fetched_at": _now_iso(),
            })
    return items
    """拉取国务院某栏目列表 + 链接"""
    items = []
    for page in range(1, max_pages + 1):
        url = f"{GOV_BASE}{path}" if page == 1 else f"{GOV_BASE}{path.rsplit('.', 1)[0]}_{page}.htm"
        html = _http_get(url)
        if not html:
            break
        # 提取文件链接: /zhengce/content/202508/xxx.htm 或 /zhengce/2025-08/15/content_xxxxxx.htm
        pattern = re.compile(r'href="(/zhengce/[^"]+content[^"]+\.htm)"[^>]*>([^<]+)</a>')
        for m in pattern.finditer(html):
            href, title = m.group(1), m.group(2).strip()
            if title and len(title) > 4:
                items.append({
                    "source": "gov.cn",
                    "section": section_name,
                    "title": title,
                    "url": GOV_BASE + href,
                    "fetched_at": _now_iso(),
                })
    return items


def health() -> dict:
    """检查可达性"""
    result = {"spp.gov.cn": False, "gov.cn": False}
    # spp 测试一个栏目 (实际 UTF-8)
    try:
        req = urllib.request.Request(f"{SPP_BASE}/spp/jczdal/index.shtml",
                                     headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = _decode(resp.read())
        result["spp.gov.cn"] = bool(html and "指导性" in html)
    except Exception:
        pass
    # gov.cn 测试
    try:
        req = urllib.request.Request(f"{GOV_BASE}/zhengce/index.htm",
                                     headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = _decode(resp.read())
        result["gov.cn"] = bool(html and "政策" in html)
    except Exception:
        pass
    return result


def query(payload: dict) -> dict:
    """retrieval_router L5 调用: 按 law/article/keyword 检索政府源

    当前实现: 简化版 — 列出 spp.gov.cn + gov.cn 最新条目, 标题匹配
    """
    law = payload.get("law", "")
    keyword = payload.get("keyword", "")
    article = payload.get("article", "")
    results = []
    health_status = health()
    # spp
    if health_status["spp.gov.cn"]:
        for section_name, path in SPP_SECTIONS[:1]:  # 仅第一个栏目 (省时)
            for item in fetch_spp_list(section_name, path, max_pages=1):
                if (keyword and keyword in item["title"]) or \
                   (law and law in item["title"]):
                    results.append(item)
    # gov.cn
    if health_status["gov.cn"]:
        for section_name, path in GOV_SECTIONS[:1]:
            for item in fetch_gov_list(section_name, path, max_pages=1):
                if (keyword and keyword in item["title"]) or \
                   (law and law in item["title"]):
                    results.append(item)
    if results:
        return {
            "found": True,
            "law": law,
            "article": article or "(列表匹配)",
            "content": "\n".join([f"- [{r['source']}] {r['title']} ({r['url']})" for r in results[:5]]),
            "items": results[:5],
            "fetched_at": _now_iso(),
        }
    return {"found": False, "law": law, "article": article, "items": []}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", choices=["spp", "gov"], help="列出某源最近条目")
    parser.add_argument("--query", help="retrieval_router JSON 调用 (stdin)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--max-pages", type=int, default=3)
    args = parser.parse_args()

    if args.health:
        h = health()
        print(json.dumps(h, ensure_ascii=False, indent=2))
        return 0 if any(h.values()) else 1

    if args.query:
        try:
            payload = json.loads(args.query)
        except Exception:
            payload = json.loads(sys.stdin.read() or "{}")
        result = query(payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("found") else 2

    if args.list == "spp":
        all_items = []
        for name, path in SPP_SECTIONS:
            all_items.extend(fetch_spp_list(name, path, args.max_pages))
        print(json.dumps({"source": "spp.gov.cn", "count": len(all_items),
                          "items": all_items[:30]}, ensure_ascii=False, indent=2))
        return 0

    if args.list == "gov":
        all_items = []
        for name, path in GOV_SECTIONS:
            all_items.extend(fetch_gov_list(name, path, args.max_pages))
        print(json.dumps({"source": "gov.cn", "count": len(all_items),
                          "items": all_items[:30]}, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())