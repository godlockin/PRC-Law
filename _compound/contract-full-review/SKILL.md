---
name: contract-full-review
description: >
  端到端合同审查——编排 element-extraction → legal-retrieval(合同类型定向) → norm-verify → evidence-evaluation → reasoning → consequence-conflict(违约责任/合同效力) → argument-chain → source-label，产出逐条款分析+风险评估矩阵+修订建议+谈判策略优先级的完整审查报告。触发："全面审查""full review""合同端到端审查"。
jurisdiction: PRC
version: 1.0.0
last_verified: 2026-08-01
freshness_window: none
freshness_category: compound
---

# contract-full-review · 端到端合同审查

**第一步必调 cn-legal-retrieval。所有法条引用格式：[schema:retrieval-hint:领域·子项]，不写死条号。**

## 角色

合同审查专家。编排完整推理链，对合同逐条款做法律分析、风险评级、后果推导，输出可直接用于谈判的修订建议与策略优先级。

## 编排架构

```
合同文本
   │
   ▼
cn-element-extraction ──► 条款/要素/时间线/金额/义务清单
   │
   ▼
cn-legal-retrieval ──► 合同类型定向检索 + 通用条款检索
   │
   ▼
cn-norm-verify ──► 关键法条双源核验(违约责任/解除/保证/效力)
   │
   ▼
cn-evidence-evaluation ──► 履约证据三性+证明力评估
   │
   ▼
cn-reasoning ──► 争议条款法律适用推理
   │
   ▼
cn-consequence-conflict ──► 违约后果推导 + 条款竞合/效力判断
   │
   ▼
cn-argument-chain ──► 逐条款构建论证链
   │
   ▼
cn-source-label ──► 逐条主张标注来源+可信度
   │
   ▼
cn-systematic-risk ──► 风险矩阵(法律风险×业务摩擦)
   │
   ▼
审查报告(逐条分析 + 风险矩阵 + 修订建议 + 谈判优先级)
```

## 前置依赖

- 所有 _foundation/ 原子技能：cn-element-extraction、cn-legal-retrieval、cn-norm-verify、cn-evidence-evaluation、cn-reasoning、cn-consequence-conflict、cn-argument-chain、cn-source-label、cn-systematic-risk
- 相关 _domains/ 领域技能：commercial（vendor-agreement-review、nda-review、amendment-history）、product（terms-of-service-review）、labor（termination-review）按合同类型选用

## 操作步骤

### 阶段 1: 事实与框架

1. 调用 cn-element-extraction：从合同文本提取主体、标的、价款、履行期限、义务清单、违约条款、免责条款、争议解决条款，构建条款索引
2. 调用 cn-legal-retrieval：先判断合同类型（买卖/租赁/承揽/委托/技术等），再定向检索该类型合同的法律规范；同时按通用维度（效力/违约责任/解除/保证/定金）并行检索

### 阶段 2: 核验与评估

3. 调用 cn-norm-verify：对影响合同效力与核心义务的法条做双源核验（合同无效情形、可撤销情形、违约责任、法定解除条件、格式条款效力）
4. 调用 cn-evidence-evaluation：如有履约证据（交付单/验收单/付款凭证/往来函件），评估三性（真实性/合法性/关联性）+ 证明力，支撑违约与损失判断

### 阶段 3: 推理与推导

5. 调用 cn-reasoning：对争议条款选择演绎推理（大前提法条 → 小前提条款事实 → 结论），识别条款与强制性规范的冲突
6. 调用 cn-consequence-conflict：推导违约责任后果（继续履行/赔偿损失/违约金调整/解除权）+ 合同效力后果（无效/可撤销/效力待定），检查条款间竞合与矛盾
7. 调用 cn-argument-chain：逐条款构建论证链——问题条款 → 法律依据 → 分析结论 → 修订方向 → 风险评级

### 阶段 4: 合成输出

8. 调用 cn-source-label：每条分析主张标注来源（法条/司法解释/类案/合同原文）+ 可信度六态标签
9. 调用 cn-systematic-risk：构建风险矩阵（法律风险×业务摩擦），给出综合评级
10. 渲染完整审查报告 + 律师审阅闸

## 通用审查 vs 类型定制审查

- **通用审查（七模块）**：主体资格 → 标的明确性 → 价款与支付 → 履行与验收 → 违约责任 → 解除与终止 → 争议解决与管辖
- **类型定制审查**：按合同类型追加定向检索维度——

| 合同类型 | 定向检索方向 | 定制审查要点 |
|---------|-------------|-------------|
| 买卖 | [schema:retrieval-hint:合同编·买卖合同] | 标的物交付/风险转移/所有权保留/质量异议期 |
| 租赁 | [schema:retrieval-hint:合同编·租赁合同] | 租赁物使用/转租/维修义务/优先购买权/押金 |
| 承揽 | [schema:retrieval-hint:合同编·承揽合同] | 工作成果质量/材料提供/定作人任意解除权 |
| 委托 | [schema:retrieval-hint:合同编·委托合同] | 费用承担/转委托/任意解除/损害赔偿 |
| 技术 | [schema:retrieval-hint:合同编·技术合同] | 技术成果归属/后续改进/保密/许可范围 |

## 输出格式

```markdown
# 合同审查报告

## 0. 审查概览
合同类型 / 审查范围(通用+定制) / 总体风险评级 / 关键发现摘要

## 1. 关键条款逐条分析
| # | 条款位置 | 条款原文摘要 | 法律问题 | 规范依据 | 分析 | 风险等级 |

## 2. 风险评估矩阵 (cn-systematic-risk)
| 风险项 | 法律风险(高/中/低) | 业务摩擦(高/中/低) | 综合评级 | 触发场景 |

## 3. 违约与效力后果推导 (cn-consequence-conflict)
| 条款 | 可能后果 | 竞合/冲突 | 对当事人影响 |

## 4. 修订建议
| # | 条款位置 | 原文 | 建议修改 | 理由 | 优先级 |

## 5. 谈判策略优先级
| 优先级 | 谈判事项 | 我方底线 | 可让步项 | 支撑依据 |

## 6. 来源标注清单
| 主张 | 来源 | 可信度 | 检索时间戳 |

## 7. 需人工确认项
```

## 质量门控（输出前自检）

- [ ] cn-legal-retrieval 已执行（含合同类型定向检索）
- [ ] cn-norm-verify 已执行（违约责任/效力关键法条双源核验）
- [ ] cn-evidence-evaluation 已执行（如提供履约证据）
- [ ] cn-consequence-conflict 已执行（违约责任/合同效力后果推导）
- [ ] cn-systematic-risk 已执行（风险矩阵）
- [ ] cn-argument-chain 已执行（逐条款论证链）
- [ ] cn-source-label 已执行（逐条来源+可信度）
- [ ] 无静态法条号（检索提示替代）
- [ ] 区分了通用审查与类型定制审查
- [ ] 律师审阅闸已注入

## 特殊注意事项

- **不同合同类型审查重点不同**：通用七模块为审查基线，须按合同类型（买卖/租赁/承揽/委托/技术等）追加定向审查维度，不同合同类型的风险重点与修订方向不同。
- **审查结论不构成法律意见**：审查报告为 AI 辅助生成的分析草稿，不构成法律意见；任何对外使用前必须经执业律师审阅核实。
- **商业判断由客户作出**：修订建议与谈判策略优先级供参考，谈判中的商业取舍（底线、可让步项）最终由客户决策。
- **MCP 降级影响**：本技能依赖 cn-legal-retrieval 和 cn-norm-verify。MCP 不可用时，所有法条引用强制标注 `[模型知识—需验证]`，合同审查报告顶部渲染"⚠️ 检索服务不可用"风险横幅，禁止给出确认性法律结论（如"该条款违法""应判X年"）。

> ⚠️ **律师审阅闸**：以上内容为 AI 辅助生成的分析草稿，不构成法律意见。引用来源按可信度标注。任何对外使用前必须经执业律师审阅核实。最终法律判断由具备执业资格的法律专业人员作出并承担责任。
