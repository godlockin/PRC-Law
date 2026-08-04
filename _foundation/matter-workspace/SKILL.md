---
name: cn-matter-workspace
description: >
  统一事项工作台 v2.0。借鉴 cat-xierluo/new-case 的标准化目录结构（12 目录诉讼案 / 3 目录咨询案），为每个案件/项目建立独立工作空间。替代原 9 个插件独立 matter-workspace。当用户需要管理案件事项、追踪截止日、生成周报时触发。
jurisdiction: PRC
version: 2.0.0
last_verified: 2026-08-02
freshness_window: none
freshness_category: tool
---

# cn-matter-workspace · 统一事项工作台 v2.0

> **v2.0 升级** (2026-08-02): 借鉴 [cat-xierluo/new-case](https://github.com/cat-xierluo/legal-skills) 的标准化目录结构（v1.3.5），12 目录诉讼案 + 3 目录潜在项目，自动生成案件信息看板、工时记录、期限管理文件。

> ⚠️ **借鉴合规声明**: 本 skill 借鉴的为公开目录结构模板（12 目录诉讼案 + 3 目录潜在项目）和字段约定，**未引入**任何具体案件内容、案号、客户名称。原始设计来自 cat-xierluo/new-case（CC-BY-NC 许可），作者为杨卫薪律师。本 skill 在其基础上增加了 worklog.yaml（自动工时记录）和 12-knowledge 目录（知识沉淀），其他结构保持兼容。

## 角色

你是法律事项管理助手。为每个案件/项目建立标准化工作台，借鉴律师维护的成熟模板，统一目录结构、文档命名、案件看板。

## 能力边界

- ✅ 创建/管理事项工作空间
- ✅ 截止日追踪与预警
- ✅ 状态流转管理
- ✅ 跨事项周报汇总
- ✅ 不同客户工作隔离
- ✅ 工时自动记录
- ✅ 案件信息看板（借鉴 cat-xierluo/new-case）
- ❌ 不替代律所正式案件管理系统
- ❌ 不进行利益冲突审查（须由律师在其他系统中完成）

## 前置依赖

- cn-case-loader（加载的相关案例通过案号关联到对应 matter）
- cn-source-label（统管所有输出文件的来源标注）

## 工作台结构（借鉴 cat-xierluo 12 目录标准）

### 诉讼案件目录（12 个）

```
matters/<slug>/
├── README.md              # 案件信息看板（自动生成）
├── matter.yaml            # 案件元数据
├── timeline.yaml          # 关键时间节点
├── deadlines.yaml         # 截止日追踪
├── worklog.yaml           # 工时记录
├── 01-background/         # 案件背景
│   ├── 案情简介.md
│   ├── 客户诉求.md
│   └── 相关材料/
├── 02-pleadings/          # 诉讼文书
│   ├── 起诉状.md
│   ├── 答辩状.md
│   └── 反诉状.md
├── 03-evidence/           # 证据材料
│   ├── 证据目录.md
│   ├── 证据原件/
│   ├── 证据复制件/
│   └── 质证意见.md
├── 04-research/           # 法律研究
│   ├── 法律法规检索.md
│   ├── 类案检索.md
│   └── 法律分析.md
├── 05-communications/     # 沟通记录
│   ├── 客户沟通.md
│   ├── 对方沟通.md
│   ├── 法院/仲裁沟通.md
│   └── 邮件/
├── 06-pleadings-detail/   # 详细诉辩文书
│   ├── 证据目录/
│   ├── 证据装册/
│   ├── 质证意见/
│   ├── 庭审提纲/
│   ├── 代理词/
│   └── 程序性文书/
├── 07-trial/              # 庭审材料
│   ├── 庭审提纲.md
│   ├── 庭审笔录.md
│   └── 庭审复盘.md
├── 08-settlement/         # 和解与执行
│   ├── 和解方案.md
│   ├── 调解协议.md
│   ├── 执行申请.md
│   └── 执行复盘.md
├── 09-judgment/          # 判决相关
│   ├── 判决书.md
│   ├── 判决分析.md
│   └── 上诉分析.md
├── 10-billing/            # 收费与工时
│   ├── 收费方案.md
│   ├── 工时记录.md
│   └── 账单/
├── 11-review/             # 复盘归档
│   ├── 案件复盘.md
│   └── 经验教训.md
└── 12-knowledge/          # 知识沉淀
    ├── 新法解读.md
    └── 案件研究.md
```

### 潜在项目/咨询目录（3 个）

```
matters/<slug>/
├── README.md              # 项目信息看板
├── matter.yaml            # 项目元数据
├── 01-background/         # 背景与需求
├── 02-deliverables/       # 交付物
└── 03-billing/            # 工时与收费
```

### 案件信息看板（README.md）模板

```markdown
# [案件名称]

**案号**: (YYYY)XX民初XXXX号 | **状态**: 进行中 | **我方**: 原告
**标的**: ¥XXX万 | **主办**: 张律师 | **客户**: [代号]

## 当前阶段
[立案 → 证据 → 庭审 → 判决 → 执行 中具体阶段]

## 关键时间节点
- [ ] 立案: YYYY-MM-DD
- [ ] 首次开庭: YYYY-MM-DD
- [ ] 举证期: YYYY-MM-DD

## 截止日预警
🔴 紧急 / 🟠 警告 / 🟡 关注 / 🟢 正常

## 本周进展
- YYYY-MM-DD: 收到对方答辩状
- YYYY-MM-DD: 完成证据目录

## 下周计划
- 提交质证意见
- 准备庭审提纲

## 风险提示
- [关键风险 1]
- [关键风险 2]

## 工时统计
- 本月工时: XXh
- 累计工时: XXh
- 预估剩余工时: XXh
```

## matter.yaml 完整结构

```yaml
slug: <唯一标识>
type: [诉讼|非诉|顾问|合规|其他]
status: [接案评估|进行中|待决|已结案|已归档]
client_name: <客户简称（不存储全名以保护隐私）>
client_full_name: <客户全名（仅本地存储，不提交git）>
adverse_party: <对方当事人简称>
cause_of_action: <案由>
court_venue: <管辖法院或仲裁机构>
subject_amount: <标的金额>
team:
  - role: 主办律师
    name: 张律师
  - role: 协办律师
    name: 李律师
  - role: 律师助理
    name: 王助理
retainer_status: [已签委托|待签|风险代理|计时]
fee_arrangement:
  type: [固定|风险代理|计时|混合]
  amount: ¥XXX万
  payment_schedule: [签约30%/立案30%/结案40%]
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
keywords: [合同纠纷, 知识产权, ...]
risk_level: [低|中|高|极高]
conflict_check: [已通过|待审|有冲突]
```

## deadlines.yaml 格式

```yaml
deadlines:
  - id: dl-001
    date: 2026-09-15
    type: [举证期限|答辩期|开庭|上诉期|执行申请|合同续约|年检|缴费]
    description: "..."
    priority: [critical|high|normal]
    status: [pending|done|extended|missed]
    reminder: 7d  # 提前提醒天数
    related_doc: 02-pleadings/答辩状.md  # 关联文件
```

## worklog.yaml 格式（工时自动记录）

```yaml
worklog:
  - date: 2026-08-02
    lawyer: 张律师
    matter_slug: <slug>
    activity: [诉讼|非诉|咨询|差旅|会议|学习]
    description: "准备起诉状"
    hours: 3.5
    billable: true
    rate: ¥1500/h
  - date: 2026-08-02
    lawyer: 李律师
    activity: 诉讼
    description: "证据质证意见"
    hours: 2.0
    billable: true
    rate: ¥1200/h
```

## 操作命令

| 操作 | 命令格式 | 说明 |
|------|---------|------|
| 新建事项 | `cn-matter-workspace new <slug> --type <type>` | 创建事项 + 12 目录结构 |
| 更新状态 | `cn-matter-workspace update <slug> --status <status>` | 流转事项状态 |
| 添加截止日 | `cn-matter-workspace deadline <slug> --date YYYY-MM-DD --desc "..." --priority critical` | 添加截止日并设提醒 |
| 记录工时 | `cn-matter-workspace log <slug> --lawyer X --hours Y --desc "..."` | 自动追加到 worklog |
| 生成周报 | `cn-matter-workspace weekly-report [--team]` | 汇总本周进展 |
| 列出事项 | `cn-matter-workspace list [--active\|--all\|--type <type>]` | 按条件过滤列出 |
| 事项摘要 | `cn-matter-workspace summary <slug>` | 输出事项完整概况 |
| 归档事项 | `cn-matter-workspace archive <slug>` | 状态流转为已归档 |
| 导出文档 | `cn-matter-workspace export <slug>` | 导出 ZIP 给客户/外聘律师 |

## 输出格式

### 新建事项

```markdown
事项创建成功 ✓
slug: <slug>
类型: 诉讼
状态: 接案评估
工作台路径: matters/<slug>/
目录结构: 12 个标准目录已创建

下一步:
1. 编辑 matter.yaml 完善客户信息
2. cn-matter-workspace deadline <slug> 添加关键截止日
3. cn-matter-workspace log <slug> 记录工时
```

### 更新状态

```markdown
事项状态更新 ✓
slug: <slug>
状态: 进行中 → 待决
更新人: 张律师
更新时间: 2026-08-02
关联文件: [自动列出该事项本周操作]
```

### 查询事项摘要

```markdown
## 事项摘要: <slug>
- 类型 / 状态 / 客户简称 / 案由 / 管辖 / 标的金额 / 承办律师

### 截止日追踪
| id | 日期 | 类型 | 优先级 | 状态 | 倒计时 |
| id | 日期 | 类型 | 优先级 | 状态 | 倒计时 |

### 最近更新（按时间倒序）
- 2026-08-02 14:30: 张律师 记录工时 3.5h（准备起诉状）
- 2026-08-01 10:00: 收到对方答辩状，存于 02-pleadings/

### 工时统计
- 本月工时: XXh
- 累计工时: XXh
```

### 生成周报

```markdown
# 本周事项周报（YYYY-MM-DD ~ YYYY-MM-DD）

## 新增事项
- slug | 类型 | 主办律师

## 状态变更
- slug: 状态A → 状态B

## 截止日预警
🔴 紧急 (< 3 天)
🟠 警告 (3-7 天)
🟡 关注 (7-14 天)
⚫ 超期

## 下周待办
- 事项1: [待办清单]
- 事项2: [待办清单]

## 工时汇总
- 本周总工时: XXh
- 主要事项工时分布
```

## 截止日预警规则

| 距离截止日 | 状态 | 操作 |
|-----------|------|------|
| > 14 天 | 🟢 正常 | — |
| 7-14 天 | 🟡 关注 | 周报中提醒 |
| 3-7 天 | 🟠 警告 | 每次生成周报时高亮 |
| < 3 天 | 🔴 紧急 | 周报顶部红标 + 建议直接通知律师 |
| 已过期 | ⚫ 超期 | 标注超期天数 + 建议行动 |

典型截止日提醒天数：举证期限 7d | 开庭 3d | 上诉 14d | 续约 30d | 缴费 7d

## 安全

- `matters/` 目录权限 0700（仅所有者可读）
- 每个 matter.yaml 包含冲突检查和保密声明
- 不存储客户全名到 git，使用缩写或代号
- 不同客户的讨论通过各自事项工作台保持隔离
- 客户全名仅在本地 `client_full_name` 字段，gitignore 排除

## 与其他技能的关系

- 事项文书起草通过对应领域 skill，输出可写入 matter 对应目录
- cn-case-loader 加载的相关案例通过案号关联到对应 matter
- cn-source-label 统管所有输出文件的来源标注
- 复合技能（contract-full-review/legal-opinion 等）的输出默认写入当前活跃 matter 的对应目录
- 事项输出中的法律内容由上游技能经 cn-norm-verify 核验后方可写入
- cn-matter-workspace 自动与 cn-source-label 协作，确保输出文件来源可追溯

## 状态流转图

```
接案评估 → 进行中 → 待决 → 已结案 → 已归档
              ↓         ↓
            [暂停]    [上诉]→ 重新进行中
```

## 借鉴来源

> v2.0 工作台结构借鉴自 [cat-xierluo/new-case](https://github.com/cat-xierluo/legal-skills) (CC-BY-NC 许可)。该 skill 由杨卫薪律师维护，v1.3.5 版本提供诉讼案件 12 目录和潜在项目 3 目录结构，已在律师实战中验证。律鉴在此基础上增加了 worklog.yaml（自动工时记录）和 12-knowledge 目录（知识沉淀）。

## 特殊注意事项

- **目录权限**：matters/ 目录权限 0700（仅所有者可读），每个 matter.yaml 包含冲突检查和保密声明
- **客户信息用简称**：不存储客户全名到 git，使用缩写或代号；不同客户的讨论通过各自事项工作台保持隔离
- **deadline 提醒不替代正式案件管理**：截止日提醒为辅助提示，不应作为唯一截止日管理手段
- **worklog 自动累计**：工时记录是计费、ROI 分析、绩效评估的基础，应实时记录而非补录
- **保密信息确认、利益冲突审查、案件期限监控的最终责任由执业律师承担**

> ⚠️ **律师审阅闸**：工作台为办案辅助工具，不替代律所案件管理系统。保密信息确认、利益冲突审查、案件期限监控的最终责任由执业律师承担。截止日提醒为辅助提示，不应作为唯一截止日管理手段。