#!/usr/bin/env python3
"""
judge_pattern.py — 法官/法院裁判倾向分析

基于元典真实案例数据，对法官/法院做画像。
所有数据来源于元典，不引入 mock 数据。

已知数据限制：元典案例库不直接提供法官姓名，
主要画像基于法院层级和地域。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

import urllib.request
import urllib.error

API_KEY = os.environ.get("YUANDIAN_API_KEY", "")
BASE_URL = "https://open.chineselaw.com"

if not API_KEY:
    print("ERROR: YUANDIAN_API_KEY not set")
    sys.exit(1)


def call_yuandian(endpoint: str, payload: dict) -> dict:
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def fetch_cases_by_court(court_name: str, cause: str, max_pages: int = 3) -> list:
    """按法院+案由检索案例"""
    cases = []
    for page in range(1, max_pages + 1):
        result = call_yuandian("/open/rh_ptal_search", {
            "keyword": cause,
            "jbdw": [court_name],
            "top_k": 30,
        })
        if "data" in result:
            cases.extend(result.get("data", {}).get("lst", []))
        if len(result.get("data", {}).get("lst", [])) < 30:
            break
        time.sleep(0.3)
    return cases


def analyze_court_pattern(cases: list) -> dict:
    """分析法院裁判倾向"""
    if not cases:
        return {"error": "无案例数据"}

    # 法院层级
    court_levels = Counter(c.get("cj", "?") for c in cases)

    # 程序分布
    procedures = Counter(c.get("spcx", "?") for c in cases)

    # 案由分布
    causes = Counter()
    for c in cases:
        for ay in c.get("ay", []):
            causes[ay] += 1

    # 时间分布（按年份）
    years = Counter()
    for c in cases:
        cprq = c.get("cprq", "")
        year = cprq[:4] if cprq else "?"
        years[year] += 1

    # 裁判类型
    types = Counter(c.get("type", "?") for c in cases)

    return {
        "total": len(cases),
        "court_levels": dict(court_levels.most_common(5)),
        "procedures": dict(procedures.most_common(5)),
        "top_causes": dict(causes.most_common(5)),
        "year_distribution": dict(sorted(years.items())),
        "judgment_types": dict(types.most_common(5)),
    }


def generate_court_report(court_name: str, cause: str, analysis: dict) -> str:
    """生成法院画像报告"""
    if "error" in analysis:
        return f"❌ {analysis['error']}"

    report = f"""# 法院画像报告: {court_name}

**分析案由**: {cause}
**样本量**: {analysis['total']} 件
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**数据来源**: 元典案例库（基于中国裁判文书网）

## 法院层级分布

| 层级 | 案件数 | 占比 |
|------|--------|------|
"""
    total = analysis["total"]
    for level, count in analysis["court_levels"].items():
        pct = count / total * 100
        report += f"| {level} | {count} | {pct:.0f}% |\n"

    report += f"""
## 程序分布

| 程序 | 案件数 |
|------|--------|
"""
    for proc, count in analysis["procedures"].items():
        report += f"| {proc} | {count} |\n"

    report += f"""
## 主要案由

| 案由 | 案件数 |
|------|--------|
"""
    for cause_, count in analysis["top_causes"].items():
        report += f"| {cause_} | {count} |\n"

    report += f"""
## 裁判类型分布

| 类型 | 案件数 |
|------|--------|
"""
    for jtype, count in analysis["judgment_types"].items():
        report += f"| {jtype} | {count} |\n"

    report += """
## 数据限制说明

- 元典案例库不直接提供承办法官姓名
- 本画像基于**法院层级 + 程序 + 案由 + 时间分布**统计
- 如需精确到法官级别，需查询中国裁判文书网原文（部分公开）
- 所有数据均为元典 API 真实返回，未引入 mock 数据

> ⚠️ **律师审阅闸**: 本报告为基于公开裁判文书的统计分析，不构成对承办法官的具体评价。统计结果仅供诉讼策略参考。最终策略由执业律师判断。
"""
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="法院画像分析")
    parser.add_argument("--court", required=True, help="法院名称")
    parser.add_argument("--cause", default="合同纠纷", help="案由")
    parser.add_argument("--max-pages", type=int, default=2, help="最大检索页数")
    parser.add_argument("--output", "-o", default="COURT-REPORT.md", help="报告输出")
    args = parser.parse_args()

    print(f"检索: {args.court} - {args.cause}")
    print("=" * 60)

    cases = fetch_cases_by_court(args.court, args.cause, args.max_pages)
    print(f"获取 {len(cases)} 条案例")

    analysis = analyze_court_pattern(cases)
    report = generate_court_report(args.court, args.cause, analysis)

    output_path = Path(__file__).parent.parent / "docs" / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {output_path}")


if __name__ == "__main__":
    main()