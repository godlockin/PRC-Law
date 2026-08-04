# 律鉴变更日志（CHANGELOG）

> 所有版本变更的官方记录。格式基于 [Keep a Changelog](https://keepachangelog.com/)。
> 律鉴使用语义化版本号：[主版本].[次版本].[修订号]。

## [未发布] · 计划中

### 计划
- v10.0: 多源交叉核验（北大法宝 MCP 集成）
- v10.1: Word DOCX 输出模板
- v10.2: 案件-模板-法条 知识图谱可视化
- v10.3: 在线 demo（Hugging Face Spaces 或 GitHub Pages）

---

## [8.6] · 2026-08-04

### 新增 · 6 个 ND Demo 全部端到端可跑
- **ND1**: 时间锚点法律测试（基于最高法指导案例 17 号）
- **ND2**: 167 号案复现（8 技能协同完整演示）
- **ND3**: 案例库检索与法院画像
- **ND4**: 170 号案公序良俗论证（6 阶解释审计）
- **ND5**: 法条跟踪与预警
- **ND6**: 合同全面审查 v2.0（6 Agent ORCHESTRATOR）

### 变更
- **核心原则**: 所有 demo 基于真实最高法指导案例 + 元典 API 实时检索，**零 mock 数据**
- ND6 重做：从"通用模板"改为"167 号案真实合同"——确保每个 demo 都有真实样例

### 修复
- 修复了 DEMOS.md 中 ND3-ND5 的"待实现"状态，更新为"已实测"
- 修复了 ND6 场景描述，与真实合同数据匹配

---

## [8.5] · 2026-08-04

### 新增 · ND3-ND5 端到端 demo
- **scripts/demo_nd3.py**: 案例库检索 + 杭州法院画像
- **scripts/demo_nd4.py**: 170 号公序良俗 6 阶解释
- **scripts/demo_nd5.py**: 法条跟踪预警

### 变更
- DEMOS.md 重新设计为"灵感和专业性"导向
- 每个 demo 增加"为什么重要"和"启发的用法"两段

---

## [8.4] · 2026-08-04

### 新增 · ND1 + ND2 端到端 demo
- **scripts/demo_nd1.py**: 1993 vs 2013 版消法对比
- **scripts/demo_nd2.py**: 167 号案 8 技能协同演示

### 变更
- 清理了 6 个旧的"输入模板"D1-D6（无法自动运行）
- 重新设计 DEMOS.md 为"灵感+专业"导向

---

## [8.3] · 2026-08-04

### 安全
- **关键修复**: 使用 `git filter-repo` 从所有历史 commit 中删除硬编码的元典 API Key
  - 涉及 commit: 50c59d3 起算的所有历史
  - 涉及文件: `.mcp.json` 和 `scripts/yuandian_mcp_bridge.py`
  - 历史重写: 50c59d3 → 2fce4d7（之后的 commit hash 全部重写）
- `.mcp.json` 加入 `.gitignore`
- 新建 `.mcp.json.example` 模板，引导用户正确配置
- 修复 `yuandian_mcp_bridge.py`：移除硬编码 fallback，改为强制要求环境变量

### 新增
- **QUICKSTART.md**: 5 分钟快速上手指南
- `.claude-plugin/plugin.json` 更新到 v8.2
- `commands/cn-law.md` 完整路由表

### 重要用户行动（紧急）
> ⚠️ 用户的元典 API Key（`sk_pnRWec1huctF8Hsnct5cziK4j2fKYkuJ`）曾在 50c59d3 commit 中被推送到公开仓库。
> **用户必须** 立即登录 [open.chineselaw.com](https://open.chineselaw.com) → 删旧 key → 建新 key。
> 旧的 key 应立即作废。

---

## [8.2] · 2026-08-04

### 新增 · 6 个跨能力 Demo 套件
- 6 个 demo 覆盖：合同审查/时间锚点/内部调查/法官画像/危机响应/学习路径
- 每个 demo 包含输入模板（基于公开法律模板）
- `scripts/demo_runner.py` 一键运行

---

## [8.0] · 2026-08-04

### 新增 · 知识图谱三向关联
- `scripts/kg_query.py` — 案件-模板-法条三向关联查询
- 基于元典真实检索 + 本地 SKILL.md 扫描
- README 收尾 + v5-v7 创新章节

---

## [7.0] · 2026-08-04

### 新增 · Benchmark CI 自动化
- `.github/workflows/benchmark.yml` GitHub Actions
- 每周一 02:00 UTC 自动跑
- 关键安全设计：`persist-credentials: false`、并发控制、upload-artifact

### 新增 · 自动化脚本
- `scripts/benchmark_summary.py` — 多维能力测试
- `scripts/statute_monitor.py` — 法条监听
- `scripts/judge_pattern.py` — 法院画像

---

## [6.0] · 2026-08-04

### 新增 · cn-argument-chain 升级
- 集成 6 阶解释审计（cn-interpretation-audit）
- 风险分叉推演（与 cn-consequence-conflict 双向打通）

---

## [5.0] · 2026-08-04

### 新增 · 三个 PRC-Law 独有创新
- **cn-statute-watchdog** — 法条修订跟踪与主动预警
- **cn-judge-pattern** — 法官/法院裁判倾向分析
- **cn-interpretation-audit** — 6 阶法律解释方法强制审计

---

## [4.0] · 2026-08-04

### 新增 · 借鉴合规原则全局化
- ORCHESTRATOR 多 Agent 架构（借鉴 Contract-Reviewer-Eval）
- W1/W2 双闸门（借鉴 gutachten-civil-case）
- 能力槽降级体系
- 请求权基础方法论（cn-civil-claim-analysis）

### 重要变更
- **明确借鉴原则**: 仅借鉴可观察的架构模式，不引入 mock 数据、不引用未经第三方审核的自评数据
- CLAUDE.md 新增"借鉴真实性与可追溯原则"全局章节

---

## [3.0] · 2026-08-02

### 新增 · 152 个 SKILL.md（v3.0 → v8.6 累计）
- 10 领域 + 9 法务专属 = 19 个领域
- 6 个复合技能
- 17 个基础能力

### 新增 · 9 个法务专属技能
- corporate: contract-template-management, contract-approval-workflow, outside-counsel-management, legal-budget-tracking
- regulatory: compliance-training, crisis-response, legal-bp, knowledge-management, compliance-self-audit

### 新增 · 三个独有创新机制
- **时间锚点机制**: cn-legal-retrieval 的 `refer_date` 参数锁定行为时有效的法条版本
- **风险分叉推演**: cn-consequence-conflict 推演最有利/最可能/最不利三场景
- **Toulmin 论证链**: cn-argument-chain 强制 6 要素 + 7 项自检清单

### Benchmark
- 5 个最高法指导案例 vs AI 推理
- 综合得分 92% (18.4/20)
- 零方向性错误
- 关键发现：法条版本时效 100% 正确（refer_date 根治"误用新法判定旧案"）

---

## [1.0] · 2026-08-02 · 初始版本

### 新增
- 94 个 SKILL.md（10 领域）
- 6 个复合编排
- 5 个评测文件 + 降级策略
- 6 个工具脚本（CI/验证/缓存/覆盖度）
- Apache-2.0 协议 + plugin.json

### 已知问题（v3.0 已修复）
- ⚠️ 50c59d3 commit 中硬编码了元典 API Key
  - **v8.3 已用 git filter-repo 完整删除**
  - **v8.3 历史重写**: 50c59d3 → 2fce4d7

---

## 版本对照

| 版本 | SKILL.md | 关键能力 | 状态 |
|------|---------:|---------|------|
| v1.0 | 94 | 基础 15 技能 | 历史 |
| v3.0 | 140 | +时间锚点+风险分叉+Toulmin | 已完成 |
| v4.0 | 144 | +ORCHESTRATOR+双闸门+请求权基础 | 已完成 |
| v5.0 | 147 | +法条跟踪+法官画像+解释审计 | 已完成 |
| v6.0 | 147 | +6 脚本 | 已完成 |
| v7.0 | 147 | +CI 工作流 | 已完成 |
| v8.0 | 149 | +知识图谱+解读 | 已完成 |
| v8.2 | 149 | +6 demo 框架 | 已完成 |
| v8.3 | 149 | +QUICKSTART+安全治理 | 已完成 |
| v8.4 | 149 | +ND1/ND2 端到端 | 已完成 |
| v8.5 | 149 | +ND3-ND5 端到端 | 已完成 |
| v8.6 | 149 | +ND6 端到端 | 当前 |

## 数据来源统计

| 数据源 | 数量 | 状态 |
|--------|------|:----:|
| 最高法指导案例（已入库） | 9 个 | ✅ |
| 民法典（已缓存） | 1 部 | ✅ |
| 真实可端到端 demo | 6 个 | ✅ |
| 自动化脚本 | 6 个 | ✅ |
| 复合技能编排 | 6 个 | ✅ |
| 基础能力 | 17 个 | ✅ |
| 领域技能 | 132 个 | ✅ |
| **总计** | **149 SKILL.md** | — |

---

> 详细技术实现见 [README.md](README.md)，快速上手见 [QUICKSTART.md](QUICKSTART.md)，演示见 [docs/DEMOS.md](docs/DEMOS.md)。