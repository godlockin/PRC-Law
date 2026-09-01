#!/usr/bin/env python3
"""
mediation_hint.py — 调解策略生成器 (cn-mediation-hint)

输入: 案由 + 标的额 + 双方诉求 + 证据强度 + 程序阶段
输出: 让幅区间 + 类案胜诉率 + 成本测算 + 风险弱点 + 底线策略

算法核心:
  expected_value = amount × win_rate_predicted - cost_to_proceed
  让幅区间 = [expected × 0.85, expected × 1.15]

类案胜诉率: 调用 CaseClient.search() 抽样类案统计
  - 民事类案: 基于 cail2018 (刑事) + 法律规则基线 (规则常量)
  - 实际项目里可接入民商事案例库

依赖:
  - scripts/case_client.py (cail2018 streaming)
  - 不需要 LLM, 纯规则引擎 + 案例统计

用法:
    from scripts.mediation_hint import MediationHintEngine, CaseInput
    engine = MediationHintEngine()
    inp = CaseInput(case_type="合同纠纷", amount=100.0, ...)
    report = engine.generate(inp)
    print(report)
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# === 输入 ===
@dataclass
class CaseInput:
    """调解案件输入"""
    case_type: str           # 案由 — "合同纠纷" / "劳动争议" / "侵权" / "婚姻" / "借贷"
    amount: float            # 标的额 (万元)
    plaintiff_demand: str    # 原告诉求 (简述)
    defendant_position: str  # 被告答辩 (简述)
    evidence_plaintiff: str = "中"  # 原告证据: 强/中/弱
    evidence_defendant: str = "中"  # 被告证据: 强/中/弱
    procedural_stage: str = "诉前"  # 诉前/诉中/庭前
    lawyer_role: str = "原告"  # 律师代理: 原告/被告
    # 案件时间 (月): 影响时间成本测算
    case_age_months: int = 3
    # 案件标的特征
    has_written_contract: bool = True
    is_continued_performance: bool = False


# === 类案基线胜诉率 (来自中国司法大数据 + 法律实务共识) ===
# 这些是基于公开统计的参考值, 律师使用时应基于本地案例库校准
BASE_WIN_RATES = {
    "合同纠纷": 0.62,    # 原告胜诉率(部分支持)
    "劳动争议": 0.78,    # 劳动者倾向胜诉
    "侵权": 0.55,
    "婚姻": 0.45,        # 离婚诉求驳回率较高
    "借贷": 0.75,        # 有借据情况下
    "房屋买卖": 0.58,
    "建设工程": 0.50,
    "知识产权": 0.45,
    "医疗损害": 0.40,
    "交通事故": 0.70,
}


# === 证据强度调节系数 ===
# 表格 (与 cn-mediation-hint/SKILL.md 一致):
#              原告证据 ↓ / 被告证据 →
#              强      中      弱
#   强       +0.10  +0.15  +0.25
#   中       -0.15   0.00  +0.15
#   弱       -0.25  -0.15  -0.05
EVIDENCE_ADJUST = {
    ("强", "强"): +0.10,   # 双方证据均充分, 原告略占 (有举证责任分配优势)
    ("强", "中"): +0.15,
    ("强", "弱"): +0.25,   # 原告证据明显优势
    ("中", "强"): -0.15,
    ("中", "中"): 0.00,
    ("中", "弱"): +0.15,
    ("弱", "强"): -0.25,   # 被告证据明显优势
    ("弱", "中"): -0.15,
    ("弱", "弱"): -0.05,   # 双方均弱, 法官倾向维持现状
}


# === 案由时效 (月) ===
# 注意区分: 民法典第188条第1款 (普通3年) vs 第188条第2款 (最长20年)
#            民法典第195条第1项 (人身损害 1 年)
STATUTE_OF_LIMITATIONS = {
    "合同纠纷": 36,        # 民法典第188条第1款 - 普通诉讼时效 3 年
    "劳动争议": 12,        # 劳动争议调解仲裁法第27条第1款 - 仲裁时效 1 年
    "侵权": 36,            # 财产侵权: 民法典第188条第1款 (3年); 人身损害: 第195条第1项 (1年)
    "婚姻": 36,            # 离婚本身无时效 (形成权); 离婚后财产分割 3 年 (民法典第188条第1款)
    "借贷": 36,            # 民法典第188条第1款
    "房屋买卖": 36,        # 民法典第188条第1款 (房屋权属争议另论)
    "建设工程": 36,        # 工程款请求权: 民法典第807条优先权 (6个月); 兜底第188条 (3年)
    "知识产权": 36,        # 民法典第188条第1款; 专利/商标另参专门法
    "医疗损害": 36,        # 财产损害: 民法典第188条第1款 (3年); 人身损害: 第195条第1项 (1年)
    "交通事故": 36,        # 财产损害: 民法典第188条第1款 (3年); 人身损害: 第195条第1项 (1年)
}


# === 律师费基线 (中位数, 各地有差异) ===
LAWYER_FEE_RATE = {
    # 标的额区间(万元) → 律师费比例
    "tier1": (0, 10, 0.085),       # 10万以下 8.5%
    "tier2": (10, 50, 0.055),      # 10-50万 5.5%
    "tier3": (50, 100, 0.04),      # 50-100万 4%
    "tier4": (100, 500, 0.025),    # 100-500万 2.5%
    "tier5": (500, 1000, 0.015),   # 500-1000万 1.5%
    "tier6": (1000, float("inf"), 0.01),  # 1000万以上 1%
}


def estimate_lawyer_fee(amount: float) -> float:
    """估算律师费 (万元) — 简单分档累进"""
    fee = 0.0
    remaining = amount
    tiers = sorted(LAWYER_FEE_RATE.values(), key=lambda x: x[0])
    prev_upper = 0
    for lower, upper, rate in tiers:
        if remaining <= 0:
            break
        span = upper - lower if upper != float("inf") else remaining
        used = min(remaining, span)
        fee += used * rate
        remaining -= used
        prev_upper = upper
    return round(fee, 2)


# === 核心算法 ===
@dataclass
class MediationReport:
    """调解策略报告"""
    case_summary: str
    win_rate_predicted: float       # 预测胜诉率 (按律师代理方)
    evidence_assessment: str        # 证据评估
    settlement_low: float           # 让幅下限 (万元)
    settlement_high: float          # 让幅上限 (万元)
    settlement_recommend: float     # 建议初始报价 (万元)
    cost_to_proceed: dict           # 成本测算
    risk_weaknesses: list[str]      # 风险弱点清单
    bottom_line: str                # 底线策略
    time_to_settle_months: int      # 预计调解耗时 (月)
    class_case_refs: list[dict]     # 类案先例引用 (cail2018 + 规则)
    strategy_summary: str           # 一句话策略总结
    disclaimer: str = ""            # AI 标识 + 律师审阅闸

    def to_markdown(self, amount: float = 0.0) -> str:
        """生成律师可直接阅读的 Markdown 策略单"""
        md = f"""# 调解策略建议单

> ⚠️ **AI 辅助生成 — 律师审阅后使用** (上海律协指引 2025-08 §13)
> 本建议基于规则引擎 + 类案统计, **仅供律师参考**, 不构成法律意见.
> 律师使用前必须: 1) 校准本地类案库; 2) 评估证据细节; 3) 与当事人充分沟通.
> 引用: PRC-Law cn-mediation-hint v1.0.0

---

## 一、案件摘要

{self.case_summary}

## 二、胜诉率预测

**律师代理方预测胜诉率**: **{self.win_rate_predicted:.0%}**

证据评估: {self.evidence_assessment}

## 三、让幅建议区间 (万元)

| 维度 | 金额 (万元) | 含义 |
|------|------------|------|
| 建议初始报价 | **{self.settlement_recommend:.1f}** | 调解第一次报价 |
| 让幅下限 | {self.settlement_low:.1f} | 律师最低接受线 |
| 让幅上限 | {self.settlement_high:.1f} | 律师最高接受线 |
| 标的额 | {amount:.1f} | 案件争议金额 |

## 四、成本测算

- **律师费估算**: {self.cost_to_proceed.get('lawyer_fee', 0):.1f} 万元
- **诉讼费**: {self.cost_to_proceed.get('court_fee', 0):.1f} 万元
- **时间成本**: {self.cost_to_proceed.get('time_months', 0)} 个月
- **机会成本**: {self.cost_to_proceed.get('opportunity', '中')}
- **总推进成本**: {self.cost_to_proceed.get('total', 0):.1f} 万元 (律师费+诉讼费)

## 五、风险弱点清单

"""
        for w in self.risk_weaknesses:
            md += f"- ⚠️ {w}\n"
        md += f"""
## 六、底线策略

{self.bottom_line}

## 七、预计耗时

**{self.time_to_settle_months} 个月** (从当前位置到结案, 调解成功路径)

## 八、类案先例引用

"""
        for ref in self.class_case_refs:
            md += f"- {ref}\n"

        md += f"""
## 九、策略总结

> {self.strategy_summary}

---

{self.disclaimer}

> ⚠️ **律师审阅闸**: 上述建议仅供参考. 律师必须:
> 1. 评估本案证据细节 (本引擎仅看粗强度)
> 2. 与当事人沟通调解授权范围
> 3. 拒绝/接受底线须当事人书面确认
> 4. 最终决策由律师 + 当事人共同作出
"""
        return md


class MediationHintEngine:
    """调解策略生成器"""

    def __init__(self, use_case_client: bool = True,
                 calibration: Optional[dict] = None):
        self.use_case_client = use_case_client
        self._case_client = None
        self._calibration = calibration  # 本地校准数据 {案由: {win_rate, confidence}}
        if use_case_client:
            try:
                from case_client import CaseClient
                self._case_client = CaseClient()
            except Exception as e:
                print(f"⚠ CaseClient 不可用 ({e}), 仅用规则基线", file=sys.stderr)

    @classmethod
    def from_calibration_file(cls, path: str, **kwargs) -> "MediationHintEngine":
        """从 local_calibration 生成的 JSON 加载基线"""
        cal = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(calibration=cal, **kwargs)

    def _resolve_base_rate(self, case_type: str) -> tuple[float, str, str]:
        """返回 (base_rate, 来源标签, 置信度)

        优先级: 本地校准 (high) > 本地校准 (low) > 规则基线
        """
        default = BASE_WIN_RATES.get(case_type, 0.55)
        if self._calibration:
            by_type = self._calibration.get("by_case_type", {})
            local = by_type.get(case_type)
            if local:
                wr = local.get("win_rate")
                conf = local.get("confidence", "insufficient")
                if wr is not None and conf == "high":
                    return wr, f"本地校准 ({local['sample_size']} 案)", "high"
                if wr is not None and conf == "low":
                    return wr, f"本地校准 (低置信, {local['sample_size']} 案)", "low"
        return default, "中国司法大数据 2023 规则基线", "default"

    def generate(self, inp: CaseInput) -> MediationReport:
        """生成调解策略报告"""
        # 1. 基础胜诉率 — 优先本地校准
        base_rate, base_source, base_conf = self._resolve_base_rate(inp.case_type)

        # 2. 证据调节
        adjust = EVIDENCE_ADJUST.get(
            (inp.evidence_plaintiff, inp.evidence_defendant), 0.0)
        win_rate = max(0.05, min(0.95, base_rate + adjust))

        # 2.5 ⚠️ 时效风险 (严重: 超过时效 → 案件必败)
        statute_months = STATUTE_OF_LIMITATIONS.get(inp.case_type, 36)
        if inp.case_age_months > statute_months:
            # 超过时效 → 胜诉率强制降到 5% (除非时效中断/中止)
            win_rate = 0.05
            if inp.lawyer_role == "原告":
                statute_risk = (
                    f"案件已 {inp.case_age_months} 个月, 超过{inp.case_type}诉讼时效期间({statute_months}个月, "
                    f"民法典第188条第1款). 时效抗辩将导致败诉, **不建议起诉**. "
                    f"若调解不成, 评估时效中断/中止事由 (民法典第195/196条)"
                )
            else:
                # 被告代理: 我方处于优势
                statute_risk = (
                    f"案件已 {inp.case_age_months} 个月, 超过{inp.case_type}诉讼时效期间({statute_months}个月). "
                    f"**可主张诉讼时效抗辩** (民法典第188条第1款 / 第193条), 原告起诉将被驳回"
                )
        elif inp.case_age_months > statute_months * 0.8:
            # 接近诉讼时效届满 (>80%) → 胜诉率 -0.20
            win_rate = max(0.05, win_rate - 0.20)
            statute_risk = (
                f"案件 {inp.case_age_months} 个月, 接近{inp.case_type}诉讼时效期间届满({statute_months}个月). "
                f"对方可能援引诉讼时效抗辩 (民法典第188条第1款 / 第193条)"
            )
        else:
            statute_risk = ""

        # 2.6 已履行义务 → 原告处于不利 (被告可主张瑕疵抗辩)
        if inp.is_continued_performance and inp.lawyer_role == "原告":
            win_rate = max(0.05, win_rate - 0.10)

        # 律师代理方角度调整
        if inp.lawyer_role == "被告":
            win_rate = 1.0 - win_rate  # 被告角度 = 1 - 原告胜诉率

        # 3. 类案统计校准 (ChatLaw 2024 民事 + cail2018 刑事 + 规则基线)
        class_refs = []
        if self._case_client and self._case_client.is_available():
            # 3.1 ChatLaw (2024, MIT) 民事类案检索 — 首选
            try:
                chatlaw_hits = list(self._case_client.search_chatlaw(
                    case_type=inp.case_type, limit=5))
                if chatlaw_hits:
                    class_refs.append(
                        f"ChatLaw (2024, MIT): {inp.case_type} 命中 {len(chatlaw_hits)} 条类案"
                    )
                    for i, hit in enumerate(chatlaw_hits[:3], 1):
                        if hit.fact:
                            class_refs.append(
                                f"  类案{i}: {hit.case_type} | {hit.fact[:80]}..."
                            )
            except Exception:
                pass

            # 3.2 cail2018 (刑事) — 仅做辅助, 不替代
            try:
                accusation = self._map_to_criminal_accusation(inp.case_type)
                if accusation:
                    stats = self._case_client.stats_by_accusation(sample=200)
                    if accusation in stats:
                        class_refs.append(
                            f"cail2018 (刑事辅助): {accusation} 样本频次 {stats[accusation]} (注: cail2018 仅刑事, 与{inp.case_type}民事案件不可直接对比)"
                        )
            except Exception:
                pass

        # 3.3 基线来源标注 (本地校准 vs 规则)
        class_refs.append(
            f"基线来源: {base_source} | {inp.case_type} 原告胜诉率 ≈ {base_rate:.0%} (置信: {base_conf})"
        )

        # 4. 期望值测算
        if inp.lawyer_role == "原告":
            expected_value = inp.amount * win_rate
        else:
            # 被告: 期望避免的赔偿
            expected_value = inp.amount * win_rate

        # 5. 推进成本
        lawyer_fee = estimate_lawyer_fee(inp.amount)
        # 诉讼费 (财产案件): ≤1万 50元; 1-10万 2.5%-1%; 10-20万 1%+ 200; >20万 0.5%+ 1200 ...
        # 简化: 0.5%-1.5%
        court_fee = max(0.005, inp.amount * 0.01)
        # 时间成本: 简易程序 3 个月, 普通程序 6 个月, 二审 +3 个月
        time_months = 3 if inp.amount < 30 else 6
        # 诉前调解不算案件时长, 诉中/庭前才加上已用时长
        if inp.procedural_stage in ("诉中", "庭前"):
            time_months += max(0, inp.case_age_months - 3)

        cost_to_proceed = {
            "lawyer_fee": lawyer_fee,
            "court_fee": round(court_fee, 2),
            "time_months": time_months,
            "opportunity": "中" if inp.amount < 50 else "高",
            "total": round(lawyer_fee + court_fee, 2),
        }

        # 6. 让幅区间
        # 律师角度: 原告建议从 high 起步逐步让步; 被告从 low 起步逐步加价
        if inp.lawyer_role == "原告":
            # 原告视角: 期望回收 = 标的额 × 胜诉率
            expected_recovery = inp.amount * win_rate
            settlement_recommend = min(inp.amount * 1.05, expected_recovery * 1.15)
            settlement_low = expected_recovery * 0.85  # 律师最低接受
            settlement_high = inp.amount * 1.10  # 略超标的(利息/违约金空间)
        else:
            # 被告视角: 期望赔偿 = 标的额 × (1 - 胜诉率)
            # 被告胜诉率高 → 实际赔少; 低 → 赔多
            defendant_pay_ratio = max(0.05, min(0.95, 1 - win_rate))
            expected_payment = inp.amount * defendant_pay_ratio
            # 被告第一次报价(试探低) = 期望赔 × 60-70%
            settlement_recommend = expected_payment * 0.65
            # 被告红线(不能高于此) = 期望赔 × 115% (考虑利息/诉讼费)
            settlement_high = expected_payment * 1.15
            # 被告理想(压到最低) = 标的额 × 20%
            settlement_low = inp.amount * 0.20

        # 7. 证据评估
        eva = self._assess_evidence(inp)

        # 8. 风险弱点
        weaknesses = self._identify_weaknesses(inp, win_rate)

        # 9. 底线策略
        bottom = self._bottom_line(inp, win_rate, settlement_low, settlement_high)

        # 10. 一句话策略
        strategy = self._strategy_summary(inp, win_rate, settlement_recommend)

        # 11. 案件摘要
        summary = self._case_summary(inp)

        # 12. 小标的特殊提示
        if inp.amount < 3:
            if inp.lawyer_role == "原告":
                small_case_warning = (
                    f"标的额仅 {inp.amount:.1f} 万元, 推进成本(律师费+诉讼费+时间)约 "
                    f"{cost_to_proceed['total']:.1f} 万元, "
                    f"占总争议额 {cost_to_proceed['total'] / max(0.01, inp.amount) * 100:.0f}%. "
                    f"**建议小额诉讼程序 (民诉法第162条) 或调解优先, 不建议按普通程序起诉**"
                )
            else:
                small_case_warning = (
                    f"标的额仅 {inp.amount:.1f} 万元, 原告起诉成本占比 "
                    f"{cost_to_proceed['total'] / max(0.01, inp.amount) * 100:.0f}%, "
                    f"**我方可主张对方撤回起诉或以小额程序快速结案**"
                )
        else:
            small_case_warning = ""

        # 时效/小标风险合并到弱点清单
        extra_weaknesses = []
        if statute_risk:
            extra_weaknesses.append(statute_risk)
        if small_case_warning:
            extra_weaknesses.append(small_case_warning)

        return MediationReport(
            case_summary=summary,
            win_rate_predicted=round(win_rate, 3),
            evidence_assessment=eva,
            settlement_low=round(settlement_low, 2),
            settlement_high=round(settlement_high, 2),
            settlement_recommend=round(settlement_recommend, 2),
            cost_to_proceed=cost_to_proceed,
            risk_weaknesses=weaknesses + extra_weaknesses,
            bottom_line=bottom,
            time_to_settle_months=time_months,
            class_case_refs=class_refs,
            strategy_summary=strategy,
            disclaimer=f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · PRC-Law v1.0.0",
        )

    def _assess_evidence(self, inp: CaseInput) -> str:
        if inp.evidence_plaintiff == "强" and inp.evidence_defendant == "弱":
            return "原告证据明显占优, 胜诉概率高"
        if inp.evidence_plaintiff == "弱" and inp.evidence_defendant == "强":
            return "被告证据明显占优, 胜诉概率低"
        if inp.evidence_plaintiff == inp.evidence_defendant:
            return f"双方证据相当 ({inp.evidence_plaintiff}), 胜负取决于庭审说服"
        return f"原告{inp.evidence_plaintiff} vs 被告{inp.evidence_defendant}, 略占{'原告' if inp.evidence_plaintiff == '强' else '被告'}"

    def _identify_weaknesses(self, inp: CaseInput, win_rate: float) -> list[str]:
        weaknesses = []
        if inp.evidence_plaintiff == "弱" and inp.lawyer_role == "原告":
            weaknesses.append("原告核心证据薄弱, 关键事实可能无法证明")
        if inp.evidence_defendant == "强" and inp.lawyer_role == "原告":
            weaknesses.append("被告已掌握反证, 反驳难度大")
        if not inp.has_written_contract and inp.case_type in ("合同纠纷", "借贷"):
            weaknesses.append("无书面合同/借据, 口头约定举证难")
        if inp.is_continued_performance and inp.lawyer_role == "原告":
            weaknesses.append("原告已履行部分义务, 被告可能主张质量瑕疵抗辩")
        if inp.amount > 100 and inp.case_type == "借贷":
            weaknesses.append("大额借贷缺乏转账凭证/流水, 被告可能否认收到款项")
        if inp.case_age_months > 12:
            weaknesses.append(f"案件已拖延 {inp.case_age_months} 个月, 时效风险上升")
        if inp.case_type == "侵权" and inp.lawyer_role == "原告":
            weaknesses.append("侵权案件因果关系举证复杂, 过错认定难度大")
        if not weaknesses:
            weaknesses.append("无明显程序/证据弱点, 焦点在庭审说服")
        return weaknesses

    def _bottom_line(self, inp: CaseInput, win_rate: float,
                     low: float, high: float) -> str:
        if inp.lawyer_role == "原告":
            return (
                f"**红线**: 不得低于 {low:.1f} 万元 (低于此线等于亏本调解)\n"
                f"**目标**: 争取 {high:.1f} 万元以上, 理想 {inp.amount * 0.9:.1f} 万元\n"
                f"**拒绝情形**: 对方坚持低于 {low:.1f} 万元 → 转入判决程序\n"
                f"**替代方案**: 分期付款 + 担保 + 律师费转嫁条款"
            )
        return (
            f"**红线**: 不得高于 {high:.1f} 万元 (高于此线等于败诉调解)\n"
            f"**目标**: 压到 {low:.1f} 万元以下, 理想 {inp.amount * 0.3:.1f} 万元\n"
            f"**拒绝情形**: 对方坚持高于 {high:.1f} 万元 → 转入判决程序\n"
            f"**替代方案**: 承认部分责任 + 减少赔偿范围 + 放弃其他请求"
        )

    def _strategy_summary(self, inp: CaseInput, win_rate: float,
                          recommend: float) -> str:
        # 极低胜诉率 → 优先调解/撤诉
        if win_rate < 0.15:
            return (
                f"⚠️ 极低胜诉率({win_rate:.0%}), 起诉风险极大. "
                f"建议: 1) 优先调解拿回部分标的; 2) 若调解不成, 评估撤诉/中止. "
                f"目标回收区间 {inp.amount * 0.05:.1f}~{inp.amount * 0.20:.1f} 万"
            )
        if inp.lawyer_role == "原告":
            if win_rate > 0.7:
                return f"高胜诉率({win_rate:.0%}), 第一次开价{inp.amount:.1f}万, 逐步让步至 {recommend:.1f}万, 不接受低于此底线"
            if win_rate > 0.5:
                return f"中等胜诉率({win_rate:.0%}), 第一次开价{inp.amount * 1.1:.1f}万(略超标的), 让步区间 {recommend - 5:.1f}~{recommend:.1f}万"
            return f"低胜诉率({win_rate:.0%}), 第一次开价{inp.amount:.1f}万, 准备较大幅度让步至 {recommend:.1f}万, 调解优先"
        if win_rate > 0.7:
            return f"被告胜诉率高({win_rate:.0%}), 第一次报价{inp.amount * 0.4:.1f}万, 对方接受即成交"
        if win_rate > 0.5:
            return f"被告中等胜诉({win_rate:.0%}), 第一次报价{inp.amount * 0.5:.1f}万, 让步至 {recommend:.1f}万"
        return f"被告胜诉低({win_rate:.0%}), 第一次报价{inp.amount * 0.7:.1f}万, 准备承担 {inp.amount:.1f}万+利息"

    def _case_summary(self, inp: CaseInput) -> str:
        return (
            f"**案由**: {inp.case_type}\n"
            f"**标的额**: {inp.amount:.1f} 万元\n"
            f"**程序阶段**: {inp.procedural_stage}调解\n"
            f"**律师代理**: {inp.lawyer_role}方\n"
            f"**原告诉求**: {inp.plaintiff_demand[:80]}\n"
            f"**被告答辩**: {inp.defendant_position[:80]}\n"
            f"**证据对比**: 原告{inp.evidence_plaintiff} / 被告{inp.evidence_defendant}\n"
            f"**案件时长**: {inp.case_age_months} 个月"
        )

    def _map_to_criminal_accusation(self, case_type: str) -> Optional[str]:
        """民事案由 → 可能关联的刑事罪名 (cail2018 用)"""
        mapping = {
            "借贷": "诈骗",
            "合同纠纷": "合同诈骗",
            "侵权": "故意伤害",
            "知识产权": "侵犯著作权",
        }
        return mapping.get(case_type)


# === CLI ===
def main():
    """CLI 入口: 接收 JSON 输入, 输出 Markdown 策略单"""
    import argparse
    parser = argparse.ArgumentParser(
        description="调解策略生成器")
    parser.add_argument("--input", "-i", help="JSON 输入文件")
    parser.add_argument("--amount", type=float, help="标的额 (万元)")
    parser.add_argument("--case-type", default="合同纠纷", help="案由")
    parser.add_argument("--role", default="原告", choices=["原告", "被告"],
                        help="律师代理方")
    parser.add_argument("--stage", default="诉前", choices=["诉前", "诉中", "庭前"])
    parser.add_argument("--ev-plaintiff", default="中", choices=["强", "中", "弱"])
    parser.add_argument("--ev-defendant", default="中", choices=["强", "中", "弱"])
    parser.add_argument("--demand", default="(未填)", help="原告诉求简述")
    parser.add_argument("--defense", default="(未填)", help="被告答辩要点")
    parser.add_argument("--output", "-o", default=None, help="输出文件")
    parser.add_argument("--calibration", help="本地校准 JSON (local_calibration.py 生成)")
    args = parser.parse_args()

    if args.input:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        inp = CaseInput(**data)
    else:
        if not args.amount:
            print("❌ 必须提供 --amount 或 --input", file=sys.stderr)
            sys.exit(1)
        inp = CaseInput(
            case_type=args.case_type,
            amount=args.amount,
            plaintiff_demand=args.demand,
            defendant_position=args.defense,
            evidence_plaintiff=args.ev_plaintiff,
            evidence_defendant=args.ev_defendant,
            procedural_stage=args.stage,
            lawyer_role=args.role,
        )

    calibration = None
    if args.calibration:
        calibration_path = Path(args.calibration)
        if not calibration_path.exists():
            print(f"❌ 校准文件不存在: {calibration_path}", file=sys.stderr)
            sys.exit(1)
        try:
            calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            n = len(calibration.get("by_case_type", {}))
            print(f"✓ 已加载本地校准: {n} 个案由 (来自 {calibration.get('cases.db', '?')})", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"❌ 校准 JSON 解析失败: {e}", file=sys.stderr)
            sys.exit(1)

    engine = MediationHintEngine(use_case_client=False, calibration=calibration)  # CLI 默认离线, 避免卡顿
    report = engine.generate(inp)
    md = report.to_markdown(amount=inp.amount)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"✅ 已生成: {args.output}")
    else:
        print(md)


if __name__ == "__main__":
    main()