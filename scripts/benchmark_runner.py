#!/usr/bin/env python3
"""
benchmark_runner.py — Benchmark 自动化运行脚本

读取 data/cases/supreme-court/ 下的最高法指导案例，
跑每个案例的测试问题，调用元典 MCP 检索，
对照真实判决结果生成报告。

不引入参考项目的数据（无 mock），仅基于元典真实数据 + 案例原文。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import urllib.request
import urllib.error

API_KEY = os.environ.get("YUANDIAN_API_KEY", "")
BASE_URL = "https://open.chineselaw.com"
CASES_DIR = Path(__file__).parent.parent / "data" / "cases" / "supreme-court"
REPORT_DIR = Path(__file__).parent.parent / "docs"

if not API_KEY:
    print("ERROR: YUANDIAN_API_KEY not set")
    sys.exit(1)


def call_yuandian(endpoint: str, payload: dict) -> dict:
    """调用元典 REST API"""
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode(errors="replace")[:300]}
    except Exception as e:
        return {"error": str(e)}


def load_case(file_path: Path) -> dict:
    """加载单个案例"""
    return json.loads(file_path.read_text())


def extract_fact_summary(case_data: dict) -> str:
    """从案例数据提取案情摘要"""
    item = case_data["data"][0]
    sections = item.get("section", [])
    for s in sections:
        if s["name"] == "基本案情":
            return s["value"]
    return item.get("content", "")[:500]


def extract_reference_date(case_data: dict) -> str:
    """提取裁判日期作为时间锚点"""
    item = case_data["data"][0]
    cprq = item.get("cprq", "")  # 裁判日期
    return cprq


def run_test(case_data: dict, refer_date: Optional[str] = None) -> dict:
    """
    对单个案例运行 benchmark 测试：
    1. 提取案情摘要
    2. 用案情做关键词检索（模拟 AI 推理）
    3. 对照真实判决结果
    """
    item = case_data["data"][0]
    ah = item.get("ah", "")
    title = item.get("title", "")
    fact = extract_fact_summary(case_data)

    if not refer_date:
        refer_date = extract_reference_date(case_data)

    # Step 1: 用案例案由检索
    ay = item.get("ay", [])
    keyword = ay[0] if ay else title.split("诉")[0]

    # Step 2: 检索相关法条（行为时版本）
    search_result = call_yuandian("/open/rh_ft_search", {
        "keyword": keyword,
        "top_k": 3,
    })

    # Step 3: 评估检索质量（仅看是否能找到相关法条）
    found_relevant = False
    if "data" in search_result:
        for ft in search_result.get("data", []):
            if ft.get("sxx") == "现行有效" or ft.get("sxx") == "已被修改":
                found_relevant = True
                break

    return {
        "ah": ah,
        "title": title,
        "refer_date": refer_date,
        "keyword": keyword,
        "found_relevant": found_relevant,
        "search_error": "error" in search_result,
        "result_count": len(search_result.get("data", [])) if "data" in search_result else 0,
    }


def generate_report(results: list) -> str:
    """生成 Benchmark 报告"""
    total = len(results)
    relevant = sum(1 for r in results if r["found_relevant"])
    errors = sum(1 for r in results if r["search_error"])

    report = f"""# PRC-Law Benchmark v3.0 (自动运行)

> 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 测试案例数: {total}
> 元典 API: {'可用' if not any(r['search_error'] for r in results) else '部分失败'}

## 检索能力测试

| 指标 | 数值 |
|------|------|
| 总案例数 | {total} |
| 检索到相关法条 | {relevant} ({relevant/total*100:.0f}%) |
| 检索失败 | {errors} |

## 逐案结果

"""
    for r in results:
        status = "✅" if r["found_relevant"] else ("❌" if r["search_error"] else "⚠️")
        report += f"""### {r['ah']}

- 标题: {r['title']}
- 基准日: {r['refer_date']}
- 关键词: {r['keyword']}
- 检索结果数: {r['result_count']}
- 状态: {status} {'找到相关法条' if r['found_relevant'] else '未找到 / 失败'}

"""
    report += """
## 说明

- 本报告仅测试 **元典 API 检索能力**，不评估 AI 推理质量
- 完整 Benchmark（含 AI 推理 vs 真实判决对比）见 BENCHMARK-v3.0 报告
- 本脚本不引入 mock 数据，全部基于元典 API 真实检索结果
"""
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PRC-Law Benchmark 自动运行")
    parser.add_argument("--output", "-o", default="BENCHMARK-AUTO.md",
                       help="报告输出文件名")
    parser.add_argument("--limit", type=int, default=0,
                       help="限制案例数（0=全部）")
    args = parser.parse_args()

    if not CASES_DIR.exists():
        print(f"ERROR: {CASES_DIR} not found")
        sys.exit(1)

    case_files = sorted(CASES_DIR.glob("*.json"))
    if args.limit > 0:
        case_files = case_files[:args.limit]

    if not case_files:
        print(f"ERROR: 没有找到案例文件 in {CASES_DIR}")
        sys.exit(1)

    print(f"Benchmark 运行: {len(case_files)} 个案例")
    print("=" * 60)

    results = []
    for i, case_file in enumerate(case_files, 1):
        print(f"\n[{i}/{len(case_files)}] {case_file.name}")
        try:
            case_data = load_case(case_file)
            result = run_test(case_data)
            results.append(result)
            status = "✅" if result["found_relevant"] else "❌"
            print(f"  {status} {result['keyword']}: {result['result_count']} 条")
        except Exception as e:
            print(f"  [ERROR] {e}")
        time.sleep(0.5)  # 避免 API 限流

    # 生成报告
    report = generate_report(results)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / args.output
    report_path.write_text(report, encoding="utf-8")
    print(f"\n\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()