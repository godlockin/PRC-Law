# 律鉴变更日志（CHANGELOG）

> 所有版本变更的官方记录。格式基于 [Keep a Changelog](https://keepachangelog.com/)。
> 律鉴使用语义化版本号：[主版本].[次版本].[修订号]。

## [未发布]

### 新增 · 独立数据集仓库 prc-law-data (v8.3.0)

PRC-Law 与法律数据集**解耦**, 新增 prc-law-data 独立仓库作为可选 submodule:

**仓库结构** (`/Users/chenchen/working/sourcecode/tools/law/cn_law_skill/prc-law-data/`):
- `data/statutes/<slug>.json` — **18525 部**法律全文 (民法典 1258 条, 公司法 213 条, 数据安全法 53 条, ...)
- `data/index/laws.jsonl` — 元数据索引
- `data/index/slug-map.json` — 中文名 → slug 映射 (18541 条)
- `data/index/articles.jsonl` — 法条反向索引 (中+阿拉伯双键)
- `scripts/import.py` — 从 3 个上游源合并导入
- `scripts/update.sh` — 增量更新 (上游版本检测)
- `scripts/serve.py` — HTTP 检索 API
- `scripts/verify.py` — 完整性校验 (sha256)

**数据来源** (公开 + 零 credit):
- [13098806890/laws-data](https://github.com/13098806890/laws-data) — 1945 文件 + 中英双语 + RAG 增强 (MIT)
- [LawRefBook/Laws](https://github.com/LawRefBook/Laws) — 1688 部法律 + 459 部司法解释 (1.8k⭐)
- [twang2218/chinese-law-and-regulations](https://huggingface.co/datasets/twang2218/chinese-law-and-regulations) — 22552 条 (Apache-2.0)

**接入 PRC-Law**:
- `vendor/prc-law-data` symlink (submodule 替身, 立即可用)
- `.gitmodules` 配置 (正式发布时切换为真正 submodule)
- `scripts/dataset_client.py` — 自动探测三种对接模式 (vendor / env var / HTTP)
- `scripts/retrieval_router.py` — 升级到 **6 级 fallback**:
  1. L1 元典/法宝 MCP (消耗 credit)
  2. **L2 prc-law-data 数据集 (零 credit, 默认首选)** ⭐
  3. L3 本地 cache
  4. L4 flk_npc 爬虫
  5. **L5 政府公开源 (spp.gov.cn + gov.cn)** ⭐
  6. L6 [待检索]

### 新增 · 政府公开源 fetcher

`scripts/fetch_gov_cn.py` — 实测可拉:
- 最高人民检察院 spp.gov.cn 指导性案例 (117 条最新批次可达)
- 国务院 gov.cn/zhengce/ 最新政策 (实测 6 条)
- 健康检查 + 列表模式 + 查询模式

### 标签新增
- `[已确认: prc-law-data 离线数据集 YYYY-MM-DD]` (L2)
- `[已确认: 最高人民检察院/国务院 YYYY-MM-DD]` (L5)

### 文档
- `_foundation/cn-fallback-source/SKILL.md` — 6 级 fallback 协议 + 三种对接模式说明
- `prc-law-data/README.md` — 独立仓库使用指南
- `prc-law-data/docs/schema.md` — 数据 schema 定义

### 量化覆盖
- 高频核心法律 **52/54 (96%)** 命中率
- 数据三法 + 配套 100% 覆盖
- 司法解释深度 (民法典配套解释 4 部全到位)

### 设计原则
- **解耦**: 数据集独立仓库, PRC-Law 仅保留调用脚本
- **可选**: 不强制依赖 prc-law-data, 不配置时自动 skip L2 走 L3+
- **按需加载**: 单部法律 ~200KB, 按 slug 拉取, 不预下载全部
- **零 credit**: 3 个公开源合并, 优先于商业 API
- **时效补丁**: 政府源 L5 补充离线数据集的快照滞后

### 自同步能力（Self-Sync）
律鉴 v8.2.0+ 起具备**联网自更新**能力，无需用户手动 `git pull`。

- **`scripts/upstream_check.py`** — 联网校验上游版本
  - HTTPS GET `api.github.com/repos/godlockin/PRC-Law/releases/latest`，fallback 到最新 commit SHA
  - 比对 `.claude-plugin/plugin.json` 的 `version` 字段
  - 写 `~/.prc-law/upstream-state.json`（atomic rename）
  - 1h 缓存，避免重复打 API
- **`scripts/upstream_sync.sh`** — 后台 git 同步
  - `mkdir` 原子锁防并发（macOS/Linux 通吃，规避 flock 缺失问题）
  - 自动跟随当前分支（`dev/feature` 分支也能同步到同名远端）
  - **`git pull --ff-only`** — 永不强覆盖本地改动
  - dirty tree 检测 → 自动放弃并写 `state.action = "manual"`
- **`hooks/hooks.json` SessionStart** — Claude 启动时 `nohup ... & disown` 触发校验，**零阻塞主技能**
- **`.github/workflows/self-sync.yml`** — 远端周扫
  - `cron: '0 3 * * 1'`（北京时间每周一 11:00）
  - push 触发自动 bump patch 版本
  - drift 时自动开 `self-sync-drift` issue（含去重）
- **`_foundation/cn-upstream-sync/SKILL.md`** — 只读展示层
  - 用户主动询问"检查更新/同步/upgrade plugin"时触发
  - 同 session 内只提示一次（按 `checked_at` 去重）

### 安全 · Argv Flag Smuggling 防护
修复了 background security review 报告的高危问题：

- `REPO` 白名单：`^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`
- `BRANCH` 白名单：`^[A-Za-z0-9._/-]{1,100}$`
- `git fetch --end-of-options` + `git pull --ff-only --end-of-options`：所有后续 arg 必须当 refspec 解析，无法注入 `-upload-pack` 等 flag

攻击向量测试：
```bash
UPSTREAM_BRANCH='-upload-pack=evil' bash scripts/upstream_sync.sh
# → exit 2, FATAL: invalid BRANCH='-upload-pack=evil'
```

### 设计原则
- **后台 + 静默**：所有网络/IO 走 detach，主技能路径不受影响
- **只 ff-only**：永远不强覆盖本地改动
- **跟随分支**：自动同步当前所在分支
- **多层安全**：白名单 + `--end-of-options` + mkdir-lock
- **失败容忍**：任何步骤失败只写 state 不抛异常

### 用户可见
- 状态查看：`cat ~/.prc-law/upstream-state.json`
- 字段：`local_version` / `remote_version` / `drift` / `action` (`sync`/`wait`/`manual`/`synced`) / `reason`
- 关闭同步：`export PRC_LAW_SKIP_SYNC=1` 或注释 `hooks/hooks.json` 的 SessionStart 段

---

## [9.2] · 2026-08-04

### 新增 · Word DOCX 输出
- **`scripts/md2docx.py`** — Markdown → Word DOCX 转换器
  - 中文字体支持（宋体/黑体/仿宋/等宽）
  - 标题分级（一/二/三级）
  - 表格（带边框）
  - 引用块（律师审阅闸高亮）
  - 列表（多级）
  - 代码块
- **`scripts/verify_docx.py`** — DOCX 验证（基于 LibreOffice）
  - 通过 LibreOffice 转 .txt 验证中文完整性
  - 解决 python-docx 读取 cell.text 的字符切割 bug
- **零 mock 数据原则**: 输出仅基于真实 demo 报告

### 已知问题
- python-docx 的 `cell.text` 读取在某些场景会切字符（已知 bug）
- 实际 DOCX 内容正确（LibreOffice 转换验证）
- 律鉴使用 LibreOffice 验证而非 python-docx 读取

### 使用

```bash
# 转换 demo 报告为 Word
python3 scripts/md2docx.py docs/demos/ND2-report.md output.docx

# 验证
python3 scripts/verify_docx.py output.docx
```

---

## [9.0] · 2026-08-04

### 新增 · 项目收尾文档
- **`CHANGELOG.md`** — 完整版本变更记录（v1.0-v9.0）
- **`CONTRIBUTING.md`** — 贡献指南（含技能开发规范、安全规范、借鉴合规要求）
- **`ROADMAP.md`** — 项目路线图（含短期/中期/长期目标）

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