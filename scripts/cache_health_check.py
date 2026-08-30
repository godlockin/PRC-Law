#!/usr/bin/env python3
"""
cache_health_check.py — 法条缓存健康度监控

作用:
- 扫描 references/.cache/statutes.json + .freshness.yaml
- 计算每部法律的「覆盖率」「陈旧度」
- 输出到 ~/.prc-law/cache-health.json(供 cn-cache-health skill 展示)
- 当覆盖率 < 阈值时写 ~/.prc-law/cache-alert.json + 可选 stdout 横幅

设计:
- 后台运行友好(可被 SessionStart hook 调用)
- 失败容忍(任何异常只写 alert,不抛)
- 纯 stdlib(无 requests/yaml 依赖,降低使用门槛)
- **不是 cache hit rate** —— 而是用本地缓存**能覆盖多少法律查询**

用法:
  python3 scripts/cache_health_check.py           # 单次扫描, 输出到 ~/.prc-law/cache-health.json
  python3 scripts/cache_health_check.py --json    # 输出 JSON 到 stdout
  python3 scripts/cache_health_check.py --quiet   # 静默模式, 仅写文件
  python3 scripts/cache_health_check.py --no-alert  # 不生成 alert
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- 配置 ---
ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = ROOT / "references" / ".cache" / "statutes.json"
INDEX_FILE = ROOT / "references" / ".cache" / "index.json"
FRESHNESS_FILE = ROOT / "references" / "_freshness.yaml"

STATE_DIR = Path.home() / ".prc-law"
HEALTH_FILE = STATE_DIR / "cache-health.json"
ALERT_FILE = STATE_DIR / "cache-alert.json"

# 阈值(可被环境变量覆盖)
COVERAGE_WARN = float(os.environ.get("PRC_LAW_COVERAGE_WARN", "0.6"))  # <60% 预警
COVERAGE_FAIL = float(os.environ.get("PRC_LAW_COVERAGE_FAIL", "0.3"))  # <30% 强警
FRESHNESS_DAYS = int(os.environ.get("PRC_LAW_FRESHNESS_DAYS", "180"))  # 默认新鲜度窗口

# 元典/法宝 cost 估算(单次 API 调用的 ¥ 估值,粗略)
COST_PER_API_YUAN = float(os.environ.get("PRC_LAW_COST_PER_API", "0.05"))


def log(msg: str) -> None:
    """静默写日志(避免污染父进程 stdout)"""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with (STATE_DIR / "cache-health.log").open("a") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


def load_cache() -> dict:
    """加载 statutes.json, 容错"""
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception as e:
        log(f"parse cache failed: {e}")
        return {}


def load_freshness() -> dict:
    """
    解析 _freshness.yaml 中 laws.<name>.last_verified 字段
    不依赖 PyYAML — 用简易解析(文件结构稳定)
    """
    if not FRESHNESS_FILE.exists():
        return {}
    out: dict[str, str] = {}
    try:
        current_law: str | None = None
        for line in FRESHNESS_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            # laws:  → skip
            if stripped == "laws:":
                continue
            # `  civil-code:` → current_law
            if stripped.endswith(":") and not stripped.startswith("-"):
                key = stripped.rstrip(":")
                # 顶层 fields (defaults/laws) 跳过
                if key in ("defaults", "laws"):
                    continue
                # 缩进: top-level 字段是 `  name:`(2 spaces), laws.<name>: 是 `  name:`(2 spaces)
                # 我们已经只接受 `key:` 这种,所有都是 law names
                current_law = key
                out.setdefault(current_law, "")
            elif current_law and stripped.startswith("last_verified:"):
                val = stripped.split(":", 1)[1].strip()
                out[current_law] = val
    except Exception as e:
        log(f"parse freshness failed: {e}")
    return out


def parse_iso_date(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def compute_law_health(law_name: str, law_data: dict, freshness: dict) -> dict:
    """单部法律的健康度"""
    articles_cached = len(law_data.get("articles", {}))
    expected = law_data.get("expected_articles", 0)
    coverage = articles_cached / expected if expected else 0.0
    status = law_data.get("status", "unknown")
    pulled_at = law_data.get("pulled_at", "") or law_data.get("last_filled", "")
    pulled_dt = parse_iso_date(pulled_at[:10]) if pulled_at else None
    age_days = (datetime.now() - pulled_dt).days if pulled_dt else None

    # freshness 匹配: 中文 law_name → YAML slug 反向映射
    # YAML key 是 civil-code / criminal-law 等英文 slug,
    # 这里建立 15 部高频法律的精确映射
    LAST_VERIFIED_OVERRIDE = {
        "民法典": "civil-code",
        "刑法": "criminal-law",
        "公司法": "company-law",
        "民事诉讼法": "civil-procedure-law",
        "个人信息保护法": "personal-information-protection-law",
        "数据安全法": "data-security-law",
        "网络安全法": "cyber-security-law",
        "劳动合同法": "labor-contract-law",
        "行政处罚法": "administrative-penalty-law",
        "行政复议法": "administrative-reconsideration-law",
        "行政诉讼法": "administrative-litigation-law",
        "商标法": "trademark-law",
        "专利法": "patent-law",
        "著作权法": "copyright-law",
        "反不正当竞争法": "anti-unfair-competition-law",
        "消费者权益保护法": "consumer-protection-law",
    }
    slug = LAST_VERIFIED_OVERRIDE.get(law_name, "")
    last_verified = freshness.get(slug, "")
    freshness_age = None
    if last_verified:
        fv_dt = parse_iso_date(last_verified)
        if fv_dt:
            freshness_age = (datetime.now() - fv_dt).days

    # 健康等级
    if coverage >= 0.9 and (freshness_age is None or freshness_age <= FRESHNESS_DAYS):
        health = "good"
    elif coverage >= COVERAGE_WARN and (freshness_age is None or freshness_age <= FRESHNESS_DAYS * 2):
        health = "warn"
    else:
        health = "fail"

    return {
        "law": law_name,
        "articles_cached": articles_cached,
        "articles_expected": expected,
        "coverage": round(coverage, 3),
        "status": status,
        "pulled_at": pulled_at,
        "age_days": age_days,
        "freshness_verified": last_verified,
        "freshness_age_days": freshness_age,
        "health": health,
    }


def estimate_savings(health_report: list[dict]) -> dict:
    """估算缓存已省 API 调用 + 节省金额"""
    saved_calls = sum(h["articles_cached"] for h in health_report)
    saved_yuan = round(saved_calls * COST_PER_API_YUAN, 2)
    missing_calls = sum(max(0, h["articles_expected"] - h["articles_cached"]) for h in health_report)
    return {
        "saved_api_calls": saved_calls,
        "saved_yuan": saved_yuan,
        "missing_api_calls": missing_calls,
        "estimated_fill_cost_yuan": round(missing_calls * COST_PER_API_YUAN, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="输出 JSON 到 stdout")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    parser.add_argument("--no-alert", action="store_true", help="不生成 alert")
    args = parser.parse_args()

    cache = load_cache()
    freshness = load_freshness()

    if not cache:
        report = {
            "ts": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "overall_health": "fail",
            "reason": "no cache file",
            "laws": [],
        }
        if not args.quiet:
            log("cache file not found")
    else:
        per_law = [compute_law_health(name, data, freshness) for name, data in cache.items()]
        # 总体健康度
        if not per_law:
            overall = "fail"
        else:
            good_n = sum(1 for h in per_law if h["health"] == "good")
            overall = "good" if good_n == len(per_law) else (
                "warn" if good_n >= len(per_law) * 0.7 else "fail"
            )
        savings = estimate_savings(per_law)
        report = {
            "ts": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "overall_health": overall,
            "total_laws": len(per_law),
            "good_count": sum(1 for h in per_law if h["health"] == "good"),
            "warn_count": sum(1 for h in per_law if h["health"] == "warn"),
            "fail_count": sum(1 for h in per_law if h["health"] == "fail"),
            "savings": savings,
            "thresholds": {
                "coverage_warn": COVERAGE_WARN,
                "coverage_fail": COVERAGE_FAIL,
                "freshness_days": FRESHNESS_DAYS,
            },
            "laws": sorted(per_law, key=lambda x: (x["health"] != "fail", x["health"] != "warn", x["law"])),
        }

    # 写健康度文件
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = HEALTH_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        tmp.replace(HEALTH_FILE)
    except Exception as e:
        log(f"write health failed: {e}")
        return 1

    # alert 逻辑
    if not args.no_alert:
        alerts = []
        for h in report.get("laws", []):
            reasons = []
            if h["health"] == "fail":
                reasons.append(f"覆盖率 {h['coverage']*100:.0f}% < {COVERAGE_FAIL*100:.0f}%")
            elif h["health"] == "warn":
                reasons.append(f"覆盖率 {h['coverage']*100:.0f}% < {COVERAGE_WARN*100:.0f}%")
            if h.get("freshness_age_days") and h["freshness_age_days"] > FRESHNESS_DAYS:
                reasons.append(f"新鲜度 {h['freshness_age_days']}天 > {FRESHNESS_DAYS}天")
            if reasons:
                alerts.append({
                    "law": h["law"],
                    "health": h["health"],
                    "reasons": reasons,
                })
        if alerts:
            alert_payload = {
                "ts": report["ts"],
                "alert_count": len(alerts),
                "alerts": alerts,
            }
            try:
                tmp = ALERT_FILE.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(alert_payload, ensure_ascii=False, indent=2))
                tmp.replace(ALERT_FILE)
            except Exception as e:
                log(f"write alert failed: {e}")

    # 输出
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.quiet:
        # 简明横幅
        savings = report.get("savings", {})
        print(f"📊 PRC-Law cache health: {report.get('overall_health','?').upper()}")
        print(f"   laws: {report.get('good_count',0)} good / {report.get('warn_count',0)} warn / {report.get('fail_count',0)} fail")
        if savings:
            print(f"   saved ¥{savings.get('saved_yuan',0)} ({savings.get('saved_api_calls',0)} API calls cached)")
            print(f"   fill missing: ¥{savings.get('estimated_fill_cost_yuan',0)} ({savings.get('missing_api_calls',0)} calls)")
        alerts_path = ALERT_FILE
        if alerts_path.exists():
            try:
                ac = json.loads(alerts_path.read_text())
                if ac.get("alert_count", 0) > 0:
                    print(f"   ⚠ {ac['alert_count']} alerts → see {ALERT_FILE}")
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"unexpected: {e}")
        sys.exit(1)