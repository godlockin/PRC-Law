# cn-statute-watchdog 工作流集成说明

> 关联 skill: `_foundation/statute-watchdog/SKILL.md`
> 工作流说明: 将法条修订跟踪与现有 skill 体系深度集成

## 工作流触发矩阵

| 法条状态变化 | 自动触发 | 工作流 |
|------------|---------|--------|
| 现行有效 → 已被修改 | ✅ | 通知 + 在办事项复审 |
| 现行有效 → 失效 | 🔴 | 通知 + 在办事项紧急复审 + 模板更新 |
| 已被修改 → 失效 | 🔴 | 通知 + 在办事项紧急复审 |
| 失效 → 现行有效 | 🟡 | 通知 + 模板审视 |
| 新法新规发布 | 🟠 | 通知 + 评估影响范围 |

## 在办事项复审流程

```
[cn-statute-watchdog 检测变化]
       │
       ▼
[Step 1: 影响评估]
  扫描 matter-workspace 的 watchlist
  识别在用该法条的所有事项
       │
       ▼
[Step 2: 优先级排序]
  P0: 现行诉讼/仲裁进行中的事项
  P1: 拟提起但未立案的事项
  P2: 既往已结案但可能需要追溯的事项
       │
       ▼
[Step 3: 自动重审]
  对每个 P0/P1 事项：
  ├── 重新检索法条（cn-legal-retrieval with refer_date=新版本生效日）
  ├── 比较旧版 vs 新版差异
  ├── 调用 cn-consequence-conflict 重新评估后果
  ├── 调用 cn-outcome-forecast 重新评估胜诉概率
  └── 生成"法条变更影响评估报告"
       │
       ▼
[Step 4: 通知 + 决策]
  通知律师/客户
  建议应对行动：
  - 重新提交诉状（如事实变更）
  - 修订合同条款（如合同期长）
  - 调整诉讼策略
  - 暂缓行动
```

## 自动通知模板

```yaml
notification:
  recipient: [法务总监/主办律师]
  channel: [邮件/IM]
  priority: [P0/P1/P2]
  content:
    subject: "[法条变更] {法条名} 第 {X} 条 - 影响 {事项数} 个在办事项"
    body:
      - 法条变更详情（old vs new）
      - 影响的在办事项清单
      - 建议应对行动
      - 截止时间（如有时效）
      - 操作链接（如集成到 matter-workspace）
```

## 与 PRC-Law 现有 skill 的集成

| 现有 skill | 集成方式 |
|----------|---------|
| **cn-legal-retrieval** | 提供实时检索能力（当前/历史版本） |
| **cn-element-extraction** | 自动识别事项中在用的法条，加入监听清单 |
| **cn-matter-workspace** | 维护事项的 watchlist |
| **cn-consequence-conflict** | 复审时重新评估后果 |
| **cn-outcome-forecast** | 复审时重新评估胜诉概率 |
| **cn-systematic-risk** | 法条变化作为风险因素 |
| **cn-argument-chain** | 重新构建论证链（如法条变更） |
| **cn-source-label** | 标注新旧版本法源 |

## 工作流启用命令

```
# 手动触发法条监听
cn-statute-watchdog listen --fgmc <法规名> [--auto-add-to-watchlist]

# 自动添加事项到监听清单
cn-matter-workspace update <slug> --watch-statutes <ftids>

# 查看所有监听中的法条
cn-statute-watchdog list-watchlist

# 触发事项复审
cn-statute-watchdog review-matter <slug> --trigger "法条修订"

# 生成变更报告
cn-statute-watchdog report --month YYYY-MM
```

## 实现优先级

| 阶段 | 功能 | 时间 |
|------|------|------|
| P0 | 手动调用监听 + 变更检测 | v5.0（已完成） |
| P1 | 与 matter-workspace 自动集成 | v5.1 |
| P2 | 元典 MCP 自动检测脚本 | v5.1 |
| P3 | 多源对比（北大法宝） | v5.2 |

## 借鉴差异说明

> 本工作流是 PRC-Law **独有**。
>
> 设计灵感：
> - PRC-Law 已有时间锚点 + cn-norm-verify 双源核验
> - 借鉴项目无任何法条变更跟踪能力
> - 法律实务中"诉讼过程中法条被修改"的真实痛点