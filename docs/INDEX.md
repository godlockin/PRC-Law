# 律鉴文档索引

> **所有文档的一站式入口**。按角色和用途分类。
> 更新：2026-08-04 | 版本：v9.2

## 🚀 我是新用户

| 步骤 | 文档 | 时间 |
|------|------|------|
| 1️⃣ | [README.md](../README.md) | 2 分钟 |
| 2️⃣ | [QUICKSTART.md](../QUICKSTART.md) | 5 分钟 |
| 3️⃣ | [DEMOS.md](DEMOS.md) | 10 分钟 |
| 4️⃣ | 跑一个 demo：`python3 scripts/demo_nd1.py` | 5 分钟 |

## ⚖️ 我是律师/法务

- 📖 [QUICKSTART.md](../QUICKSTART.md) - 5 分钟上手 + 4 个对话范例
- 🎬 [DEMOS.md](DEMOS.md) - 6 个端到端 demo
  - ND1: 时间锚点法律测试（避免误用新法判定旧案）
  - ND2: 167 号案复现（8 技能协同完整演示）
  - ND3: 案例库检索与法院画像
  - ND4: 170 号案公序良俗论证
  - ND5: 法条跟踪与预警
  - ND6: 合同全面审查 ORCHESTRATOR

## 💻 我是开发者

- 🏛️ [CLAUDE.md](../CLAUDE.md) - 全局推理链 + 借鉴原则
- 🛠️ [QUICKSTART.md](../QUICKSTART.md#6-进阶用法) - 跑 benchmark + 监听法条
- 🔌 [commands/cn-law.md](../commands/cn-law.md) - 统一入口与路由

## 🤝 我想贡献

- [CONTRIBUTING.md](../CONTRIBUTING.md) - 贡献指南 + 技能开发规范
- [CHANGELOG.md](../CHANGELOG.md) - 版本变更记录
- [ROADMAP.md](../ROADMAP.md) - 项目路线图

## 📚 项目元数据

- [LICENSE](../LICENSE) - 自定义许可协议
- [.claude-plugin/plugin.json](../.claude-plugin/plugin.json) - Claude Code 插件清单
- [docs/assets/logo.svg](assets/logo.svg) - Logo SVG
- [docs/assets/banner.svg](assets/banner.svg) - Banner SVG
- [docs/assets/README.md](assets/README.md) - 视觉资产说明

## 🧪 测试与基准

- [scripts/benchmark_summary.py](../scripts/benchmark_summary.py) - 多维能力测试
- [scripts/benchmark_runner.py](../scripts/benchmark_runner.py) - 5 案例 benchmark
- [scripts/demo_runner.py](../scripts/demo_runner.py) - 旧 demo runner
- [scripts/demo_nd1.py](../scripts/demo_nd1.py) - 时间锚点
- [scripts/demo_nd2.py](../scripts/demo_nd2.py) - 167 号案
- [scripts/demo_nd3.py](../scripts/demo_nd3.py) - 法院画像
- [scripts/demo_nd4.py](../scripts/demo_nd4.py) - 公序良俗
- [scripts/demo_nd5.py](../scripts/demo_nd5.py) - 法条跟踪
- [scripts/demo_nd6.py](../scripts/demo_nd6.py) - 合同审查
- [scripts/judge_pattern.py](../scripts/judge_pattern.py) - 法院画像
- [scripts/kg_query.py](../scripts/kg_query.py) - 知识图谱
- [scripts/md2docx.py](../scripts/md2docx.py) - DOCX 输出
- [scripts/statute_monitor.py](../scripts/statute_monitor.py) - 法条监听
- [scripts/verify_docx.py](../scripts/verify_docx.py) - DOCX 验证

## 📁 源代码结构

```
律鉴/
├── README.md            入口
├── QUICKSTART.md        快速上手
├── LICENSE              许可协议
├── CLAUDE.md            全局配置 + 推理链
├── CHANGELOG.md         变更日志
├── CONTRIBUTING.md      贡献指南
├── ROADMAP.md           路线图
│
├── _foundation/         17 原子技能
│   ├── cn-element-extraction/
│   ├── cn-legal-retrieval/
│   ├── cn-norm-verify/
│   ├── cn-interpretation-audit/   ← 独有
│   ├── cn-civil-claim-analysis/   ← 独有
│   ├── cn-statute-watchdog/      ← 独有
│   ├── cn-judge-pattern/         ← 独有
│   ├── cn-outcome-forecast/
│   ├── cn-argument-chain/
│   ├── cn-reasoning/
│   ├── cn-consequence-conflict/
│   ├── cn-evidence-evaluation/
│   ├── cn-source-label/
│   ├── cn-terminology/
│   ├── cn-concept-comprehension/
│   ├── cn-systematic-risk/
│   ├── cn-matter-workspace/
│   └── cn-cold-start/
│
├── _domains/            132 领域技能（10 领域）
│   ├── commercial/      商事合同 (9)
│   ├── corporate/       公司并购 (16)
│   ├── labor/           劳动用工 (20)
│   ├── litigation/      争议解决 (18)
│   ├── privacy/         隐私数据 (9)
│   ├── product/         产品合规 (7)
│   ├── ip/              知识产权 (12)
│   ├── regulatory/      监管合规 (14)
│   ├── ai-governance/   AI 治理 (10)
│   └── legal-edu/       法学教育 (10)
│
├── _compound/           6 复合技能
│   ├── judgment-draft/
│   ├── legal-opinion/
│   ├── contract-full-review/
│   ├── settlement-evaluation/
│   ├── claim-chart/
│   └── due-diligence-grid/
│
├── data/cases/          9 最高法指导案例（真实）
├── docs/                文档 + demo 报告
├── scripts/             12 自动化脚本
├── references/          降级策略
├── commands/cn-law.md   Claude Code 统一入口
└── .claude-plugin/      插件清单
```

## 🔍 按主题找文档

### 法律能力

- 推理链架构 → [CLAUDE.md](../CLAUDE.md)
- 证据评估 → `_foundation/evidence-evaluation/SKILL.md`
- 风险评估 → `_foundation/systematic-risk/SKILL.md`
- 结果预测 → `_foundation/outcome-forecast/SKILL.md`
- 法官画像 → `_foundation/judge-pattern/SKILL.md`

### 实操能力

- 跑 demo → `python3 scripts/demo_nd{1-6}.py`
- 转 Word → `python3 scripts/md2docx.py input.md output.docx`
- 监听法条 → `python3 scripts/statute_monitor.py`
- 法院画像 → `python3 scripts/judge_pattern.py --court "..." --cause "..."`

### 项目治理

- 借鉴原则 → [CLAUDE.md](../CLAUDE.md#借鉴真实性与可追溯原则全局强制)
- 贡献规范 → [CONTRIBUTING.md](../CONTRIBUTING.md)
- 许可协议 → [LICENSE](../LICENSE)

## 📋 文档版本对应

| 律鉴版本 | 文档更新 |
|---------|---------|
| v9.2 | 完整文档（README/QUICKSTART/DEMOS/CHANGELOG/CONTRIBUTING/ROADMAP） |
| v8.x | 6 端到端 demo + benchmark CI |
| v5.x | 三个独有创新（法条跟踪/法官画像/解释审计） |
| v3.x | 时间锚点 + 风险分叉 + Toulmin |
| v1.x | 初始 94 技能 |

---

> ⚠️ **律师审阅闸**: 本文档索引为导航文档，不构成法律意见。索引中的所有文档须经执业律师核实后方可作为法律意见依据。