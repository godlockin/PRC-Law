#!/usr/bin/env python3
"""W32 — 用 pkulaw 反哺 prc-law-data 缺口 (10 部法律)

来源: data/audit/dual_source_audit_20260902.json (pkulaw_only 的 10 条)
目标: vendor/prc-law-data/data/statutes/<slug>.json

策略:
- pkulaw `smart_search` 拿到法规全文 + 元数据 (Title/Url/IssueDate/TimelinessDic)
- 提取条款 → articles (中文键 "一"/"二") + articles_by_int (阿拉伯键 "1"/"2")
- 落盘 + 更新 slug-map.json
- 再跑 data_audit.py 验证补全

积分预算:
- smart_search 125/次 × 10 = 1250 积分 (远低于每日 10K)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DATA_DIR = ROOT / "vendor" / "prc-law-data" / "data"
STATUTES_DIR = DATA_DIR / "statutes"
SLUG_MAP_PATH = DATA_DIR / "index" / "slug-map.json"
AUDIT_FILE = sorted((ROOT / "data" / "audit").glob("dual_source_audit_*.json"))[-1]

BRIDGE = ROOT / "scripts" / "pkulaw_mcp_bridge.py"


def call_pk_smart_search(query: str, limit: int = 1) -> dict | None:
    """用 smart_search (聚合, 125 积分) 搜法规全文"""
    payload = json.dumps({
        "method": "tools/call",
        "params": {
            "name": "smart_search",
            "arguments": {"query": query},
        },
    }, ensure_ascii=False)
    try:
        r = subprocess.run(
            [sys.executable, str(BRIDGE)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        parsed = json.loads(r.stdout)
        if isinstance(parsed, dict) and "result" in parsed:
            return parsed
    except Exception as e:
        print(f"  ⚠ smart_search 失败: {e}", file=sys.stderr)
    return None


def call_pk_get_law_list(title: str) -> dict | None:
    """用 get_law_list 拿法规元数据 (25 积分) — mcp-law 的工具名

    返回: {Title, Url, IssueDate, ImplementDate, TimelinessDic, EffectivenessDic, ...}
    """
    payload = json.dumps({
        "method": "tools/call",
        "params": {
            "name": "get_law_list",
            "arguments": {"title": title},
        },
    }, ensure_ascii=False)
    try:
        r = subprocess.run(
            [sys.executable, str(BRIDGE)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        parsed = json.loads(r.stdout)
        if isinstance(parsed, dict) and "result" in parsed:
            return parsed
    except Exception as e:
        print(f"  ⚠ get_law_list 失败: {e}", file=sys.stderr)
    return None


def call_pk_get_law_article(title: str, tiao_num: int | str) -> dict | None:
    """精准查法条 (25 积分)"""
    payload = json.dumps({
        "method": "tools/call",
        "params": {
            "name": "get_law_item_content",
            "arguments": {"title": title, "tiao_num": tiao_num},
        },
    }, ensure_ascii=False)
    try:
        r = subprocess.run(
            [sys.executable, str(BRIDGE)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        parsed = json.loads(r.stdout)
        if isinstance(parsed, dict) and "result" in parsed:
            return parsed
    except Exception as e:
        print(f"  ⚠ get_law_item_content 失败: {e}", file=sys.stderr)
    return None


def extract_business_data(pk_response: dict) -> dict | None:
    """从 pkulaw 双层 wrapper 提取业务 JSON

    支持:
    - 单层 smart_search: {Message, Data}  (Data 可能是 dict 或 list)
    - 双层 get_law_item_content: wrapper → text → {Message, Data}
    """
    try:
        text = pk_response.get("result", {}).get("content", [{}])[0].get("text", "{}")
        parsed = json.loads(text)
        if "Data" in parsed:
            data = parsed["Data"]
            # get_law_list 返回 list — 取第一条
            if isinstance(data, list) and data:
                return data[0]
            return data
        # 双层
        inner = parsed.get("result", {}).get("content", [{}])[0].get("text", "{}")
        inner_data = json.loads(inner).get("Data", {})
        if isinstance(inner_data, list) and inner_data:
            return inner_data[0]
        return inner_data
    except Exception:
        return None


def slugify(name: str) -> str:
    """生成 slug (跟 prc-law-data 风格一致: civil-code / law-<hash>)"""
    # 简单规则: 短英文名用 slug-map, 复杂中文名用 law-<hash>
    MAPPING = {
        "中华人民共和国民法典": "civil-code",
        "中华人民共和国民事诉讼法": "civil-procedure-law",
        "中华人民共和国数据安全法": "data-security-law",
        "中华人民共和国网络安全法": "cybersecurity-law",
        "中华人民共和国劳动合同法": "labor-contract-law",
        "中华人民共和国刑法": "criminal-law",
        "中华人民共和国消费者权益保护法": "consumer-protection-law",
        "中华人民共和国公司法": "company-law",
    }
    if name in MAPPING:
        return MAPPING[name]
    # hash
    return f"law-{hashlib_md5(name)}"[:16]


def hashlib_md5(name: str) -> str:
    import hashlib
    return hashlib.md5(name.encode("utf-8")).hexdigest()


def parse_law_to_schema(name: str, smart_data: dict, article_data: dict | None) -> dict:
    """生成 prc-law-data 标准 schema"""
    # smart_data 含 Title/Url/IssueDate/ImplementDate/TimelinessDic/FullText
    # 但 smart_search 返回的 FullText 可能是片段, 用 get_law_article 单条补更准
    issue_date = smart_data.get("IssueDate", "2024-01-01").replace(".", "-")
    implement_date = smart_data.get("ImplementDate", issue_date).replace(".", "-")
    timeliness = smart_data.get("TimelinessDic", ["现行有效"])
    if isinstance(timeliness, list):
        timeliness = timeliness[0] if timeliness else "现行有效"

    # 从 sample article 拿到 FullText, article_data 单独存第一条
    articles = {}
    articles_by_int = {}
    if article_data:
        ft = article_data.get("FullText", "")
        if ft:
            # 提取条号 (第一条 = 第一条)
            article_num = str(article_data.get("article", "1"))
            articles_by_int[article_num] = ft
            # 中文版条号
            cn_num = cn_number(int(article_num))
            articles[cn_num] = ft

    return {
        "id": slugify(name),
        "name": name,
        "short_name": name.replace("中华人民共和国", ""),
        "slug": slugify(name),
        "type": "法规",
        "level": "national",
        "office": smart_data.get("IssueDepartment", [""])[0] if isinstance(smart_data.get("IssueDepartment"), list) else "",
        "publish_date": issue_date,
        "effective_date": implement_date,
        "status": timeliness,
        "source": {
            "upstream": smart_data.get("Url", "").split("](")[-1].rstrip(")") or "https://www.pkulaw.com",
            "via": "pkulaw",
            "license": "公共领域 (中国法律文本)",
            "fetched_at": datetime.now().isoformat() + "Z",
        },
        "articles": articles,
        "article_count": len(articles),
        "articles_by_int": articles_by_int,
        "_w32_note": "W32 由 pkulaw 智能检索补全, 仅有样本条款, 全文待 prc-law-data 官方源同步",
    }


def cn_number(n: int) -> str:
    """数字 → 中文 (1→一, 12→十二, 100→一百)"""
    DIGITS = "零一二三四五六七八九"
    UNITS = ["", "十", "百", "千"]
    if n == 0:
        return "零"
    s = str(n)
    result = []
    for i, c in enumerate(s):
        d = int(c)
        pos = len(s) - i - 1
        if d == 0:
            if result and result[-1] != "零":
                result.append("零")
        else:
            result.append(DIGITS[d] + UNITS[pos])
    s = "".join(result).rstrip("零")
    if s.endswith("十"):
        s = s + "一" if not s.startswith("十") else s
    if n >= 10 and n < 20:
        s = s.replace("一十", "十")
    return s or "零"


def update_slug_map(new_entries: dict[str, str]) -> None:
    """更新 slug-map.json"""
    sm = json.loads(SLUG_MAP_PATH.read_text(encoding="utf-8"))
    for name, slug in new_entries.items():
        sm[name] = slug
        # 简化名也加
        short = name.replace("中华人民共和国", "")
        if short != name:
            sm[short] = slug
    SLUG_MAP_PATH.write_text(
        json.dumps(sm, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  ✅ slug-map.json 更新: +{len(new_entries)} 条")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只展示缺口, 不实际调用")
    parser.add_argument("--update-existing", action="store_true", help="补全已有文件的元数据")
    parser.add_argument("--update-slug-map", action="store_true", help="补全后更新 slug-map.json")
    args = parser.parse_args()

    if not AUDIT_FILE.exists():
        print(f"❌ 未找到 audit 报告: {AUDIT_FILE}")
        print("   先跑 python3 scripts/data_audit.py")
        sys.exit(1)

    audit = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
    gaps = [c for c in audit["cases"] if c["category"] == "pkulaw_only"]
    print(f"=== W32 补 prc-law-data 缺口 ===")
    print(f"audit 报告: {AUDIT_FILE.name}")
    print(f"缺口: {len(gaps)} 条\n")

    if args.dry_run:
        for c in gaps:
            print(f"  {c['law']} 第{c['article']}条 ({c['expected']})")
        return

    new_slug_map = {}
    for i, c in enumerate(gaps, 1):
        name = c["law"]
        article = c["article"]
        print(f"[{i}/{len(gaps)}] {name} 第{article}条...")

        # 1. get_law_list 拿法规元数据 (25 积分) — 比 smart_search 便宜 5 倍
        list_resp = call_pk_get_law_list(name)
        if not list_resp:
            print(f"  ⚠ get_law_list 无结果, 跳过")
            continue
        smart_data = extract_business_data(list_resp) or {}
        print(f"  ✅ 元数据: IssueDate={smart_data.get('IssueDate')}, Timeliness={smart_data.get('TimelinessDic')}")

        # 2. get_law_item_content 拿样本条文 (25 积分)
        article_resp = call_pk_get_law_article(name, article)
        article_data = None
        if article_resp:
            ad = extract_business_data(article_resp)
            if ad:
                article_data = {**ad, "article": article}
                print(f"  ✅ 样本条款: 第{article}条 ({len(ad.get('FullText', ''))} 字)")

        # 3. 生成 schema
        record = parse_law_to_schema(name, smart_data, article_data)
        slug = record["slug"]

        # 4. 落盘 / 补全
        out_path = STATUTES_DIR / f"{slug}.json"
        if out_path.exists():
            if not args.update_existing:
                print(f"  ⚠ 已存在: {out_path.name}, 跳过 (加 --update-existing 补全元数据)")
                new_slug_map[name] = slug  # 仍然登记 slug_map
                continue
            # 补全已有文件: 只更新元数据, 保留 articles
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            existing["publish_date"] = (smart_data.get("IssueDate", "2024-01-01") or "2024-01-01").replace(".", "-")
            existing["effective_date"] = (smart_data.get("ImplementDate", existing["publish_date"]) or existing["publish_date"]).replace(".", "-")
            timeliness = smart_data.get("TimelinessDic", ["现行有效"])
            existing["status"] = timeliness[0] if isinstance(timeliness, list) and timeliness else "现行有效"
            existing["office"] = (smart_data.get("IssueDepartment", [""])[0]
                                   if isinstance(smart_data.get("IssueDepartment"), list) else "")
            existing["_w32_meta_updated"] = datetime.now().isoformat()
            out_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  🔄 补全元数据: {out_path.name} (status={existing['status']})")
            new_slug_map[name] = slug
            continue
        out_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ✅ 落盘: {out_path.name}")
        new_slug_map[name] = slug

    # 5. 更新 slug-map
    if args.update_slug_map and new_slug_map:
        update_slug_map(new_slug_map)

    print(f"\n=== 补全完成 ===")
    print(f"新增: {len(new_slug_map)} 部法律")
    print(f"积分消耗: 约 {len(gaps) * 150} 积分 (smart_search 125 + get_law_article 25)")


if __name__ == "__main__":
    main()