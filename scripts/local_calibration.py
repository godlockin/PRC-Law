#!/usr/bin/env python3
"""
local_calibration.py — 本地案件库胜诉率校准工具 (W7.1)

律师实战痛点:
  调解/诉讼策略默认基线胜诉率来自中国司法大数据 (公开统计, 与本地实际有偏差)
  → 需要把本地 100+ 个真实案件统计出来, 形成"本地案由胜诉率基线"

功能:
  - 扫描 cases.db (case_indexer 创建)
  - 解析 judgment_result 字段, 分类: 胜诉 / 部分胜诉 / 败诉 / 调解 / 撤诉 / 其他
  - 按 cause_of_action (案由) 统计胜诉率
  - 输出 JSON: {案由: {total, win_rate, sample_size, confidence}}
  - 自动生成 mediation_hint 可加载的校准文件

用法:
  # 扫描本地 cases.db
  python3 scripts/local_calibration.py --db cases.db --output calibration.json

  # 看摘要
  python3 scripts/local_calibration.py --db cases.db --report

  # 让 mediation_hint 加载校准数据
  python3 scripts/mediation_hint.py --amount 100 --case-type "合同纠纷" \
      --calibration calibration.json --output strategy.md

样本要求:
  - 每案由样本数 >= 10 才有统计意义
  - 样本数 5-9 标"低置信"
  - 样本数 < 5 标"不校准, 用规则基线"
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# === 结果分类 ===
WIN_KEYWORDS = ["胜诉", "支持", "全部支持", "判决被告", "被告承担", "被告支付"]
PARTIAL_KEYWORDS = ["部分支持", "部分胜诉", "酌情", "部分驳回"]
LOSS_KEYWORDS = ["败诉", "驳回", "驳回诉讼请求", "不予支持", "全部驳回", "不予立案"]
SETTLE_KEYWORDS = ["调解", "和解", "撤诉", "撤回起诉", "按撤诉处理"]
DISMISS_KEYWORDS = ["驳回起诉", "不予受理", "移送"]

# 默认基线胜诉率 (来自中国司法大数据, 兜底)
DEFAULT_BASE_RATES = {
    "合同纠纷": 0.62,
    "劳动争议": 0.78,
    "侵权": 0.55,
    "婚姻": 0.45,
    "借贷": 0.75,
    "房屋买卖": 0.58,
    "建设工程": 0.50,
    "知识产权": 0.45,
    "医疗损害": 0.40,
    "交通事故": 0.70,
}

# 最小样本数 (置信阈值)
MIN_SAMPLES_HIGH = 10  # 高置信
MIN_SAMPLES_LOW = 5    # 低置信


def classify_judgment(result_text: str) -> str:
    """判决结果分类 (基于关键词匹配)"""
    if not result_text:
        return "unknown"

    text = result_text.strip()

    # 优先级: 调解 > 部分 > 胜/败 > 驳回
    if any(kw in text for kw in SETTLE_KEYWORDS):
        return "settlement"
    if any(kw in text for kw in PARTIAL_KEYWORDS):
        return "partial_win"
    if any(kw in text for kw in LOSS_KEYWORDS):
        return "loss"
    if any(kw in text for kw in WIN_KEYWORDS):
        return "win"
    if any(kw in text for kw in DISMISS_KEYWORDS):
        return "dismiss"

    return "unknown"


def normalize_case_type(case_type: str) -> str:
    """案由归一化 (律师输入可能简写)"""
    if not case_type:
        return "unknown"
    mapping = {
        "合同": "合同纠纷",
        "借款": "借贷",
        "欠款": "借贷",
        "工伤": "劳动争议",
        "辞退": "劳动争议",
        "离婚": "婚姻",
        "遗产": "婚姻",
        "车祸": "交通事故",
        "人身损害": "侵权",
    }
    for k, v in mapping.items():
        if k in case_type:
            return v
    return case_type


def calibrate_from_db(db_path: Path) -> dict:
    """从 cases.db 统计校准数据

    Returns:
        {
            "案件总数": int,
            "生成时间": str,
            "cases.db": str,
            "by_case_type": {
                "合同纠纷": {
                    "total": int, "win": int, "partial": int,
                    "loss": int, "settlement": int, "dismiss": int,
                    "unknown": int, "win_rate": float (原告胜诉率, 含部分胜诉),
                    "sample_size": int, "confidence": "high"/"low"/"insufficient"
                }
            }
        }
    """
    if not db_path.exists():
        print(f"❌ cases.db 不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        # 拉取所有案件
        cur = conn.execute(
            "SELECT cause_of_action, judgment_result FROM cases"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("⚠ cases.db 无案件, 无法校准", file=sys.stderr)

    # 按案由聚合
    buckets: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "win": 0, "partial_win": 0,
        "loss": 0, "settlement": 0, "dismiss": 0, "unknown": 0,
    })

    for cause, result in rows:
        norm_cause = normalize_case_type(cause or "unknown")
        bucket = buckets[norm_cause]
        bucket["total"] += 1
        classification = classify_judgment(result or "")
        # 用 .get 兜底, 避免新增 classification 时 KeyError
        bucket[classification] = bucket.get(classification, 0) + 1

    # 计算胜诉率 + 置信度
    output = {
        "案件总数": len(rows),
        "生成时间": datetime.now().isoformat(timespec="seconds"),
        "cases.db": str(db_path),
        "by_case_type": {},
    }

    for cause, b in sorted(buckets.items(), key=lambda x: -x[1]["total"]):
        decided = b["total"] - b["unknown"] - b["settlement"] - b["dismiss"]
        if decided <= 0:
            win_rate = None
            confidence = "no_decision_data"
        else:
            # 原告胜诉率 = (胜 + 0.5 * 部分胜) / 已判决数
            win_rate = (b["win"] + 0.5 * b["partial_win"]) / decided
            win_rate = round(win_rate, 3)
            if b["total"] >= MIN_SAMPLES_HIGH:
                confidence = "high"
            elif b["total"] >= MIN_SAMPLES_LOW:
                confidence = "low"
            else:
                confidence = "insufficient"

        output["by_case_type"][cause] = {
            "total": b["total"],
            "win": b["win"],
            "partial_win": b["partial_win"],
            "loss": b["loss"],
            "settlement": b["settlement"],
            "dismiss": b["dismiss"],
            "unknown": b["unknown"],
            "win_rate": win_rate,
            "sample_size": b["total"],
            "confidence": confidence,
        }

    return output


def print_report(data: dict) -> None:
    """打印校准报告 (Markdown)"""
    md = f"""# 本地案件胜诉率校准报告

> ⚠️ **数据本地化警告**: 本报告基于 `{data['cases.db']}` 中的律师本地案件.
> 样本量 < 10 的案由建议仍用规则基线. 本校准仅供律师内部参考.

**生成时间**: {data['生成时间']}
**案件总数**: {data['案件总数']}

## 各案由胜诉率

| 案由 | 样本 | 胜 | 部分 | 败 | 调解/撤 | 原告胜诉率 | 置信 |
|------|------|-----|------|-----|---------|------------|------|
"""
    for cause, b in sorted(data["by_case_type"].items(), key=lambda x: -x[1]["sample_size"]):
        wr = f"{b['win_rate']:.1%}" if b["win_rate"] is not None else "—"
        md += f"| {cause} | {b['sample_size']} | {b['win']} | {b['partial_win']} | {b['loss']} | {b['settlement'] + b['dismiss']} | {wr} | {b['confidence']} |\n"

    md += """
## 解读

- **置信 high**: 样本数 ≥ 10, 本地基线**优先**于中国司法大数据
- **置信 low**: 样本数 5-9, 本地基线**辅助**参考
- **置信 insufficient**: 样本数 < 5, **用规则基线**

## 与规则基线对照

| 案由 | 本地 | 规则基线 | 偏差 |
|------|------|----------|------|
"""
    for cause, b in sorted(data["by_case_type"].items(), key=lambda x: -x[1]["sample_size"]):
        local = b["win_rate"]
        default = DEFAULT_BASE_RATES.get(cause)
        if local is not None and default is not None:
            diff = f"{(local - default) * 100:+.0f}%"
        else:
            diff = "—"
        local_str = f"{local:.1%}" if local is not None else "—"
        default_str = f"{default:.1%}" if default is not None else "—"
        md += f"| {cause} | {local_str} | {default_str} | {diff} |\n"

    md += """
> ⚠️ **律师审阅闸**: 本校准仅作策略参考, 不替代律师个案判断.
> 偏差 > 30% 的案由, 建议复核本地案件抽样, 确认是否因地区/法官/当事人结构差异.
"""
    print(md)


def main():
    parser = argparse.ArgumentParser(
        description="本地案件胜诉率校准 (W7.1)")
    parser.add_argument("--db", default="cases.db",
                        help="cases.db 路径 (case_indexer 创建)")
    parser.add_argument("-o", "--output",
                        help="输出 JSON 路径 (默认 stdout)")
    parser.add_argument("--report", action="store_true",
                        help="打印 Markdown 报告 (而不是 JSON)")
    args = parser.parse_args()

    data = calibrate_from_db(Path(args.db))

    if args.report:
        print_report(data)
    elif args.output:
        Path(args.output).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✅ 已生成校准: {args.output}", file=sys.stderr)
        print(f"   案件总数: {data['案件总数']}", file=sys.stderr)
        print(f"   覆盖案由: {len(data['by_case_type'])}", file=sys.stderr)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()