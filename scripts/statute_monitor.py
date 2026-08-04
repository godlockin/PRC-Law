#!/usr/bin/env python3
"""
statute_monitor.py — 法条修订自动监控

定期扫描 watchlist 中的法条，检测状态变化，触发预警和工作流。

与 cn-statute-watchdog SKILL 配套使用。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error

# --- 配置 ---
API_KEY = os.environ.get("YUANDIAN_API_KEY", "")
BASE_URL = "https://open.chineselaw.com"
WATCHLIST_FILE = Path.home() / ".prc-law" / "statute-watchlist.json"
LOG_FILE = Path.home() / ".prc-law" / "statute-monitor.log"

if not API_KEY:
    print("ERROR: YUANDIAN_API_KEY not set")
    print("Set: export YUANDIAN_API_KEY=sk_xxx")
    sys.exit(1)

WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)


# --- 数据模型 ---
class StatuteStatus:
    CURRENT = "现行有效"
    AMENDED = "已被修改"
    EXPIRED = "失效"
    PARTIAL = "部分失效"


def load_watchlist() -> list:
    """加载监听清单"""
    if not WATCHLIST_FILE.exists():
        return []
    return json.loads(WATCHLIST_FILE.read_text())


def save_watchlist(watchlist: list):
    """保存监听清单"""
    WATCHLIST_FILE.write_text(
        json.dumps(watchlist, ensure_ascii=False, indent=2)
    )


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
        return {"error": f"HTTP {e.code}", "body": e.read().decode(errors="replace")[:500]}
    except Exception as e:
        return {"error": str(e)}


def check_ft_detail(fgmc: str, ftnum: str, refer_date: Optional[str] = None) -> dict:
    """检查法条当前状态"""
    payload = {"fgmc": fgmc, "ftnum": ftnum}
    if refer_date:
        payload["refer_date"] = refer_date
    return call_yuandian("/open/rh_ft_detail", payload)


def detect_change(old_status: str, new_status: str) -> Optional[str]:
    """检测状态变化并返回预警级别"""
    transitions = {
        (StatuteStatus.CURRENT, StatuteStatus.AMENDED): "warning",  # 被修改
        (StatuteStatus.CURRENT, StatuteStatus.EXPIRED): "critical",  # 失效
        (StatuteStatus.CURRENT, StatuteStatus.PARTIAL): "warning",
        (StatuteStatus.AMENDED, StatuteStatus.EXPIRED): "critical",
        (StatuteStatus.AMENDED, StatuteStatus.PARTIAL): "warning",
        (StatuteStatus.EXPIRED, StatuteStatus.CURRENT): "notice",  # 恢复
        (StatuteStatus.PARTIAL, StatuteStatus.CURRENT): "notice",
    }
    return transitions.get((old_status, new_status))


def scan_watchlist(watchlist: list) -> list:
    """扫描整个监听清单，返回变更列表"""
    changes = []
    for item in watchlist:
        fgmc = item["fgmc"]
        ftnum = item["ftnum"]
        old_status = item["last_status"]
        last_checked = item.get("last_checked", "")

        # 检查当前状态
        result = check_ft_detail(fgmc, ftnum)
        if "error" in result:
            print(f"  [ERROR] {fgmc} {ftnum}: {result['error']}")
            continue

        new_status = result.get("data", {}).get("sxx", "未知")
        item["last_checked"] = datetime.now().isoformat()
        item["last_status"] = new_status

        # 检测变化
        if new_status != old_status:
            level = detect_change(old_status, new_status)
            changes.append({
                "fgmc": fgmc,
                "ftnum": ftnum,
                "old_status": old_status,
                "new_status": new_status,
                "level": level,
                "content": result.get("data", {}).get("content", ""),
                "first_retrieved": item.get("first_retrieved", ""),
                "used_in_matters": item.get("used_in_matters", []),
            })
    return changes


def generate_alert(change: dict) -> str:
    """生成预警消息"""
    level_emoji = {
        "critical": "🔴",
        "warning": "🟠",
        "notice": "🟡",
    }
    level_label = {
        "critical": "紧急",
        "warning": "警告",
        "notice": "关注",
    }
    emoji = level_emoji.get(change["level"], "❓")
    label = level_label.get(change["level"], "未知")

    alert = f"""
{emoji} [{label}] 法条状态变化

**法条**: 《{change['fgmc']}》 第 {change['ftnum']} 条
**变化**: {change['old_status']} → {change['new_status']}
**首次检索**: {change['first_retrieved']}

### 当前条文
{change['content'][:300]}{'...' if len(change['content']) > 300 else ''}

### 影响范围
"""
    for matter in change["used_in_matters"]:
        alert += f"- {matter}\n"
    if not change["used_in_matters"]:
        alert += "- 无在办事项使用\n"

    alert += """
### 建议行动
- [ ] 重新检索法条（当前版本）
- [ ] 评估在办事项影响
- [ ] 通知相关律师/客户
"""
    return alert


def log_change(change: dict):
    """记录变更日志"""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(f"[{datetime.now().isoformat()}] {change['fgmc']} {change['ftnum']}: "
                f"{change['old_status']} → {change['new_status']}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="法条修订监控")
    parser.add_argument("--watchlist", help="监听清单文件路径")
    parser.add_argument("--add", action="store_true", help="添加新法条到监听清单")
    parser.add_argument("--fgmc", help="法规名（用于 --add）")
    parser.add_argument("--ftnum", help="条号（用于 --add）")
    parser.add_argument("--matter", help="关联的事项 slug（用于 --add）")
    parser.add_argument("--scan", action="store_true", help="扫描监听清单")
    parser.add_argument("--report", help="生成变更报告 (YYYY-MM)")
    parser.add_argument("--loop", type=int, help="持续运行，每 N 小时扫描一次")
    args = parser.parse_args()

    if args.add:
        if not args.fgmc or not args.ftnum:
            print("ERROR: --fgmc and --ftnum required")
            sys.exit(1)
        watchlist = load_watchlist()
        result = check_ft_detail(args.fgmc, args.ftnum)
        if "error" in result:
            print(f"ERROR: {result['error']}")
            sys.exit(1)
        new_item = {
            "fgmc": args.fgmc,
            "ftnum": args.ftnum,
            "first_retrieved": datetime.now().isoformat(),
            "last_checked": datetime.now().isoformat(),
            "last_status": result.get("data", {}).get("sxx", "未知"),
            "used_in_matters": [args.matter] if args.matter else [],
        }
        watchlist.append(new_item)
        save_watchlist(watchlist)
        print(f"✅ 已添加: {args.fgmc} {args.ftnum}")
        print(f"   状态: {new_item['last_status']}")
        return

    if args.scan or args.loop:
        watchlist = load_watchlist()
        if not watchlist:
            print("监听清单为空。使用 --add 添加法条。")
            return

        print(f"开始扫描 {len(watchlist)} 个法条...")
        changes = scan_watchlist(watchlist)
        save_watchlist(watchlist)

        if changes:
            print(f"\n检测到 {len(changes)} 个变化:\n")
            for change in changes:
                alert = generate_alert(change)
                print(alert)
                log_change(change)
        else:
            print("✅ 无变化")

        if args.loop:
            print(f"\n下次扫描: {args.loop} 小时后")
            time.sleep(args.loop * 3600)
            return main()  # 递归
        return

    if args.report:
        print(f"生成 {args.report} 月报...")
        # TODO: 实现月报生成
        return

    parser.print_help()


if __name__ == "__main__":
    main()