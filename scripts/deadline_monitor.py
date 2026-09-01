#!/usr/bin/env python3
"""
deadline_monitor.py — 时效主动预警 (W7.2)

律师痛点: 错过上诉期/再审期/答辩期/履行期 → 案件败诉
本工具: 扫描本地案件库 (cases.db 或 matter 目录),
  生成"时效预警清单", 按紧急度排序, Markdown 输出.

支持的时效类型:
  - 上诉期 (民诉/刑诉/行政判决15天/裁定10天)
  - 再审申请期 (民诉 6 个月, 刑诉无期限)
  - 答辩期 (民诉 15 天, 涉外 30 天)
  - 履行期 (履行通知书指定期)
  - 仲裁时效 (1 年)
  - 普通诉讼时效 (3 年)
  - 离婚后财产分割 (3 年)

用法:
  # 扫描本地 cases.db
  python3 scripts/deadline_monitor.py --db cases.db --output deadline-report.md

  # 列出 30 天内即将到期
  python3 scripts/deadline_monitor.py --db cases.db --within-days 30

  # 集成 matter 目录 (JSON 形式, 每案件一个 .json)
  python3 scripts/deadline_monitor.py --matters-dir matters/ --output alert.md

matter JSON schema:
  {
    "case_id": "...",
    "case_type": "民诉/刑诉/...",
    "procedure": "一审/二审/再审/执行",
    "trigger_date": "2026-08-01",  # 期限起算日 (送达日/判决日)
    "trigger_type": "judgment_served",  # 见 TRIGGER_TYPES
    "parties": ["原告", "被告"]
  }
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# === 时效规则 (按案由类型 + 程序) ===
@dataclass
class DeadlineRule:
    trigger_type: str        # 触发类型
    case_types: list[str]    # 适用案由
    procedure: str           # 程序
    days: int                # 期限天数
    description: str
    legal_basis: str         # 法条依据


DEADLINE_RULES = [
    # 民诉
    DeadlineRule("judgment_served", ["民诉"], "一审", 15,
                 "民诉判决上诉期", "民诉法 第171条"),
    DeadlineRule("ruling_served", ["民诉"], "一审", 10,
                 "民诉裁定上诉期", "民诉法 第171条"),
    DeadlineRule("judgment_served", ["民诉"], "二审", 6,
                 "民诉再审申请期 (判决/裁定生效后 6 个月)", "民诉法 第216条"),
    DeadlineRule("complaint_served", ["民诉"], "一审", 15,
                 "民诉答辩期", "民诉法 第126条"),
    # 涉外民诉
    DeadlineRule("complaint_served", ["民诉涉外"], "一审", 30,
                 "涉外民诉答辩期", "民诉法 第274条"),
    DeadlineRule("judgment_served", ["民诉涉外"], "一审", 30,
                 "涉外民诉上诉期", "民诉法 第279条"),
    # 刑诉
    DeadlineRule("judgment_received", ["刑诉"], "一审", 10,
                 "刑诉判决上诉/抗诉期", "刑诉法 第230条"),
    DeadlineRule("ruling_received", ["刑诉"], "一审", 5,
                 "刑诉裁定上诉期", "刑诉法 第230条"),
    DeadlineRule("complaint_received", ["刑诉附带民诉"], "一审", 10,
                 "刑事附带民诉答辩期", "刑诉法 第101条"),
    # 行政诉讼
    DeadlineRule("judgment_received", ["行政"], "一审", 15,
                 "行政判决上诉期", "行政诉讼法 第85条"),
    DeadlineRule("ruling_received", ["行政"], "一审", 10,
                 "行政裁定上诉期", "行政诉讼法 第85条"),
    DeadlineRule("administrative_action", ["行政"], "起诉", 6,
                 "行政起诉期限 (知道行为之日起 6 个月, 最长 5 年)", "行政诉讼法 第46条"),
    # 仲裁
    DeadlineRule("award_received", ["仲裁"], "裁决", 6,
                 "仲裁裁决撤销申请期", "仲裁法 第59条"),
    # 履行期
    DeadlineRule("performance_notice", ["执行"], "履行", 0,
                 "履行通知书指定期 (通常 15-30 天, 视通知书)", "民诉法 第253条"),
    # 民事时效
    DeadlineRule("knowledge_date", ["民事时效"], "时效", 1095,  # 3 年
                 "普通诉讼时效", "民法典 第188条"),
]


# === Trigger types ===
TRIGGER_TYPES = sorted({r.trigger_type for r in DEADLINE_RULES})


@dataclass
class MatterDeadline:
    case_id: str
    case_type: str
    procedure: str
    trigger_date: date
    deadline_date: date
    days_remaining: int       # 距今天数 (负数 = 已过期)
    description: str
    legal_basis: str
    parties: list[str] = field(default_factory=list)
    urgency: str = ""         # 已过期/紧急/警告/正常

    @property
    def is_expired(self) -> bool:
        return self.days_remaining < 0

    @property
    def is_critical(self) -> bool:
        return 0 <= self.days_remaining <= 7

    @property
    def is_warning(self) -> bool:
        return 8 <= self.days_remaining <= 30


def calc_deadline(matter: dict, today: date) -> Optional[MatterDeadline]:
    """根据 matter 信息计算时效届满日

    Args:
        matter: {"case_id", "case_type", "procedure", "trigger_date", "trigger_type", "parties"}
        today: 当前日期
    Returns:
        MatterDeadline 对象 (找不到规则返回 None)
    """
    trigger_type = matter.get("trigger_type", "")
    case_type = matter.get("case_type", "")
    procedure = matter.get("procedure", "一审")
    trigger_date_str = matter.get("trigger_date", "")

    if not trigger_date_str:
        return None
    try:
        trigger_date = datetime.strptime(trigger_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    # 找规则
    rule = None
    for r in DEADLINE_RULES:
        if r.trigger_type == trigger_type and case_type in r.case_types \
                and r.procedure == procedure:
            rule = r
            break

    if not rule:
        return None

    deadline_date = trigger_date + timedelta(days=rule.days)
    days_remaining = (deadline_date - today).days

    if days_remaining < 0:
        urgency = "EXPIRED"
    elif days_remaining <= 7:
        urgency = "CRITICAL"
    elif days_remaining <= 30:
        urgency = "WARNING"
    else:
        urgency = "NORMAL"

    return MatterDeadline(
        case_id=matter.get("case_id", "未知"),
        case_type=case_type,
        procedure=procedure,
        trigger_date=trigger_date,
        deadline_date=deadline_date,
        days_remaining=days_remaining,
        description=rule.description,
        legal_basis=rule.legal_basis,
        parties=matter.get("parties", []),
        urgency=urgency,
    )


def load_matters_from_dir(matters_dir: Path) -> list[dict]:
    """从 matter 目录加载案件 (每案件一个 .json)"""
    matters = []
    for fp in sorted(matters_dir.glob("*.json")):
        try:
            matters.append(json.loads(fp.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            print(f"⚠ {fp.name} 解析失败: {e}", file=sys.stderr)
    return matters


def load_matters_from_db(db_path: Path) -> list[dict]:
    """从 cases.db 加载 (使用 judgment_date 作为送达日, 假设一审判决上诉期)"""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT id, cause_of_action, judgment_date, parties "
            "FROM cases WHERE judgment_date IS NOT NULL"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    matters = []
    for case_id, cause, jd, parties in rows:
        if not jd:
            continue
        matters.append({
            "case_id": case_id,
            "case_type": "民诉",  # 缺信息, 默认民诉
            "procedure": "一审",
            "trigger_type": "judgment_served",
            "trigger_date": jd,
            "parties": [parties] if parties else [],
        })
    return matters


def format_report(deadlines: list[MatterDeadline], today: date) -> str:
    """生成 Markdown 时效预警报告"""
    md = f"""# 时效预警报告

> ⚠️ **AI 辅助生成 — 律师审阅后使用** (上海律协指引 2025-08 §13)
> 本报告扫描本地案件库, 识别临近/已过期时效. 律师必须复核送达日准确性,
> **节假日顺延/在途期间扣除/中止中断事由** 需律师人工判断.

**生成时间**: {today.isoformat()}
**案件扫描数**: {len(deadlines)}

## 紧急度分布

"""
    by_urgency: dict[str, list] = {"EXPIRED": [], "CRITICAL": [], "WARNING": [], "NORMAL": []}
    for d in deadlines:
        by_urgency[d.urgency].append(d)

    md += "| 紧急度 | 案件数 | 说明 |\n|--------|--------|------|\n"
    md += f"| 🔴 **EXPIRED** (已过期) | {len(by_urgency['EXPIRED'])} | 立即处理 |\n"
    md += f"| 🟠 **CRITICAL** (≤ 7 天) | {len(by_urgency['CRITICAL'])} | 48 小时内处理 |\n"
    md += f"| 🟡 **WARNING** (8-30 天) | {len(by_urgency['WARNING'])} | 2 周内处理 |\n"
    md += f"| 🟢 **NORMAL** (> 30 天) | {len(by_urgency['NORMAL'])} | 正常跟踪 |\n"

    if not deadlines:
        md += "\n✅ **无案件时效预警** (案件库为空或均已结案)\n"
        return md

    md += "\n## 案件时效清单 (按紧急度排序)\n\n"
    md += "| 案件ID | 程序 | 起算日 | 届满日 | 剩余天数 | 类型 | 法条 | 紧急 |\n"
    md += "|--------|------|--------|--------|----------|------|------|------|\n"
    for urgency in ["EXPIRED", "CRITICAL", "WARNING", "NORMAL"]:
        for d in sorted(by_urgency[urgency], key=lambda x: x.days_remaining):
            md += (
                f"| {d.case_id} | {d.procedure} | {d.trigger_date.isoformat()} | "
                f"{d.deadline_date.isoformat()} | "
                f"{d.days_remaining:+d} | {d.description} | {d.legal_basis} | "
                f"{d.urgency} |\n"
            )

    md += "\n## 律师审阅闸\n\n"
    md += "> ⚠️ 本报告为辅助工具, 律师必须:\n"
    md += "> 1. 复核每个案件的**实际送达日** (本报告按 judgment_date 估算)\n"
    md += "> 2. 评估**节假日顺延** (法定节假日届满日顺延至其后第一个工作日)\n"
    md += "> 3. 评估**在途期间扣除** (律师在途期间不计入)\n"
    md += "> 4. 评估**时效中断/中止事由** (民法典 195-196 条)\n"
    md += "> 5. 对 EXPIRED 案件, 评估是否仍有补救路径 (如: 申请再审/检察建议)\n"
    md += ">\n"
    md += "> 任何对外法律行为前必须经执业律师审阅核实.\n"

    return md


def main():
    """W7.2 + W14 统一入口

    W7.2 模式 (--matters-dir / --db): 扫描已有 matter JSON 库
    W14 模式 (--timeline): 接 cn-element-extraction 时间线, 自动算时效
    """
    parser = argparse.ArgumentParser(
        description="时效主动预警 (W7.2 扫描 / W14 自动计算)")
    parser.add_argument("--timeline", help="时间线 JSON (W14, cn-element-extraction A2 输出)")
    parser.add_argument("--case-type", default="合同纠纷",
                        help="案由 (W14 模式)")
    parser.add_argument("--case-id", default="未命名案件",
                        help="案件 ID (W14 模式)")
    parser.add_argument("--matters-dir", help="matter 目录 (W7.2 模式)")
    parser.add_argument("--db", help="cases.db 路径 (W7.2 模式)")
    parser.add_argument("-o", "--output", help="输出 Markdown 文件 (默认 stdout)")
    parser.add_argument("--within-days", type=int, default=30,
                        help="仅显示 N 天内 (W7.2 模式, 默认 30)")
    parser.add_argument("--today", default=None,
                        help="指定今天日期 (YYYY-MM-DD)")
    args = parser.parse_args()

    # today
    if args.today:
        today = datetime.strptime(args.today, "%Y-%m-%d").date()
    else:
        today = date.today()

    # W14 模式: 时间线 → 自动计算
    if args.timeline:
        timeline_path = Path(args.timeline)
        if not timeline_path.exists():
            print(f"❌ 时间线文件不存在: {timeline_path}", file=sys.stderr)
            sys.exit(1)
        try:
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
            sys.exit(1)

        deadlines = auto_calc_from_timeline(timeline, args.case_type, today)
        md = format_auto_report(deadlines, args.case_id, today)

        if args.output:
            Path(args.output).write_text(md, encoding="utf-8")
            n_expired = sum(1 for d in deadlines if d.urgency == "EXPIRED")
            n_critical = sum(1 for d in deadlines if d.urgency == "CRITICAL")
            print(f"✅ 已生成: {args.output}", file=sys.stderr)
            print(f"   时效数: {len(deadlines)} | EXPIRED: {n_expired} | CRITICAL: {n_critical}",
                  file=sys.stderr)
        else:
            print(md)
        return

    # W7.2 模式: 扫描 matter 库
    if not args.db and not args.matters_dir:
        parser.error("必须提供 --timeline (W14), 或 --db / --matters-dir (W7.2)")

    if args.db:
        matters = load_matters_from_db(Path(args.db))
    else:
        matters = load_matters_dir_safe(Path(args.matters_dir))

    if not matters:
        print("⚠ 无案件 (db/matters-dir 为空)", file=sys.stderr)

    deadlines = []
    for m in matters:
        d = calc_deadline(m, today)
        if d:
            deadlines.append(d)

    filtered = [
        d for d in deadlines
        if d.urgency in ("EXPIRED", "CRITICAL")
        or d.days_remaining <= args.within_days
    ]

    md = format_report(filtered, today)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        n_expired = sum(1 for d in filtered if d.urgency == "EXPIRED")
        n_critical = sum(1 for d in filtered if d.urgency == "CRITICAL")
        print(f"✅ 已生成: {args.output}", file=sys.stderr)
        print(f"   案件: {len(filtered)} | EXPIRED: {n_expired} | CRITICAL: {n_critical}", file=sys.stderr)
    else:
        print(md)


def load_matters_dir_safe(d: Path) -> list[dict]:
    """W7.2 旧版兼容 (避免重复定义)"""
    return load_matters_from_dir(d)


# === W14: 自动时效计算器 v2.0 ===
# 接 cn-element-extraction 时间线, 不依赖律师手动录 trigger_date

# 时效类别 → 起算日触发事件 + 法条
TIME_BAR_TRIGGERS = {
    "诉讼时效_普通": {
        "trigger_event": ["违约日", "侵权日", "债权到期日", "解除合同日", "行政行为日"],
        "anchor": "知道或应当知道权利受到损害以及义务人之日起 3 年",
        "legal_basis": "民法典 第188条",
        "days": 365 * 3,
        "case_types": ["合同纠纷", "侵权", "借贷", "房屋买卖", "婚姻财产", "建设工程", "知识产权", "医疗损害", "交通事故"],
    },
    "诉讼时效_短期": {
        "trigger_event": ["人身损害日", "拒付租金日", "拖欠劳动报酬日", "出售质量不合格商品未声明日"],
        "anchor": "知道或应当知道权利受到损害以及义务人之日起 1 年 (特别法)",
        "legal_basis": "民法典 第188条第2款 / 产品质量法 等",
        "days": 365,
        "case_types": ["侵权", "借贷", "劳动报酬"],
    },
    "诉讼时效_最长20年": {
        "trigger_event": ["权利受到损害日"],
        "anchor": "自权利受到损害之日起 20 年 (最长保护期)",
        "legal_basis": "民法典 第188条第2款",
        "days": 365 * 20,
        "case_types": ["*"],
    },
    "劳动仲裁时效": {
        "trigger_event": ["解除劳动合同日", "工资欠付日", "劳动争议发生日"],
        "anchor": "知道或应当知道其权利被侵害之日起 1 年",
        "legal_basis": "劳动争议调解仲裁法 第27条",
        "days": 365,
        "case_types": ["劳动争议"],
    },
    "上诉期_民诉判决": {
        "trigger_event": ["一审判决书送达日"],
        "anchor": "判决书送达之日起 15 日",
        "legal_basis": "民诉法 第171条",
        "days": 15,
        "case_types": ["合同纠纷", "侵权", "婚姻", "借贷", "房屋买卖", "建设工程", "知识产权", "医疗损害", "交通事故"],
    },
    "上诉期_民诉裁定": {
        "trigger_event": ["一审裁定书送达日"],
        "anchor": "裁定书送达之日起 10 日",
        "legal_basis": "民诉法 第171条",
        "days": 10,
        "case_types": ["*"],
    },
    "再审申请期_民诉判决": {
        "trigger_event": ["二审判决/裁定生效日", "一审判决/裁定生效日 (无上诉)"],
        "anchor": "判决/裁定发生法律效力之日起 6 个月内",
        "legal_basis": "民诉法 第216条",
        "days": 30 * 6,
        "case_types": ["*"],
    },
    "答辩期_民诉": {
        "trigger_event": ["起诉状副本送达日"],
        "anchor": "副本送达之日起 15 日内提出答辩状",
        "legal_basis": "民诉法 第126条",
        "days": 15,
        "case_types": ["*"],
    },
    "答辩期_涉外": {
        "trigger_event": ["起诉状副本送达日"],
        "anchor": "副本送达之日起 30 日 (涉外)",
        "legal_basis": "民诉法 第274条",
        "days": 30,
        "case_types": ["涉外"],
    },
    "行政起诉期": {
        "trigger_event": ["行政行为作出日", "收到行政行为通知日"],
        "anchor": "知道作出行政行为之日起 6 个月, 最长 5 年",
        "legal_basis": "行政诉讼法 第46条",
        "days": 30 * 6,
        "case_types": ["行政"],
    },
    "仲裁裁决撤销": {
        "trigger_event": ["仲裁裁决书送达日"],
        "anchor": "收到裁决书之日起 6 个月",
        "legal_basis": "仲裁法 第59条",
        "days": 30 * 6,
        "case_types": ["仲裁"],
    },
}


# 中断/中止证据形式清单 (W14 P0 痛点)
INTERRUPTION_EVIDENCE = [
    {
        "type": "起诉/仲裁",
        "form": "法院/仲裁委受理案件通知书、立案通知书",
        "legal_basis": "民法典 第195条第1项",
        "evidence_quality": "强 (直接中断)",
    },
    {
        "type": "主张权利",
        "form": "催款函/律师函 + 送达凭证 (EMS签收回执)",
        "legal_basis": "民法典 第195条第2项",
        "evidence_quality": "中 (需证明送达对方)",
    },
    {
        "type": "对方同意履行",
        "form": "书面承诺还款/部分还款凭证/对账单",
        "legal_basis": "民法典 第195条第2项",
        "evidence_quality": "强 (对方自认)",
    },
    {
        "type": "其他与提起诉讼具有同等效力",
        "form": "申请调解/申请仲裁/向人民调解委员会申请调解",
        "legal_basis": "民法典 第195条第3、4项",
        "evidence_quality": "中 (视具体形式)",
    },
]

SUSPENSION_GROUNDS = [
    {"ground": "不可抗力 (天灾/疫情等)",
     "duration": "最后 6 个月内, 时效中止; 原因消除后继续 6 个月",
     "evidence": "政府公告/疫情通报/媒体公开记录"},
    {"ground": "无/限制民事行为能力人无法定代理人",
     "duration": "时效中止, 法定代理人确定后继续",
     "evidence": "户籍证明/监护权证明"},
    {"ground": "继承开始后未确定继承人/遗产管理人",
     "duration": "时效中止, 继承人/遗产管理人确定后继续",
     "evidence": "继承公证/法院判决"},
    {"ground": "权利人被义务人或其他人控制",
     "duration": "时效中止, 失去控制后继续",
     "evidence": "报警记录/限制人身自由决定"},
]


@dataclass
class TimelineEvent:
    """时间线节点 (来自 cn-element-extraction A2)"""
    date: date
    event: str
    source: str = ""
    certainty: str = "确定"  # 确定 / 推定 / 待核
    category: str = ""  # 合同签订日 / 违约日 / 解除日 / 催告日 / 起诉日


@dataclass
class AutoDeadline:
    """自动计算出的时效"""
    category: str            # 诉讼时效_普通 / 上诉期_民诉判决
    trigger_event: str       # 触发的事件名 (来自 TimelineEvent.event)
    trigger_date: date
    deadline_date: date
    days_remaining: int
    legal_basis: str
    description: str
    urgency: str             # EXPIRED / CRITICAL / WARNING / NORMAL
    interruption_evidence: list = field(default_factory=list)
    suspension_grounds: list = field(default_factory=list)


def auto_calc_from_timeline(
    timeline: list[dict],
    case_type: str = "合同纠纷",
    today: Optional[date] = None,
) -> list[AutoDeadline]:
    """W14 P0: 从 cn-element-extraction 时间线自动算时效

    Args:
        timeline: A2 时间线节点列表, 每项 {date, event, source, certainty}
        case_type: 案由 (决定适用哪些时效规则)
        today: 当前日期 (默认系统日期)

    Returns:
        AutoDeadline 列表, 按 urgency 排序
    """
    if today is None:
        today = date.today()

    # 解析 timeline → TimelineEvent
    events: list[TimelineEvent] = []
    for t in timeline:
        if isinstance(t.get("date"), str):
            try:
                d = datetime.strptime(t["date"], "%Y-%m-%d").date()
            except ValueError:
                continue
        elif isinstance(t.get("date"), date):
            d = t["date"]
        else:
            continue
        events.append(TimelineEvent(
            date=d,
            event=t.get("event", ""),
            source=t.get("source", ""),
            certainty=t.get("certainty", "确定"),
            category=t.get("category", ""),
        ))

    if not events:
        return []

    deadlines: list[AutoDeadline] = []

    # 遍历所有时效类别, 看 timeline 是否有匹配事件
    for cat_name, cat in TIME_BAR_TRIGGERS.items():
        # 案由过滤
        if cat["case_types"] != ["*"] and case_type not in cat["case_types"]:
            continue
        # 找匹配事件
        for ev in events:
            matched = False
            for trig in cat["trigger_event"]:
                if trig in ev.event or trig in ev.category:
                    matched = True
                    break
            if not matched:
                continue
            # 计算 deadline
            deadline_date = ev.date + timedelta(days=cat["days"])
            days_remaining = (deadline_date - today).days

            if days_remaining < 0:
                urgency = "EXPIRED"
            elif days_remaining <= 7:
                urgency = "CRITICAL"
            elif days_remaining <= 30:
                urgency = "WARNING"
            else:
                urgency = "NORMAL"

            deadlines.append(AutoDeadline(
                category=cat_name,
                trigger_event=ev.event,
                trigger_date=ev.date,
                deadline_date=deadline_date,
                days_remaining=days_remaining,
                legal_basis=cat["legal_basis"],
                description=cat["anchor"],
                urgency=urgency,
                interruption_evidence=INTERRUPTION_EVIDENCE if "诉讼时效" in cat_name else [],
                suspension_grounds=SUSPENSION_GROUNDS if "诉讼时效" in cat_name else [],
            ))

    # 去重: 同一类别可能匹配多个 event, 保留最早的 (最早触发的时效)
    seen: dict[str, AutoDeadline] = {}
    for d in deadlines:
        if d.category not in seen or d.trigger_date < seen[d.category].trigger_date:
            seen[d.category] = d

    return sorted(seen.values(), key=lambda x: x.days_remaining)


def format_auto_report(deadlines: list[AutoDeadline], case_id: str, today: date) -> str:
    """生成自动时效计算报告"""
    md = f"""# 自动时效计算报告 (W14)

> ⚠️ **AI 辅助生成 — 律师审阅后使用** (上海律协指引 2025-08 §13)
> 本报告从案情时间线 (cn-element-extraction A2) **自动计算**诉讼时效 / 上诉期 / 答辩期.
> 律师必须复核: 时间线节点准确性 + 中断/中止事由是否已发生.

**案件**: {case_id}
**生成时间**: {today.isoformat()}
**识别的时效数**: {len(deadlines)}

## 时效清单 (按紧急度排序)

| 类别 | 触发事件 | 起算日 | 届满日 | 剩余天数 | 紧急 | 法条 |
|------|---------|--------|--------|----------|------|------|
"""
    urgency_icon = {
        "EXPIRED": "🔴", "CRITICAL": "🟠", "WARNING": "🟡", "NORMAL": "🟢"
    }
    for d in sorted(deadlines, key=lambda x: x.days_remaining):
        icon = urgency_icon.get(d.urgency, "")
        md += (
            f"| {d.category} | {d.trigger_event} | {d.trigger_date.isoformat()} | "
            f"{d.deadline_date.isoformat()} | {d.days_remaining:+d} | {icon} {d.urgency} | "
            f"{d.legal_basis} |\n"
        )

    # 中断/中止证据清单 (诉讼时效才需要)
    statute_deadlines = [d for d in deadlines if "诉讼时效" in d.category or "仲裁时效" in d.category]
    if statute_deadlines:
        md += "\n## 中断事由证据清单 (民法典 第195条)\n\n"
        md += "**以下任一证据成立, 诉讼时效从该日起重新计算 3 年**:\n\n"
        md += "| 类型 | 证据形式 | 证明力 | 法条 |\n"
        md += "|------|---------|--------|------|\n"
        for ie in INTERRUPTION_EVIDENCE:
            md += f"| {ie['type']} | {ie['form']} | {ie['evidence_quality']} | {ie['legal_basis']} |\n"

        md += "\n## 中止事由清单 (民法典 第194条)\n\n"
        md += "**以下情形发生, 时效中止; 原因消除后继续计算**:\n\n"
        md += "| 事由 | 持续时间 | 证据 |\n"
        md += "|------|---------|------|\n"
        for sg in SUSPENSION_GROUNDS:
            md += f"| {sg['ground']} | {sg['duration']} | {sg['evidence']} |\n"

    md += """

## 律师审阅闸

> ⚠️ 本报告为辅助工具, 律师必须:
> 1. **复核时间线准确性** (cn-element-extraction 提取的事件可能漏判/误判)
> 2. **核查中断事由**: 已发生的部分还款/催告/起诉/书面承诺 → 诉讼时效**从该日起重新计算**
> 3. **核查中止事由**: 不可抗力/无行为能力等 → 时效**暂停**, 原因消除后继续
> 4. **节假日顺延**: 届满日为法定节假日的, 顺延至其后第一个工作日 (民诉法 第83条)
> 5. **在途期间扣除**: 律师因不可抗力/正当理由在途期间不计入 (民诉法 第82条)
> 6. 对 EXPIRED 案件评估补救路径 (申请再审/检察建议/调解)
>
> 任何对外法律行为前必须经执业律师审阅核实.
"""
    return md


if __name__ == "__main__":
    main()