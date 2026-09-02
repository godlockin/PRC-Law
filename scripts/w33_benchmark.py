#!/usr/bin/env python3
"""W33 — 真双源双盲 benchmark (5 个最高法指导案例)

思路:
- 拿 case 文件里的"相关法条"(人工标注的真值)
- pkulaw + prc-law-data 双源检索
- 计算:
  - 召回率 (recall): 真值法条里被两个源覆盖的比例
  - 一致率: 两源都覆盖的占比
  - 元数据正确率: IssueDate/Status 跟真值是否一致 (目前无人工真值,先看两源是否一致)

不引入参考项目数据 (CLAUDE.md 借鉴合规): 案例来自 data/cases/supreme-court/ 真实 JSON。
"""
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import retrieval_router as rr

CASES_DIR = ROOT / "data" / "cases" / "supreme-court"
AUDIT_OUT = ROOT / "data" / "audit" / "w33_benchmark.json"


def parse_articles_from_section(section_text: str) -> list[tuple[str, int]]:
    """从"相关法条"section 提取 (法名, 条号) 列表

    例: "《中华人民共和国物权法》第15条（注：...民法典第215条）" → [("物权法", 15), ("民法典", 215)]
    """
    results = []
    # 模式 1: 《法名》第X条
    pattern1 = re.compile(r'《([^》]+)》第([一二三四五六七八九十百零\d]+)条')
    for m in pattern1.finditer(section_text):
        name = m.group(1)
        num_cn = m.group(2)
        # 转数字
        num = _cn_to_int(num_cn)
        if num is not None:
            results.append((name, num))
    # 模式 2: 注里的 "民法典第215条" 也算 (说明现行有效)
    pattern2 = re.compile(r'《([^》]+)》第(\d+)条')
    for m in pattern2.finditer(section_text):
        name = m.group(1)
        num = int(m.group(2))
        # 避免重复
        if (name, num) not in results:
            results.append((name, num))
    return results


def _cn_to_int(cn: str) -> Optional[int]:
    """中文数字 → 整数"""
    DIGITS = {"零":0,"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
    if cn.isdigit():
        return int(cn)
    try:
        if "百" in cn:
            parts = cn.split("百")
            hundreds = DIGITS.get(parts[0], 0) if parts[0] else 0
            rest = parts[1] if len(parts) > 1 else ""
            tens_digit = DIGITS.get(rest[0], 0) if rest and rest[0] in DIGITS else 0
            ones = DIGITS.get(rest[-1], 0) if rest and rest[-1] in DIGITS else 0
            return hundreds * 100 + tens_digit * 10 + ones
        if "十" in cn:
            parts = cn.split("十")
            tens = DIGITS.get(parts[0], 1) if parts[0] else 1
            rest = parts[1] if len(parts) > 1 else ""
            ones = DIGITS.get(rest, 0) if rest in DIGITS else 0
            return tens * 10 + ones
        return DIGITS.get(cn)
    except Exception:
        return None


def extract_cited_articles(case: dict) -> list[tuple[str, int]]:
    """从 case JSON 提取所有引用法条"""
    cited = []
    for sec in case.get("data", [{}])[0].get("section", []):
        if sec.get("name") in ("相关法条", "裁判要点"):
            cited.extend(parse_articles_from_section(sec.get("value", "")))
    return cited


def test_article_lookup(name: str, article: int) -> dict:
    """单条法条双源检索"""
    # pkulaw
    import os
    os.environ.pop("YUANDIAN_API_KEY", None)
    pkulaw_hit = False
    pkulaw_status = "unknown"
    try:
        r = rr.try_yuandian_pkulaw(name, article, None)
        if r:
            content = str(r.get("content", ""))
            if "Authorization Required" in content or "90001" in content:
                pkulaw_status = "credit_exhausted"
            elif r.get("pkulaw_url"):
                pkulaw_hit = True
                pkulaw_status = "ok"
            else:
                pkulaw_status = "no_url"
    except Exception as e:
        pkulaw_status = f"error: {e}"

    # prc-law-data
    prc_hit = False
    try:
        from dataset_client import DatasetClient
        client = DatasetClient()
        if client.is_available():
            hit = client.lookup(name, article)
            prc_hit = bool(hit)
    except Exception:
        pass

    return {
        "law": name,
        "article": article,
        "pkulaw_hit": pkulaw_hit,
        "pkulaw_status": pkulaw_status,
        "prc_law_data_hit": prc_hit,
        "consistent": pkulaw_hit and prc_hit,
    }


def main() -> None:
    cases = sorted(CASES_DIR.glob("*.json"))
    if not cases:
        print(f"❌ 没找到案例: {CASES_DIR}")
        sys.exit(1)

    print(f"=== W33 双源双盲 benchmark ===")
    print(f"案例数: {len(cases)}\n")

    all_results = []
    summary = {
        "cases_total": 0,
        "articles_total": 0,
        "consistent_count": 0,
        "pkulaw_only_count": 0,
        "prc_law_data_only_count": 0,
        "all_miss_count": 0,
    }

    for case_file in cases:
        case = json.loads(case_file.read_text(encoding="utf-8"))
        cited = extract_cited_articles(case)
        if not cited:
            continue

        title = case.get("data", [{}])[0].get("title", case_file.stem)
        print(f"[{case_file.name}] {title[:40]}")
        print(f"  引用法条: {len(cited)} 条")

        for name, article in cited:
            res = test_article_lookup(name, article)
            summary["articles_total"] += 1
            status = res.get("pkulaw_status", "?")
            if res["consistent"]:
                summary["consistent_count"] += 1
                marker = "✅ 双源"
            elif res["pkulaw_hit"]:
                summary["pkulaw_only_count"] += 1
                marker = "⚠ pkulaw"
            elif res["prc_law_data_hit"]:
                if status == "credit_exhausted":
                    summary["prc_law_data_only_count"] += 1
                    marker = "⚠ prc (pkulaw积分用尽)"
                else:
                    summary["prc_law_data_only_count"] += 1
                    marker = "⚠ prc"
            else:
                summary["all_miss_count"] += 1
                marker = "❌"
            print(f"    {marker} 《{name}》第{article}条  [pkulaw={status}]")
            all_results.append({"case": case_file.name, **res})

        summary["cases_total"] += 1
        print()

    # 报告
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": {"cases": summary["cases_total"], "articles": summary["articles_total"]},
        "summary": summary,
        "results": all_results,
    }
    AUDIT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 双盲 benchmark 结果 ===")
    print(f"案例: {summary['cases_total']}, 引用法条: {summary['articles_total']}")
    print(f"  双源一致: {summary['consistent_count']}")
    print(f"  仅 pkulaw: {summary['pkulaw_only_count']}")
    print(f"  仅 prc-law-data: {summary['prc_law_data_only_count']}")
    print(f"  都未命中: {summary['all_miss_count']}")
    if summary["articles_total"]:
        recall = summary["consistent_count"] / summary["articles_total"] * 100
        print(f"  双源召回率: {recall:.1f}%")
    print(f"\n报告: {AUDIT_OUT}")


if __name__ == "__main__":
    main()