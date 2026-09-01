# PRC-Law 部署架构 (2026-09 修订)

> 三层分离 + WorkBuddy 入口。数据外挂化, 律师私有层本地化, 入口非 CLI 化。

## 三层架构总览

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: 公共数据层 — github.com/godlockin/prc-law-data │
│ - 法规 (民法典/公司法/劳动法...)                          │
│ - 类案 (ChatLaw/LeCaRDv2/cail2018)                       │
│ - 自动同步: GitHub Actions cron (周级)                  │
│ - 自动构建: SQLite + JSON, 按 slug 分文件               │
│ - 许可: MIT (代码) / 公共领域 (法律文本)                │
└─────────────────────────────────────────────────────────┘
                          │ git submodule / HTTP / sibling
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 2: PRC-Law Skills (本仓库)                        │
│ - 24 atomic + 6 compound + 10 domain skills             │
│ - scripts/ (mediation_hint / deadline_monitor / ...)    │
│ - retrieval_router 6 级降级链                           │
│ - cn-mediation-hint + cn-pleading-templates (W4/W5)    │
│ - cn-case-archive (本地案件索引)                       │
└─────────────────────────────────────────────────────────┘
                          │ Claude Code Skill 协议
                          ↓ (WorkBuddy / 类似工具加载)
┌─────────────────────────────────────────────────────────┐
│ Layer 3: 律师私有层 (本地)                              │
│ - matters/M-XXX/ (案件目录, 每案件一份)                │
│ - cases.db (本地类案, SQLite + FTS5)                  │
│ - alerts/ (提醒输出)                                   │
│ - .lawyer_profile (律师画像)                          │
│ - 可挂载 NAS/SMB 网盘 (未来, 团队共享)                │
└─────────────────────────────────────────────────────────┘
                          ↑ 由 (Layer 4) 律师调用
┌─────────────────────────────────────────────────────────┐
│ Layer 4: 律师入口 — WorkBuddy / 类似 online/offline 工具│
│ - 自然语言触发 (不用 CLI / 不用 VSCode)                │
│ - 加载 PRC-Law skills (Claude Code 协议)              │
│ - 律师说一句话, 工具自动调 skill + 读私有层数据        │
└─────────────────────────────────────────────────────────┘
```

## Layer 1 — 公共数据层 (prc-law-data)

仓库: <https://github.com/godlockin/prc-law-data>

### 数据内容
- 法规 JSON (按 slug, ~460 MB)
- 法规索引 laws.jsonl (~1MB, 常驻内存)
- 类案索引 (cail2018/ChatLaw/LeCaRDv2 streaming 缓存)
- 数据许可证、来源、上游版本号

### 自动同步机制
- **GitHub Actions cron**: 每周日 02:00 (UTC+8) 跑
- **增量更新**: 比对 `updated_at`, 只拉新增/修改
- **手动触发**: `Actions` → Run workflow
- **失败不阻塞**: 单条 import 失败不影响其他

### 三种部署模式 (PRC-Law 集成)

| 模式 | 适用场景 | 配置命令 |
|------|---------|---------|
| **Git submodule** | 个人/律所, 长期稳定 | `git submodule add https://github.com/godlockin/prc-law-data vendor/prc-law-data` |
| **Sibling 仓库** | 开发/调试 | clone 到 `../prc-law-data/` |
| **HTTP 镜像** | 远程访问 | 配置 `PRC_LAW_DATA_HTTP_URL` |

代码自动按优先级探测 (`scripts/dataset_client.py` `CANDIDATE_DIRS`):
1. `vendor/prc-law-data/data/` (submodule)
2. `../prc-law-data/data/` (sibling)
3. `~/.../prc-law-data/data/` (硬编码工作区, 调试用)

### 数据落地位置
```
prc-law-data/
├── data/
│ ├── statutes/ # 法条 JSON (按 slug)
│ │ ├── civil-code.json   # 民法典 (含失效日期/版本号)
│ │ ├── company-law.json  # 公司法 (2024-07-01 修订)
│ │ └── ...
│ ├── index/                # 轻量索引 (常驻内存)
│ │ ├── laws.jsonl         # 所有法律元数据
│ │ └── articles.jsonl     # 法条-法律映射
│ └── sources/              # 上游原始缓存 (gitignored)
├── scripts/
│ ├── import.py             # 从上游导入并标准化
│ ├── update.sh            # 增量更新
│ └── serve.py             # HTTP 检索 API
└── .github/workflows/
 └── sync.yml               # 定时同步
```

## Layer 2 — PRC-Law Skills

仓库: <https://github.com/godlockin/PRC-Law>

### 能力清单
- **Foundation (24)**: legal-retrieval / norm-verify / argument-chain / evidence-evaluation / source-label / cn-case-archive / cn-mediation-hint / ...
- **Compound (6)**: judgment-draft / legal-opinion / contract-full-review / due-diligence-grid / claim-chart / lifecycle-planning
- **Domain (10)**: commercial / corporate / labor / privacy / product / IP / litigation / regulatory / ai-governance / legal-edu

### 关键脚本 (34 个)
- `mediation_hint.py` (W5) — 调解策略生成
- `deadline_monitor.py` (W7.2) — 时效预警
- `local_calibration.py` (W7.1) — 本地类案校准
- `retrieval_router.py` (W6) — 6 级降级检索
- `case_indexer.py` — 案件索引到 SQLite
- `md2template_docx.py` (W4) — 文书 Word 生成
- `lawyer_workflow.py` (W7.5) — 5 步律师工作流
- `dataset_client.py` — prc-law-data 客户端
- `case_client.py` — HF 类案 streaming (cail2018/ChatLaw/LeCaRDv2)

### 与数据外挂集成
```python
# scripts/dataset_client.py 启动时自动探测
from dataset_client import DatasetClient
ds = DatasetClient()
hit = ds.fetch("民法典", "第577条")
# 命中: 从 prc-law-data/data/statutes/civil-code.json 加载
# 未命中: 返回 None, 触发 retrieval_router 下一级
```

### 与商业 API 集成 (元典/法宝)

**W8.2 实现**:`scripts/retrieval_router.py` 的 `try_yuandian_pkulaw` 已存在占位,W8.2 补完 MCP 协议调用 + credit 受控降级。

策略:
- **主路径**: 元典 MCP (商业, credit 受控)
- **降级**: credit 用完 → prc-law-data → ChatLaw → 本地 cases.db → 规则基线

## Layer 3 — 律师私有层 (本地)

> ⚠️ **核心原则**: 客户案卷信息永远不离开律师本机。

### 目录结构 (推荐)

```
~/lawyer-work/
├── .lawyer_profile            # 律师画像 (json, 单文件)
├── matters/                   # 案件目录 (每案件一个子目录)
│   ├── M-2026-001/
│   │   ├── intake.json        # 接案记录
│   │   ├── strategy.md        # 调解策略单
│   │   ├── statute.json       # 法条核验结果
│   │   ├── pleading.docx      # Word 文书
│   │   ├── events.log         # 案件事件流 (append-only)
│   │   └── notes.md           # 律师批注
│   └── M-2026-002/
├── cases.db                   # 本地类案 (SQLite + FTS5)
├── alerts/                    # 提醒输出 (cron 写入)
│   ├── deadline-2026-09-15.md
│   └── statute-change-2026-09.md
└── .config/
 └── prc-law-config.json        # 律师个性化配置
```

### 未来团队共享

```
律所 NAS/SMB 网盘
├── shared/                    # 律所共享 (法规 cache, 律所规则)
│ ├── statutes/                # 法规 cache (镜像 prc-law-data)
│ └── firm_rules.json          # 律所规则 (基线胜诉率调整)
└── private/
    └── {lawyer-id}/           # 每律师私有
        ├── matters/            # 案件
        └── cases.db           # 类案
```

- **法规 cache 共享**: 律所 5 个人用同一份法规 cache, 减少拉取
- **律所规则共享**: firm_rules.json 调整默认胜诉率(按律所历史调整)
- **案件/类案私有**: 律师各自保管, 不上传律所共享

### 数据安全
- ✅ 案件目录 `chmod 700` (仅律师本人可读)
- ✅ cases.db 不上传 git
- ✅ 网盘加密 (BitLocker / FileVault)
- ⚠️ 客户案卷绝不导出 (除非律所合规审批)

## Layer 4 — 律师入口 (WorkBuddy / 类似)

> **关键转变**: 律师不需要用 CLI / VSCode, 通过类 WorkBuddy 工具加载 skills。

### WorkBuddy (腾讯工作台) 集成方式

WorkBuddy 加载 PRC-Law skills 通过 **Claude Code Skill 协议**:
- WorkBuddy 内嵌 Claude Code runtime
- 律师在 WorkBuddy 界面输入自然语言
- WorkBuddy 自动匹配 PRC-Law skills
- 调起 skill 后, skill 读律师私有层 (matters/cases.db)
- 输出 Markdown/Word 文档到律师私有层

### 律师日常使用流程

```
律师在 WorkBuddy 输入:
> 这个案子能调解吗? 标的 200 万, 合同纠纷, 我证据强对方弱

WorkBuddy 自动调:
1. cn-mediation-hint skill
2. 读 ~/.lawyer_work/matters/ (律师案件目录)
3. 读 cases.db (本地类案)
4. 输出调解策略单 (Markdown)
5. 写入 matters/M-XXX/strategy.md
```

律师**完全不需要**:
- ❌ 打开 VSCode
- ❌ 跑 Python 脚本
- ❌ 读 SKILL.md

### WorkBuddy 加载 skills 的方式

`prc-law.skills.json` (清单文件, WorkBuddy 加载):
```json
{
  "version": "1.0.0",
  "skills": [
    {"name": "cn-mediation-hint", "path": "_domains/litigation/skills/cn-mediation-hint/SKILL.md"},
    {"name": "cn-pleading-templates", "path": "_domains/litigation/skills/cn-pleading-templates/SKILL.md"},
    {"name": "cn-case-archive", "path": "_foundation/cn-case-archive/SKILL.md"},
    {"name": "deadline-monitor", "path": "scripts/deadline_monitor.py", "trigger": "cron"}
  ],
  "data_layer": {
    "type": "git-submodule",
    "url": "https://github.com/godlockin/prc-law-data",
    "path": "vendor/prc-law-data/data"
  },
  "private_layer": {
    "lawyer_workspace": "~/lawyer-work"
  }
}
```

WorkBuddy 启动序列:
1. 读取 `prc-law.skills.json`
2. git submodule update (拉数据外挂)
3. 加载 SKILL.md 到 Claude Code runtime
4. 律师私有目录 `~/lawyer-work/` 挂载到 skill context
5. cron 启动 deadline_monitor

## 数据流示例: 律师处理一个案件

```
律师在 WorkBuddy 输入:
> M-2026-001 接案, 合同纠纷, 标的 200 万, 我方强证据对方弱

↓ WorkBuddy → Claude Code

1. cn-mediation-hint skill 触发
   ↓ 读 Layer 1: vendor/prc-law-data/data/statutes/civil-code.json
   ↓ 读 Layer 3: ~/lawyer-work/cases.db (本地类案)
   ↓ 计算胜诉率 87% (本地校准 + 规则基线)
   ↓ 输出: matters/M-2026-001/strategy.md

2. cn-pleading-templates skill 触发
   ↓ 选模板: templates/lawyer-letter.md
   ↓ LLM 抽取字段 (从 strategy.md 自动填充)
   ↓ 输出: matters/M-2026-001/lawyer-letter.docx

3. cron 触发 deadline_monitor
   ↓ 读 matters/M-2026-001/intake.json
   ↓ 计算 15 天上诉期
   ↓ 输出: alerts/deadline-M-2026-001.md
   ↓ WorkBuddy 推送提醒

4. 律师 WorkBuddy 看到:
   - 调解策略单 (Markdown)
   - 律师函 (Word)
   - 时效提醒 (倒计时)
```

## 跨层数据流向

| 流向 | 数据 | 频率 |
|  | 法条 / 类案索引 | 启动时 + 按需 |
| Layer 2 → Layer 3 | 策略单 / 文书 / 提醒 | 每个 skill 执行 |
| Layer 3 → Layer 1 | 律师本地校准 (本地规则) | 周级 |
| Layer 4 → Layer 2 | 自然语言 → skill 触发 | 每次律师输入 |
| Layer 4 → Layer 3 | 案件索引 / 案件详情 | 每次律师输入 |

## 安全边界

```
外部世界         Layer 4        Layer 2          Layer 1        Layer 3
─────────        ────────       ────────         ────────       ────────
律师输入     →   WorkBuddy  →   PRC-Law      →   prc-law-data   律师私有
                              (skills)         (公开)           (本地)

不进入: 客户案卷 / 律师案件 → prc-law-data (公开仓库, 不存私有数据)
```

**客户案卷信息**:
- ✅ 只在 Layer 3 (本地)
- ✅ WorkBuddy 加密通道传给 Layer 2 (skill)
- ❌ **绝不**上传到 Layer 1 (prc-law-data 公开)
- ❌ **绝不**进入 Layer 2 任何输出(except 律师本人审阅过的策略单)

## 安装与部署

### 律师本地部署 (5 步)

```bash
# 1. 安装 WorkBuddy (假设已装)
# 2. 在 WorkBuddy 配置 PRC-Law skill 源
#    指向: https://github.com/godlockin/PRC-Law
# 3. WorkBuddy 自动 git clone + submodule init
git submodule add https://github.com/godlockin/prc-law-data vendor/prc-law-data
git submodule update --init --recursive
# 4. 配置律师工作目录
mkdir -p ~/lawyer-work/{matters,alerts}
# 5. 在 WorkBuddy 输入:
# > /init prc-law
# > /lawyer-workflow setup
```

### 律所团队部署

```bash
# 1. 律所 NAS/SMB 网盘挂载
mount -t smbfs //law-firm-nas/prc-law ~/lawyer-work
# 2. 共享法规 cache (只读)
# 3. 每律师各自有 private 子目录
# 4. cron 跑 deadline_monitor + statute_monitor
```

## 升级策略

| 层 | 升级方式 | 频率 |
|----|---------|------|
| Layer 1 (prc-law-data) | git pull (律所共享 cache) | 周级自动 |
| Layer 2 (PRC-Law) | WorkBuddy 自动更新 skill | 月级 |
| Layer 3 (律师私有) | 律师手动 + 自动 cron | 实时 |
| Layer 4 (WorkBuddy) | WorkBuddy 自身更新 | 季度 |

## 与 W7-回答 衔接

| 问题 | 答案 |
|------|------|
| 自动更新数据存哪 | Layer 1 (prc-law-data 公开仓库) |
| 案件信息存哪 | Layer 3 (本地 + 未来网盘) |
| 律师怎么用 | Layer 4 (WorkBuddy, 非 CLI) |

## 相关文档
- `prc-law-data/README.md` — 数据外挂说明
- `docs/workbuddy-integration.md` (W8.3) — WorkBuddy 集成步骤
- `docs/architecture-quickstart.md` — 5 分钟快速部署
- `docs/llm-switch-guide.md` — LLM 切换(Qwen/DeepSeek)