---
jurisdiction: PRC
last_updated: 2026-08-01
---

# 律鉴（PRC-Law）— 中国大陆法律 Agent Skills

> 中国大陆成文法体系下的法律 AI 技能库。检索即门禁、双源交叉核验、律师审阅闸。
> 覆盖 10 领域 140+ 技能：商事合同 / 公司并购 / 劳动用工 / 隐私数据 / 产品合规 /
> 知识产权 / 争议解决 / 监管合规 / AI 治理 / 法学教育。

---

## 👤 关于作者

**搞 AI 的陈老师** — 独立开发者，资深 AI 从业者，深耕法律科技与 AI Agent 工程。

| 公众号「搞 AI 的陈老师」 | 个人微信 |
|:---:|:---:|
| ![公众号](docs/assets/qrcode-mp.jpg) | ![个人微信](docs/assets/qrcode-wechat.jpg) |
| 第一手更新 · AI + 法律实战 | 读者群 · 技术交流 · 项目咨询 |

🙏 **如果律鉴对你的工作有帮助，欢迎赞赏支持持续维护**（赞赏备注「PRC-Law」可加入优先反馈名单）。

---

## 三条硬护栏（所有技能强制执行）

### 护栏 1：检索即门禁
任何法条、案号、司法解释、时效数字，必须在运行时通过 MCP 检索工具获取。
SKILL.md 中不写死具体条号，统一使用 `[schema:retrieval-hint:领域·子项]` 占位。
第一步必调 `_foundation/legal-retrieval`。

### 护栏 2：双源交叉核验
关键法条（时效/刑期/除斥期间/举证责任）强制多源比对。
- **元典** (`open.chineselaw.com/open/*`) + **北大法宝** (`apim-gateway.pkulaw.com/*`) 双商业 API
- 二者一致 → `[已确认: 元典+北大法宝 {date}]`
- 仅元典 → `[单源—需复核: 元典 {date}]`
- 仅法宝 → `[单源—需复核: 北大法宝 {date}]`
- 都无 → 降级到 `prc-law-data` 本地数据集 → 政府公开源 → `[待检索]`
- 冲突时显式列出多源差异
- 默认共享月配额 `PRC_LAW_YUANDIAN_QUOTA=5000` (元典 + 法宝合计),超限静默降级

### 护栏 3：律师审阅闸
所有输出末尾强制渲染：
> ⚠️ **律师审阅闸**：以上内容为 AI 辅助生成的分析草稿，不构成法律意见。
> 引用来源按可信度标注。任何对外使用前必须经执业律师审阅核实。
> 最终法律判断由具备执业资格的法律专业人员作出并承担责任。

## 实践画像

**法域:** 中国大陆成文法
**实践类型:** [待填写 — 法务商业 / 律所诉讼 / 产品律师 / 法学教育]
**行业:** [待填写]
**团队规模:** [待填写]
**工具熟练度:** [待填写]
**案例库路径:** [待填写 — 本地案例库目录，如 /Users/xxx/cases/]

## MCP 连接器

| 服务 | Transport | 用途 |
|------|-----------|------|
| yuandian | stdio bridge `scripts/yuandian_mcp_bridge.py` → `open.chineselaw.com/open/*` | 法令/案例/企业 REST API |
| pkulaw | HTTPS `apim-gw.pkulaw.com/{SERVICE_ID}/mcp` | 北大法宝检索 |

## 全局输出规范

- 每条法律引用标注来源标签：`[已确认]` / `[单源—需复核]` / `[待检索]` / `[模型知识—需验证]`
- 区分来源锚定断言与模型推断，后者前缀 `[模型推断]`
- 引用原文逐字引用；改述时不用引号
- 管辖地假设显式标注
- 无法锚定到来源的主张，明确说明而非编造引用
- **领域和复合技能的"输出格式"段必须包含"来源标注"列或字段**
- **复合技能必须在操作步骤中显式调用 cn-source-label**

## 推理链完整性

复合技能编排必须覆盖完整推理链，不得跳过关键节点：

```
事实输入 → 要素提取(cn-element-extraction) → 法律检索(cn-legal-retrieval) → 规范核验(cn-norm-verify)
  → 证据评估(cn-evidence-evaluation) → 法律推理(cn-reasoning)
  → 后果推导+风险分叉推演(cn-consequence-conflict) → 结果预测(cn-outcome-forecast)
  → 论证构建(cn-argument-chain) → 来源标注(cn-source-label) → 结论
```

- **judgment-draft / legal-opinion** 必须调用 cn-evidence-evaluation + cn-argument-chain + cn-outcome-forecast
- **contract-full-review** 必须调用 cn-consequence-conflict + cn-systematic-risk
- **settlement-evaluation** 必须调用 cn-outcome-forecast
- 其他复合技能至少调用 cn-source-label

## 降级策略

MCP 全部不可用时（L2 降级）：
- 所有法律结论强制标注 `[模型知识—需验证]`
- 复合/领域技能顶部渲染风险横幅："⚠️ 检索服务不可用，以下分析基于模型训练知识，法条可能已过时或废止"
- 禁止给出确认性法律结论（如"该行为违法""应判X年"）

MCP 可用的正常模式：按 references/degradation-strategy.md 执行。

## 案例库

用户提供的本地案例（.docx/.pdf/.txt）通过 `cn-case-loader` 解析入库。
SQLite 索引存储在 `cases.db`，全文搜索免 LLM 零幻觉。
增量追加：`/cn-case-loader <新目录> --db cases.db`

## 冷启动

运行 `_foundation/cold-start/SKILL.md` 完成实践画像填充。
首次使用建议先加载案例库，再配置 MCP 连接器。

## 借鉴真实性与可追溯原则（全局强制）

任何从外部项目（GitHub、HuggingFace、学术论文、商业产品等）借鉴内容时，必须遵守以下原则：

### 三不原则

1. **不引入 mock 数据**：禁止引入外部项目的示例案件、示例合同、示例客户名称、示例评分数据
2. **不引用自评数据**：禁止引用外部项目 README 的自评准确率/评分/排名等未经第三方审核的数据
3. **不抄具体内容**：禁止复制外部项目的合同文本、法律文书、判决书等具体文本内容

### 可借鉴范围

- ✅ 架构模式（如 ORCHESTRATOR 多 Agent、双闸门设计、能力槽体系）
- ✅ 方法论框架（如请求权基础三层四步、鉴定式写作风格）
- ✅ 目录结构（如 12 目录案件模板、能力槽抽象）
- ✅ 评估维度（如 5 维评分、能力 Gap 分析方法）
- ✅ 设计原则（如 rubric-blind 防泄漏、降级策略）

### 必须标注

所有借鉴内容必须在 SKILL.md 中：
- 明确标注来源仓库地址（如有）
- 标注"借鉴合规声明"，说明借鉴的范围与未借鉴的内容
- 标注任何来自外部 README 的数据为"作者自评、未经第三方审核"
- 不作为能力背书或对外宣传依据

### 审计追溯

借鉴的来源信息应在每个受影响的 SKILL.md 中显式列出，使用者可独立访问原仓库审计原始内容。

---

> ⚠️ **律师审阅闸**: PRC-Law 为 AI 辅助法律分析系统，其输出为分析草稿，不构成法律意见。系统中所有法律引用标注来源可信度标签，对外使用前必须经执业律师审阅核实。所有借鉴的外部项目内容**仅供参考和架构灵感**，最终法律判断由具备执业资格的法律专业人员作出并承担责任。

## 技能触发

本仓库技能遵循 Claude Code Agent Skills spec。
所有原子技能以 `cn-` 前缀命名，按 frontmatter description 自动触发。
领域技能在 `_domains/<领域>/skills/` 下，按业务关键词触发。
复合技能在 `_compound/` 下，编排多个原子/领域技能。
