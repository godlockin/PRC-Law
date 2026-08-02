# 双轨降级策略 — MCP 不可用时的离线行为定义

> 本文档定义当元典（法令/案例/工商）或北大法宝 MCP 服务不可用时的显式降级行为。
> 所有领域和复合技能必须遵守。
> last_verified: 2026-08-01 | freshness_window: 180 days

## 降级层级

### Level 0: 正常运行
- MCP 可用，检索返回结果 ≥1 条
- 所有来源标注正常：`[已确认]` / `[单源]` / `[本地案例库]` / `[用户提供]`
- **无限制**

### Level 1: 部分源不可用（部分源工作）
- 一个或多个 MCP 源不可用（如 yuandian-law 超时），至少一个仍可用
- 所有结果标注 `[单源—需复核: <可用源>]`
- cn-norm-verify 仅做单源核验，标注 `[单源核验—待多源确认]`
- **限制**：涉及刑事/刑期/除斥期间/举证责任分配的结论转 `[待多源确认—暂不给出]`
- **用户可见**：输出顶部显式标注 "⚠️ 当前仅单源检索可用，以下结果未经多源交叉核验"

### Level 2: 所有外部 MCP 不可用
- 全部 MCP 源均不可用
- cn-legal-retrieval 尝试本地案例库（如有）→ 标注 `[本地案例库: case_id]`
- 法条检索完全回退到 `[待检索]`
- cn-norm-verify 无法运行 → 标注 `[待检索—MCP 不可用]`
- **限制**：
  - 所有法律引用标注 `[模型知识—需验证]`
  - 复合技能（contract-full-review/judgment-draft/legal-opinion）输出顶部显式标注：
    "⚠️ 当前检索服务不可用。以下分析基于模型知识的初步判断，所有法条引用未经外部数据库核验。不可作为正式法律文件使用。请在检索服务恢复后重新运行。"
  - 禁止生成确认性法律结论
- **领域技能**：
  - 标注 "⚠️ 检索服务不可用，本分析基于模型知识，须在检索恢复后重新核验"
  - 可以继续提供结构性分析框架，但不得给出具体的法条编号和确定性法律意见

### Level 3: 完全离线（无网络 + 无本地案例库）
- 无 MCP + 无本地案例库
- **仅允许**：
  - 案例库加载（case-loader 不依赖网络）
  - 冷启动面试（cold-start 不依赖网络）
  - 法律概念理解（concept-comprehension 不依赖检索）
  - 法律术语规范（terminology 不依赖检索）
- **禁止**：所有领域技能、复合技能、norm-verify、source-label
- **提示**："当前完全离线。可使用的技能：案例库加载、冷启动配置、概念理解、术语规范。法律检索和分析类技能需要网络连接。"

## 降级缓存策略

### 法条缓存（已实现 — `scripts/statute_cache.py`）
- 15 部最高频法律已建立缓存框架（~3093 条款待填充）
- 缓存文件：`references/.cache/statutes.json`
- 索引文件：`references/.cache/index.json`
- 管理命令：
  - `python3 scripts/statute_cache.py pull` — 拉取/刷新缓存框架
  - `python3 scripts/statute_cache.py fill <法名> <条款号> '<原文>'` — 逐条填充
  - `python3 scripts/statute_cache.py fill-batch <input.jsonl>` — 批量填充
  - `python3 scripts/statute_cache.py list` — 列出所有已缓存法律及完整度
  - `python3 scripts/statute_cache.py search <关键词>` — 搜索缓存中的法条原文
  - `python3 scripts/statute_cache.py stats` — 缓存统计
  - `python3 scripts/statute_cache.py clean --older-than <天数>` — 清理过期
  - `python3 scripts/statute_cache.py refresh` — 刷新全部
- 缓存仅作 Level 2/3 离线参考，使用时标注 `[本地缓存—缓存日期—需运行时核验]`
- 缓存 freshness 窗口：90 天
- **填充方式**：运行 cn-legal-retrieval 时自动将检索到的法条全文调用 `fill` 写入缓存；或批量从官方数据库导入

### 本地案例库
- 由 case-loader 维护的 SQLite 索引不受网络影响
- Level 2 时案例检索回退到本地案例库
- 本地案例标注 `[本地案例库: case_id]`

## 降级状态指示器

各技能输出开头统一渲染：

```markdown
[检索状态: 🟢 多源可用 / 🟡 单源 / 🟠 仅本地 / 🔴 离线]
```

## CI 门控

- validate_skills.py 不对降级策略做静态检查（这是运行期行为）
- ci_check.sh 检查本文件的存在性和 freshness_window 是否过期
