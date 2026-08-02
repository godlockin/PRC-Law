---
name: legal-opinion
description: >
  法律意见书生成——编排 element-extraction → legal-retrieval(四维检索) → norm-verify(关键法条强制双源) → evidence-evaluation → reasoning → consequence-conflict → argument-chain → source-label → 初稿 → 反向核验(逐引用回源) → 终稿。含假设前提/法律分析/结论与建议/风险提示/来源标注。触发："法律意见书""legal opinion""出具意见"。
jurisdiction: PRC
version: 1.0.0
last_verified: 2026-08-01
freshness_window: none
freshness_category: compound
---

# legal-opinion · 法律意见书

**第一步必调 cn-legal-retrieval。所有法条引用格式：[schema:retrieval-hint:领域·子项]，不写死条号。**

## 角色

法律意见书起草专家。面向委托人/决策者的正式法律意见，覆盖完整推理链并强制反向核验，确保每一条结论均可回溯到经双源核验的来源。

## 编排架构

```
事实与委托事项
   │
   ▼
cn-element-extraction ──► 事实/法律问题/假设前提/关键时间
   │
   ▼
cn-legal-retrieval ──► 四维检索(实体法/程序法/司法解释/类案)
   │
   ▼
cn-norm-verify ──► 关键法条强制双源核验
   │
   ▼
cn-evidence-evaluation ──► 证据三性+证明力+证明标准
   │
   ▼
cn-reasoning ──► 演绎为主+类比(如适用)
   │
   ▼
cn-consequence-conflict ──► 法律后果推导+冲突解决
   │
   ▼
cn-argument-chain ──► 逐争点Toulmin论证(含反驳预判+限定条件)
   │
   ▼
cn-source-label ──► 逐主张标注来源+可信度
   │
   ▼
意见书初稿
   │
   ▼
反向核验(逐引用回源确认) ──► 修正 → 终稿
```

## 前置依赖

- 所有 _foundation/ 原子技能：cn-element-extraction、cn-legal-retrieval、cn-norm-verify、cn-evidence-evaluation、cn-reasoning、cn-consequence-conflict、cn-argument-chain、cn-source-label
- 相关 _domains/ 领域技能：按事项领域选用——corporate（entity-compliance）、commercial（vendor-agreement-review）、privacy（pia-generation）、ip（clearance）、labor（termination-review）

## 操作步骤

### 阶段 1: 事实与框架

1. 调用 cn-element-extraction：提取委托事项、事实背景、法律问题清单，明确假设前提（未核实事实、文件效力假设）
2. 调用 cn-legal-retrieval：四维并行检索——实体法 / 程序法 / 司法解释 / 类案参考

### 阶段 2: 核验与评估

3. 调用 cn-norm-verify：对支撑结论的关键法条强制双源核验（多源一致→[已确认]；单源→[单源—需复核]；冲突→显式列出差异）
4. 调用 cn-evidence-evaluation：评估现有证据三性+证明力+证明标准，明确证据缺口对结论的影响

### 阶段 3: 推理与推导

5. 调用 cn-reasoning：以演绎推理为主，必要时辅以类比推理（类案规则迁移），逐法律问题得出中间结论
6. 调用 cn-consequence-conflict：推导每项法律问题的后果（有效/无效/违法/可行/有风险），处理请求权竞合与规范冲突
7. 调用 cn-argument-chain：逐争点构建 Toulmin 论证链，含 Rebuttal（反驳预判）与 Qualifier（限定条件，如"在……前提下"）

### 阶段 4: 合成输出与反向核验

8. 调用 cn-source-label：逐条主张标注来源+可信度六态标签
9. 生成意见书初稿
10. 反向核验（核心质量门控）：逐引用回源确认——每处法条/司法解释/案号回到检索报告核对原文与效力状态，标注"已回源确认/未回源/存疑"
11. 输出终稿 + 律师审阅闸

## 输出格式

```markdown
# 法律意见书

## 一、引言
委托人 / 受托事项 / 意见书目的 / 审阅文件范围 / 出具日期

## 二、事实概述
经审阅确认的事实 / 未核实事实（列入假设前提）

## 三、假设前提
- 文件签署真实有效、不存在未披露的重大事实
- 法律以出具日现行有效版本为准

## 四、法律分析（逐争议焦点）
### 焦点1：[问题]
#### (1) 法律依据 [schema:retrieval-hint:按法律依据领域运行时检索]
#### (2) 论证（Toulmin 链：结论/事实依据/法律规则/法源/反驳预判/限定）
#### (3) 结论
### 焦点2：[问题]
...

## 五、结论与建议
逐项结论（可行/不可行/有风险/附条件）+ 操作建议

## 六、风险提示
法律风险 / 时效与期间风险 / 证据缺口 / 政策变动风险

## 七、来源标注清单
| 引用 | 来源 | 效力状态 | 可信度 | 回源状态 |

## 八、反向核验报告
| 引用 | 核验方式 | 结果(已回源确认/未回源/存疑) | 修正动作 |

## 九、律师审阅闸
```

## 质量门控（输出前自检）

- [ ] cn-legal-retrieval 已执行（四维检索）
- [ ] cn-norm-verify 已执行（关键法条强制双源）
- [ ] cn-evidence-evaluation 已执行（三性+证明力+证明标准）
- [ ] cn-consequence-conflict 已执行（后果推导+冲突解决）
- [ ] cn-argument-chain 已执行（逐争点 Toulmin 链）
- [ ] cn-source-label 已执行（逐主张来源+可信度）
- [ ] **反向核验已执行（逐引用回源确认）——本技能区别于其他输出的核心门控**
- [ ] 无静态法条号（检索提示替代）
- [ ] 假设前提显式列出
- [ ] 律师审阅闸已注入

## 特殊注意事项

- **反向核验为意见书核心质量门控**：反向核验（逐引用回源确认）为本技能区别于其他输出的核心质量门控，每处法条/司法解释/案号须回到检索报告核对原文与效力状态。
- **未经反向核验不得作为正式法律意见**：未完成反向核验的意见书初稿不得作为正式法律意见对外出具；每处引用标注"已回源确认/未回源/存疑"供律师复核。
- **假设前提须显式**：未核实事实与文件效力假设须列入"假设前提"，不得作为已确认事实陈述。
- **MCP 降级影响**：本技能依赖 cn-legal-retrieval 四维检索、cn-norm-verify 强制双源核验。MCP 不可用时，反向核验步骤无法执行，法律意见书降级为"分析框架草稿"而非正式法律意见，所有法条标注 `[模型知识—需验证]`，输出顶部渲染"⚠️ 检索服务不可用——以下分析为框架草稿，不构成法律意见"。

> ⚠️ **律师审阅闸**：以上内容为 AI 辅助生成的分析草稿，不构成法律意见。引用来源按可信度标注。任何对外使用前必须经执业律师审阅核实。最终法律判断由具备执业资格的法律专业人员作出并承担责任。
