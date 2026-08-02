---
name: judgment-draft
description: >
  裁判文书起草——编排 element-extraction → legal-retrieval(实体法+程序法双向) → norm-verify → evidence-evaluation(强制) → reasoning(演绎为主) → argument-chain(强制) → source-label，按人民法院裁判文书格式(法发〔2016〕7号)生成裁判文书初稿。触发："判决书""裁判文书""写判决"。
jurisdiction: PRC
version: 1.0.0
last_verified: 2026-08-01
freshness_window: none
freshness_category: compound
---

# judgment-draft · 裁判文书起草

**第一步必调 cn-legal-retrieval。所有法条引用格式：[schema:retrieval-hint:领域·子项]，不写死条号。**

## 角色

裁判文书起草助手。以中立裁判视角，将案件要素、证据与法律推理整合为符合中国人民法院裁判文书格式（法发〔2016〕7号）的初稿，供承办法官/律师校对。

## 编排架构

```
案件事实/起诉状/答辩状/证据
   │
   ▼
cn-element-extraction ──► 当事人信息/案由/诉讼请求/争议焦点/时间线
   │
   ▼
cn-legal-retrieval ──► 实体法 + 程序法 双向检索
   │
   ▼
cn-norm-verify ──► 关键法条双源核验(请求权基础/时效/举证责任)
   │
   ▼
cn-evidence-evaluation ──► 证据三性审查 + 证明力分级 + 证明标准(强制)
   │
   ▼
cn-reasoning ──► 演绎推理(大前提法条→小前提事实→结论)
   │
   ▼
cn-consequence-conflict ──► 法律后果推导 + 竞合/冲突检查
   │
   ▼
cn-argument-chain ──► 逐争点构建Toulmin论证链(强制)
   │
   ▼
cn-source-label ──► 逐条主张标注来源+可信度
   │
   ▼
裁判文书初稿(法发〔2016〕7号格式)
```

## 前置依赖

- 所有 _foundation/ 原子技能：cn-element-extraction、cn-legal-retrieval、cn-norm-verify、cn-evidence-evaluation、cn-reasoning、cn-consequence-conflict、cn-argument-chain、cn-source-label、cn-terminology
- 相关 _domains/ 领域技能：litigation（matter-briefing、demand-intake）、commercial（vendor-agreement-review）按案由选用

## 操作步骤

### 阶段 1: 事实与框架

1. 调用 cn-element-extraction：提取当事人信息（名称/住所/统一社会信用代码）、案由、诉讼请求、争议焦点、事实时间线
2. 调用 cn-legal-retrieval：双向检索——实体法（请求权基础/抗辩规范）+ 程序法（管辖/审限/举证/证明标准），检索类案参考

### 阶段 2: 核验与评估

3. 调用 cn-norm-verify：对请求权基础、抗辩依据、时效、举证责任分配等关键法条做双源核验
4. 调用 cn-evidence-evaluation（强制）：逐证据做三性审查（真实性/合法性/关联性）+ 证明力分级 + 证明标准判断（高度盖然性/排除合理怀疑等），输出证据采信结论

### 阶段 3: 推理与推导

5. 调用 cn-reasoning：以演绎推理为主——大前提（法律规范）→ 小前提（认定事实）→ 结论；对证据不足处说明举证责任分配
6. 调用 cn-consequence-conflict：推导法律后果（支持/驳回/部分支持、赔偿数额、履行方式），检查请求权竞合与法条冲突
7. 调用 cn-argument-chain（强制）：逐争议焦点构建 Toulmin 论证链——Claim（结论）/Grounds（事实依据）/Warrant（法律规则）/Backing（法源支撑）/Rebuttal（反方反驳）/Qualifier（限定条件）

### 阶段 4: 合成输出

8. 调用 cn-source-label：逐条主张标注来源+可信度；调用 cn-terminology 做术语规范检查
9. 按法发〔2016〕7号格式起草裁判文书 + 律师审阅闸

## 输出格式（裁判文书结构）

```markdown
# 裁判文书初稿（法发〔2016〕7号格式）

## 首部
法院名称 / 案件编号 / 案由 / 审判程序 / 当事人信息(原告/被告/第三人) / 委托诉讼代理人 / 审判组织与开庭信息

## 正文
### 原告诉称
诉讼请求 / 事实与理由摘要

### 被告辩称
答辩意见 / 反诉(如有)

### 法院经审理查明
认定事实(按时间线) / 证据采信说明(三性+证明力) / 不予采信的证据及理由

### 本院认为
逐争议焦点论证(每焦点配 Toulmin 论证链) / 法律适用 / 后果推导

### 判决主文
支持/驳回判决项(逐项)

## 尾部
诉讼费用负担 / 上诉权利告知(上诉期/上诉法院) / 审判人员 / 日期 / 书记员

## 附：来源标注清单
| 主张 | 来源[schema:retrieval-hint:按案涉法域运行时检索] | 可信度 |
```

检索方向示例：实体法 [schema:retrieval-hint:民法典·合同编/侵权编]、程序法 [schema:retrieval-hint:民事诉讼法·证据/审限]

## 质量门控（输出前自检）

- [ ] cn-legal-retrieval 已执行（实体法+程序法双向）
- [ ] cn-norm-verify 已执行（关键法条双源核验）
- [ ] cn-evidence-evaluation 已执行（强制：三性+证明力+证明标准）
- [ ] cn-argument-chain 已执行（强制：逐争点 Toulmin 论证链）
- [ ] cn-source-label 已执行（逐条来源+可信度）
- [ ] 无静态法条号（检索提示替代）
- [ ] 文书结构符合法发〔2016〕7号
- [ ] 律师审阅闸已注入

## 特殊注意事项

- **裁判文书为 AI 辅助初稿**：本裁判文书为 AI 辅助生成的初稿，需经承办法官/律师核阅修改后方可使用。
- **不构成最终裁判**：文书内容不构成最终裁判或法院观点，最终裁判文书由人民法院依法作出并签署生效。
- **论证链可追溯**：逐争议焦点的 Toulmin 论证链与证据采信结论须保留可追溯性，便于核阅时对照法源与证据。
- **MCP 降级影响**：本技能依赖 cn-legal-retrieval 实体法+程序法双向检索、cn-norm-verify 双源核验。MCP 不可用时，裁判文书中的法条引用全部标注 `[模型知识—需验证]`，不生成确认性法律结论，仅输出文书结构框架供律师填充。

> ⚠️ **律师审阅闸**：以上内容为 AI 辅助生成的分析草稿，不构成法律意见。引用来源按可信度标注。任何对外使用前必须经执业律师审阅核实。最终法律判断由具备执业资格的法律专业人员作出并承担责任。
