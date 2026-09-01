---
name: cn-mediation-hint
description: |
  调解策略生成器。当律师(原告/被告)在诉前/诉中/庭前调解时,需要快速判断:
  (1) 案件胜诉率预测 (2) 让幅区间 (3) 成本测算 (4) 风险弱点 (5) 底线策略。
  触发场景: "调解策略" / "这个案子能调解吗" / "诉前调解建议" / "让步空间" / "对方能接受多少"。
  基于规则引擎 + 类案基线胜诉率, 不需要 LLM 调用, 5 秒内输出策略单。
metadata:
  type: skill
  domain: litigation
  parent: dispute-resolution
  version: 1.0.0
  source: PRC-Law v9.0.0+
---

# cn-mediation-hint — 调解策略生成器

> ⚠️ **AI 辅助生成 — 律师审阅后使用** (上海律协指引 2025-08 §13)
> 本技能生成的策略建议**仅供律师参考**, 不构成法律意见。
> 律师使用前必须: 评估本案证据细节 / 校准本地类案库 / 与当事人充分沟通。

## 触发条件

用户在以下场景中提及即触发 (须明确律师代理方):
- "调解策略" / "诉前调解" / "诉中调解" / "庭前调解"
- "让步空间" / "对方能接受多少" / "调解底线"
- "我作为原告调解值不值" / "我作为被告调解值不值" / "打到底 vs 调解"
- "标的额 X 万, 案件类型 Y, 我代理原告/被告, 怎么谈"

> ⚠️ **触发歧义说明**: "调解值不值"对原告/被告含义完全不同, 必须明确 `lawyer_role` 字段 (原告/被告) 后再触发.

## 输入字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `case_type` | str | ✅ | 案由: 合同纠纷/劳动争议/侵权/婚姻/借贷/房屋买卖/建设工程/知识产权/医疗损害/交通事故 |
| `amount` | float | ✅ | 标的额(万元) |
| `lawyer_role` | str | ✅ | 律师代理: 原告/被告 |
| `procedural_stage` | str | ✅ | 诉前/诉中/庭前 |
| `evidence_plaintiff` | str | ⬜ | 原告证据: 强/中/弱 (默认中) |
| `evidence_defendant` | str | ⬜ | 被告证据: 强/中/弱 (默认中) |
| `plaintiff_demand` | str | ⬜ | 原告诉求简述 |
| `defendant_position` | str | ⬜ | 被告答辩要点 |
| `case_age_months` | int | ⬜ | 案件已用时长(月), 默认3 |
| `has_written_contract` | bool | ⬜ | 是否有书面合同, 默认true |
| `is_continued_performance` | bool | ⬜ | 是否继续履行型, 默认false |

## 输出

生成 **Markdown 调解策略单**, 包含 9 个章节:

1. 案件摘要 (案由/标的/阶段/代理方/诉求/答辩/证据)
2. 胜诉率预测 (基于规则引擎, 类案基线 + 证据强度调节)
3. 让幅建议区间 (下限/上限/初始报价)
4. 成本测算 (律师费/诉讼费/时间成本/机会成本)
5. 风险弱点清单 (程序/证据/时效风险点)
6. 底线策略 (红线/目标/拒绝情形/替代方案)
7. 预计耗时 (从当前位置到结案)
8. 类案先例引用 (cail2018 + 司法大数据基线)
9. 一句话策略总结

## 工作流

```
Step 1: 律师输入 (CLI 或 JSON)
   ↓
Step 2: scripts/mediation_hint.py 解析输入 → CaseInput dataclass
   ↓
Step 3: MediationHintEngine.generate(inp) 触发规则引擎
   ↓
Step 4: 输出 MediationReport → to_markdown()
   ↓
Step 5: 律师审阅 (人类把关)
   ↓
Step 6: 律师与当事人沟通, 决策调解方案
```

## 算法核心

```
base_rate = BASE_WIN_RATES[case_type]              # 类案基线胜诉率
adjust    = EVIDENCE_ADJUST[(ev_p, ev_d)]          # 证据强度调节
win_rate  = clamp(base_rate + adjust, 0.05, 0.95)  # 预测胜诉率

if role == 被告:
    pay_ratio = 1 - win_rate                       # 被告实际赔付比例
else:
    pay_ratio = win_rate

expected_recovery = amount × pay_ratio              # 期望回收/赔偿
settlement_recommend = expected_recovery × 1.15    # 调解首次报价(原告)
settlement_low = expected_recovery × 0.85           # 律师最低接受线
settlement_high = amount × 1.10                     # 略超标的(利息违约金)

# 成本
lawyer_fee = estimate_lawyer_fee(amount)            # 累进律师费
court_fee  = amount × 0.01                          # 简化诉讼费
time_months = 3 if amount < 30 else 6              # 简易/普通程序
```

## 类案基线胜诉率 (规则常量)

| 案由 | 原告胜诉率 | 时效 (月) | 来源 |
|------|-----------|----------|------|
| 合同纠纷 | 62% | 36 | 中国司法大数据 2023 |
| 劳动争议 | 78% | 12 | (劳动者倾向胜诉) |
| 侵权 | 55% | 36 | |
| 婚姻 | 45% | 24 | (离婚诉求驳回率较高) |
| 借贷 | 75% | 36 | (有借据情况下) |
| 房屋买卖 | 58% | 36 | |
| 建设工程 | 50% | 36 | |
| 知识产权 | 45% | 36 | |
| 医疗损害 | 40% | 36 | |
| 交通事故 | 70% | 36 | |

> **律师必读**: 这些是公开统计参考值, 实际案件必须结合本地类案库校准。
> 本地校准方法: 用 `cn-case-loader` 索引 100+ 类似案件, 统计实际胜诉率。

## 边界条件处理 (v1.0.1+)

| 触发条件 | 检测 | 算法响应 |
|---------|------|---------|
| **诉讼时效期间届满** | `case_age_months > STATUTE_OF_LIMITATIONS[case_type]` | 胜诉率强制 → 5%, 弱点清单加 "诉讼时效届满" (民法典第188条第1款) |
| **诉讼时效期间即将届满** | `case_age_months > 0.8 × 诉讼时效期间` | 胜诉率 -20%, 弱点清单加 "对方可能援引诉讼时效抗辩" |
| **已履行部分** | `is_continued_performance=True` (原告方) | 胜诉率 -10%, 弱点清单加 "瑕疵抗辩风险" |
| **小标的** | `amount < 3 万元` | 弱点清单加 "推进成本占比 X%, 建议小额程序/调解优先" |
| **极低胜诉率** | `win_rate < 15%` | 策略总结改为 "撤诉/中止优先, 目标回收 X-Y 万" |

> **律师复核要点**: 边界条件由算法自动识别, 但**所有"不建议起诉"建议必须律师人工复核**——例如时效中断/中止事由(民法典第195-196条)、共同过错分摊、未成年人/无行为能力等特殊主体。

## 证据强度调节

| 原告 \ 被告 | 强 | 中 | 弱 |
|------------|-----|-----|-----|
| **强** | +0.10 | +0.15 | +0.25 |
| **中** | -0.15 | 0.00 | +0.15 |
| **弱** | -0.25 | -0.15 | -0.05 |

## 用法

### CLI 模式

```bash
python3 scripts/mediation_hint.py \
    --amount 100 \
    --case-type "合同纠纷" \
    --role 原告 \
    --stage 诉前 \
    --demand "被告拖欠货款 100 万" \
    --defense "原告货物有质量问题" \
    --ev-plaintiff 强 \
    --ev-defendant 弱 \
    --output 调解策略-合同案.md
```

### JSON 输入

```bash
python3 scripts/mediation_hint.py -i case.json -o output.md
```

`case.json` 格式:
```json
{
  "case_type": "合同纠纷",
  "amount": 100.0,
  "lawyer_role": "原告",
  "procedural_stage": "诉前",
  "evidence_plaintiff": "强",
  "evidence_defendant": "弱",
  "plaintiff_demand": "被告拖欠货款 100 万",
  "defendant_position": "原告货物有质量问题",
  "case_age_months": 3,
  "has_written_contract": true,
  "is_continued_performance": false
}
```

### Python API

```python
from scripts.mediation_hint import MediationHintEngine, CaseInput

engine = MediationHintEngine()
inp = CaseInput(
    case_type="合同纠纷",
    amount=100.0,
    lawyer_role="原告",
    procedural_stage="诉前",
    evidence_plaintiff="强",
    evidence_defendant="弱",
    plaintiff_demand="被告拖欠货款 100 万",
    defendant_position="原告货物有质量问题",
)
report = engine.generate(inp)
print(report.to_markdown(amount=inp.amount))
```

## 输出示例

参考 `/tmp/m1.md` `/tmp/m2.md` `/tmp/m3.md` 三种典型场景。

## 数据依赖

- **必选**: 规则常量(已内置) + 律师输入
- **可选**: CaseClient (cail2018 streaming), 提供形式化类案引用, 不影响主策略生成
- **未来**: CAIL2019/2021 (民事案由数据, license: Research Only)
  - 若律师使用 cn-mediation-hint 处理民事案件, 推荐集成 zhang17173/Event-Extraction (GitHub, MIT) 做要素抽取

## 局限性与风险

1. **基线胜诉率为公开统计**, 不替代本地类案分析。律师使用前应:
   - 用 `cn-case-loader` 建立本地案件库 (cases.db)
   - 用 `cn-case-archive` (cail2018 / LaWGPT) 检索类案
   - 校准本案案由的本地胜诉率

2. **不处理复杂要素**: 案件细节(管辖/合同效力/特殊主体)未纳入算法,
   仅提供粗粒度策略骨架。律师必须补充细节判断。

3. **不预测对方行为**: 仅基于胜诉率推算"理性博弈", 实际调解还涉及
   对方情绪/商业关系/社会压力等, 这些无法量化。

4. **不能替代律师决策**: 律师审阅闸永远生效。律师必须在策略单基础上
   与当事人充分沟通, 确认调解授权范围。

## 与其他技能联动

| 技能 | 联动方式 |
|------|---------|
| `cn-case-archive` | 用 cail2018 类案补充类案先例引用 |
| `cn-case-loader` | 律师本地案件库, 校准胜诉率基线 |
| `cn-element-extraction` | 解析起诉状/答辩状, 自动填充 CaseInput |
| `cn-outcome-forecast` | 提供更精细的胜诉率预测(可替换规则引擎) |
| `cn-pleading-templates` | 调解协议生成 (md2template_docx.py) |
| `cn-source-label` | 引用类案时打 `[已确认]` / `[单源—需复核]` 标签 |

## 验证 (律师实操步骤)

1. **本地案件回测**: 拿过去 10 个已结案, 输入调解算法, 看策略建议 vs 实际结果偏差
2. **预期偏差**: 算法偏差 ≤ 15% 即可投入使用
3. **A/B 测试**: 新案件先用策略单, 再用经验判断, 对比调解成功率

## 借鉴合规声明

- 基础胜诉率常量: 来自中国司法大数据公开统计 (最高人民法院公报)
- 证据强度调节矩阵: 基于法律实务共识 + 团队经验
- 不引用任何外部项目的具体评分数据
- 不复制外部法律文书具体内容

---

> ⚠️ **律师审阅闸**: 本技能输出为调解策略**草稿**, 最终决策由律师 + 当事人共同作出。
> 调解协议生效前, 律师必须复核所有条款 (建议用 cn-pleading-templates 起草)。

## 修改记录

- 2026-09-01: v1.0.0 初始版本 (W5)
- 未来: 接入 CAIL2019/2021 + 律师本地案件库校准