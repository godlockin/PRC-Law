# WorkBuddy 集成指南 (W8.3)

> 律师通过 WorkBuddy (腾讯工作台) 或类似 online/offline 工具加载 PRC-Law skills,
> 不需要 CLI / 不需要 VSCode。

## 什么是 WorkBuddy

- **类型**: 在线/离线 AI 工作台 (腾讯出品)
- **能力**: 加载 Claude Code Skill 协议, 自然语言触发工具
- **律师用法**: 在对话窗口输入 "这个案子能调解吗", WorkBuddy 自动调 PRC-Law skills

## WorkBuddy 与 PRC-Law 集成架构

```
┌──────────────────────────────────────────────┐
│ WorkBuddy (腾讯工作台)                        │
│   - 在线: 浏览器/客户端                       │
│   - 离线: 本地模式                            │
│   - 内嵌 Claude Code runtime                 │
└──────────────────────────────────────────────┘
            ↓ 加载 PRC-Law skills
┌──────────────────────────────────────────────┐
│ PRC-Law (skills 容器)                        │
│   - cn-mediation-hint                        │
│   - cn-pleading-templates                   │
│   - cn-case-archive                         │
│   - deadline-monitor (cron)                 │
│   - ... 24 atomic + 6 compound + 10 domain │
└──────────────────────────────────────────────┘
            ↓ 调用
┌──────────────────────────────────────────────┐
│ 数据外挂 / 律师私有层                         │
│   - prc-law-data (公开)                      │
│   - ~/lawyer-work/ (本地)                    │
└──────────────────────────────────────────────┘
```

## 安装步骤 (律师)

### 1. 安装 WorkBuddy

参考腾讯工作台官方安装指南:
- macOS / Windows / Linux 客户端
- 浏览器版 (无需安装)

### 2. 配置 PRC-Law skill 源

WorkBuddy 设置 → Skill 管理 → 添加外部 skill:

```
Skill 仓库: https://github.com/godlockin/PRC-Law
加载方式: git clone
子模块: 自动初始化 prc-law-data
```

或本地仓库:
```
Skill 路径: ~/PRC-Law (已 git clone)
```

### 3. 配置律师私有工作目录

WorkBuddy 设置 → 工作目录:

```bash
mkdir -p ~/lawyer-work/{matters,alerts,.cache}
```

WorkBuddy 启动时自动扫描该目录,识别:
- `matters/` — 案件目录
- `cases.db` — 本地类案
- `.lawyer_profile` — 律师画像
- `alerts/` — 提醒输出

### 4. 配置 LLM (合规要求)

律师必须用境内 LLM (PIPL 合规),详见 `docs/llm-switch-guide.md`:

```bash
# ~/.zshrc 或 ~/.bashrc
export ANTHROPIC_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export ANTHROPIC_AUTH_TOKEN="sk-...your-key"
export ANTHROPIC_MODEL="qwen-max"
```

WorkBuddy 自动读取 shell 环境变量。

## 律师日常使用 (5 类场景)

### 场景 1: 接案评估

```
律师输入:
> 收到一个咨询, 合同纠纷, 标的 200 万, 当事人证据强对方弱,
  立案前评估胜诉率
```

WorkBuddy 自动触发:
- `cn-mediation-hint` skill
- 读取 `cases.db` (本地类案)
- 输出调解策略单 (Markdown) 到 `matters/M-XXX/strategy.md`

### 场景 2: 文书起草

```
律师输入:
> 用律师函模板, 起草一份给深圳兴华科技的催告函
```

WorkBuddy 触发:
- `cn-pleading-templates` skill
- 选模板 `templates/lawyer-letter.md`
- LLM 抽取律师刚才提供的事实
- 输出 Word 到 `matters/M-XXX/lawyer-letter.docx`

### 场景 3: 时效预警

```
律师输入:
> 查看本周所有案件时效
```

WorkBuddy 触发:
- `deadline-monitor` (cron 跑过, 缓存到 alerts/)
- 读取 `alerts/deadline-*.md`
- 输出 Markdown 表格, 律师一目了然

### 场景 4: 类案检索

```
律师输入:
> 找一下劳动违法解除赔偿金 2N 的高院案例
```

WorkBuddy 触发:
- `cn-case-archive` skill
- 检索本地 `cases.db` + ChatLaw streaming
- 输出命中案例 + 引用标签 `[已确认]`

### 场景 5: 文书 Word 转 PDF

```
律师输入:
> 把 M-2026-001 的答辩状转 PDF, 给客户签字
```

WorkBuddy 触发:
- `cn-pleading-templates` skill (转换子模块)
- 用 LibreOffice / Word 转 PDF
- 输出 `matters/M-2026-001/答辩状.pdf`

## WorkBuddy 加载 PRC-Law 的配置 (技术细节)

### `prc-law.skills.json`

WorkBuddy 通过这个清单文件识别 PRC-Law skill:

```json
{
  "version": "1.0.0",
  "repository": "https://github.com/godlockin/PRC-Law",
  "data_layer": {
    "type": "git-submodule",
    "url": "https://github.com/godlockin/prc-law-data",
    "path": "vendor/prc-law-data/data"
  },
  "private_layer": {
    "lawyer_workspace": "~/lawyer-work",
    "case_db": "~/lawyer-work/cases.db",
    "alerts": "~/lawyer-work/alerts"
  },
  "skills": [
    {
      "name": "cn-mediation-hint",
      "path": "_domains/litigation/skills/cn-mediation-hint/SKILL.md",
      "trigger": ["调解", "诉前调解", "让步空间"]
    },
    {
      "name": "cn-pleading-templates",
      "path": "_domains/litigation/skills/cn-pleading-templates/SKILL.md",
      "trigger": ["起草", "答辩状", "律师函", "起诉状"]
    },
    {
      "name": "cn-case-archive",
      "path": "_foundation/cn-case-archive/SKILL.md",
      "trigger": ["类案检索", "找相似案例", "裁判规则"]
    }
  ],
  "cron": [
    {
      "name": "deadline-monitor",
      "script": "scripts/deadline_monitor.py",
      "schedule": "0 9 * * *",  # 每天 9 点
      "output": "~/lawyer-work/alerts/"
    }
  ]
}
```

### 启动序列

WorkBuddy 启动 PRC-Law 时:
1. 检查 `prc-law.skills.json` 是否存在
2. `git submodule update --init --recursive` (拉数据外挂)
4. 加载 `SKILL.md` 到 Claude Code runtime
5. 挂载律师工作目录到 skill context
6. 启动 cron (deadline-monitor, statute-monitor)
7. WorkBuddy 显示 "PRC-Law 已就绪"

### 升级机制

WorkBuddy 检测 PRC-Law 仓库版本:
- 每周自动 `git pull` (不影响律师工作)
- 重大版本 (主版本号变更) 提示律师手动升级

## WorkBuddy vs CLI / VSCode 对比

| 维度 | WorkBuddy | CLI | VSCode |
|------|-----------|-----|--------|
| 律师上手成本 | **低**(自然语言) | 高(需学命令) | 高(需装 IDE) |
| 触发 skill | 自动(关键词) | 手动(读 SKILL.md) | 手动 |
| 文件管理 | 自动(matters/) | 手动 | 手动 |
| 类案检索 | 一句话 | 跑 python 脚本 | 跑 python 脚本 |
| 适合 | 律师日常 | 开发者 | 律师 + 开发者 |

**结论**: 律师**只用 WorkBuddy**,开发者/律所管理员用 CLI/VSCode。

## 律师实操示例 (完整对话)

```
[WorkBuddy 界面, 律师输入]
律师: 客户张总来咨询, 2024 年 3 月签订设备采购合同,
     已付 80 万, 货已收, 对方还欠 200 万尾款 14 个月没付。
     我证据很全 (合同 + 物流单 + 发票), 对方理由是质量有问题。
     现在想调解, 我应该开价多少?

[WorkBuddy 自动调 cn-mediation-hint skill]
  ↓ 读 cases.db 本地类案
  ↓ 计算胜诉率: 87% (强证据 + 合同纠纷基线 62% + 证据调节 +0.25)
  ↓ 生成调解策略单

[WorkBuddy 输出]
  ✅ 调解策略单已生成: matters/M-2026-001/strategy.md
  
  📊 关键建议:
  - 胜诉率: 87% (强证据)
  - 建议初始报价: 200 万 (略超标的)
  - 让幅下限: 175 万 (律师最低接受)
  - 让幅上限: 220 万 (含违约金空间)
  - 成本测算: 律师费 7.5 万 + 诉讼费 2 万 = 9.5 万
  - 风险弱点: 无明显程序/证据弱点
  
  ⚠️ 律师审阅闸: 上述建议仅供参考, 与当事人沟通确认调解授权。
  
  [查看完整策略单 → matters/M-2026-001/strategy.md]

[律师继续输入]
律师: 用律师函模板起草一份, 直接用上面的事实

[WorkBuddy 触发 cn-pleading-templates skill]
  ↓ 选模板 lawyer-letter.md
  ↓ LLM 抽字段: 致函对象/金额/律师/期限等
  ↓ 输出 Word: matters/M-2026-001/lawyer-letter.docx

[WorkBuddy 输出]
  ✅ Word 已生成: matters/M-2026-001/lawyer-letter.docx
  📄 律师函编号: [2026] 京海律函字第 XXX 号
  ⚠️ AI 辅助生成 — 律师审阅后使用
```

**律师全程不需要**:
- ❌ 打开命令行
- ❌ 安装 Python
- ❌ 看 SKILL.md
- ❌ 用 VSCode

## 离线模式

WorkBuddy 离线模式 (律师在高铁/飞机上):
- ✅ 本地类案检索 (`cases.db` 离线可用)
- ✅ 规则基线调解建议 (`mediation_hint.py` 纯规则)
- ❌ 元典/法宝 MCP (需联网)
- ❌ ChatLaw streaming (需联网)
- ⚠️ 自动降级到 L3-L6 (`retrieval_router` 已实现)

## 团队协作 (律所)

```
WorkBuddy 团队配置
├── 律所共享
│ ├── 法规 cache (W7 镜像 prc-law-data)
│ └── 律所规则 (firm_rules.json, 调整基线胜诉率)
└── 律师私有
  ├── {lawyer-id}/matters/
  ├── {lawyer-id}/cases.db
  └── {lawyer-id}/alerts/
```

- 法规 cache 共享: 5 个律师只下载 1 份法规
- 律所规则共享: 调整默认胜诉率(按律所历史案件)
- 案件/类案私有: 每律师独立, 通过律所 NAS 备份

## 故障排查

| 问题 | 排查 |
|------|------|
| WorkBuddy 加载 PRC-Law 失败 | 检查网络 + git submodule 是否初始化 |
| 律师工作目录为空 | `mkdir -p ~/lawyer-work/{matters,alerts}` |
| 类案检索返回空 | `cases.db` 未建, 跑 `python3 scripts/case_indexer.py init` |
| LLM 调用失败 | 检查 `ANTHROPIC_BASE_URL` 是否生效 |
| 提醒没触发 | 检查 cron 是否启动, `~/lawyer-work/alerts/` 是否存在 |

## 下一步

- WorkBuddy 上架 (W9, 与腾讯工作台对接)
- 律师 beta 测试 (W10, 找 3-5 个律师试用)
- 反馈迭代 (W11+, 收集律师真实痛点)

## 关联资源

- `docs/architecture.md` — 三层分离架构
- `docs/llm-switch-guide.md` — 境内 LLM 切换
- `docs/data-license.md` — 数据集许可证
- PRC-Law GitHub: <https://github.com/godlockin/PRC-Law>
- prc-law-data GitHub: <https://github.com/godlockin/prc-law-data>