---
name: cn-fallback-source
description: 告诉 cn-legal-retrieval 等检索类技能如何调用 retrieval_router.py, 以及新增「国家法律法规数据库」来源标签的语义。当用户问"为什么不用元典/有没有免费源/为什么这个法条标[本地缓存]"时触发。当 L1 MCP 不可用时, 自动 fallback 到本地 cache + flk.npc.gov.cn 爬虫结果。
---

# cn-fallback-source · 检索源层级与 fallback 协议

## 角色

只读协调层。在 `cn-legal-retrieval` 中执行时, **调用** `scripts/retrieval_router.py` 而不是直接调 MCP。本技能定义：

1. **4 级 fallback 链**
2. **新增的来源标签语义**
3. **何时使用每层**

## 4 级 fallback 链

按 `retrieval_router.py` 实现：

| 级别 | 数据源 | 调用方式 | 标签 | 适用 |
|------|--------|---------|------|------|
| **L1** | 元典/法宝 MCP | HTTPS SSE / stdio bridge | `[已确认: 元典+北大法宝 YYYY-MM-DD]` | 有 API key, 在线 |
| **L2** | 本地 cache (`references/.cache/statutes.json`) | 文件读 | `[本地缓存 YYYY-MM-DD—需运行时核验]` | 离线 / 已知法条 |
| **L3** | 爬虫结果 (`references/laws/<slug>.md`) | 文件读 | `[已确认: 国家法律法规数据库 YYYY-MM-DD]` | 全新法律 / 元典不可用 |
| **L4** | 无可用源 | — | `[待检索—所有源均不可用]` | 阻塞输出（参考 cn-legal-retrieval L3 规则） |

## 新增标签语义

### `[已确认: 国家法律法规数据库 YYYY-MM-DD]`

- **权威等级**：与元典同档（全国人大官方源）
- **适用场景**：MCP 不可用时；或新法律元典未及时收录
- **使用前提**：本文件已被 `sync_check.sh` 定期校对（最近 7 天内）
- **风险**：人工维护的 markdown, 偶尔可能有 OCR/排版错误 → 律师审阅闸不可省

### `[本地缓存 YYYY-MM-DD—需运行时核验]`

- **权威等级**：次档（缓存可能过期）
- **适用场景**：离线模式 / 已知法条快速命中
- **使用前提**：cache 必须标 `pulled_at` 日期，>180 天自动降级到 `[模型知识—需验证]`

## 调用方式

### Python 脚本

```python
import subprocess, json
result = subprocess.run(
    ["python3", "scripts/retrieval_router.py",
     "--law", "民法典", "--article", "577",
     "--explain", "--json"],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
# data["label"] / data["content"] / data["selected_level"]
```

### Bash

```bash
python3 scripts/retrieval_router.py --law 民法典 --article 577 --explain
```

输出示例：

```
✅ 找到 (L2)
   来源链: cache
   标签: [本地缓存 2026-08-01—需运行时核验]
   法律: 民法典 第577条
   ...
```

## 不做的事

- ❌ 不主动调 MCP（让 `retrieval_router` 决定是否走到 L1）
- ❌ 不绕过来源标注（即便 L3 命中，仍须标 `[已确认: 国家法律法规数据库]`）
- ❌ 不修改 cache 文件本身（仅 fetch_flk_npc.py 与 fill_cache_batch.py 写）

## 维护

- **新增爬虫源**：扩展 `retrieval_router.py` 的 `try_*` 函数，并在 `LABEL_BY_LEVEL` 加映射
- **新增 fallback 级别**：在 `LABEL_BY_LEVEL` 添加，向后兼容
- **测试**：见 `scripts/fetch_flk_npc.py --list` + `retrieval_router.py --explain`

## 关联

- 路由器: `scripts/retrieval_router.py`
- 爬虫: `scripts/fetch_flk_npc.py` + `scripts/fetch_court_guides.py`
- 校对: `scripts/sync_check.sh` (cron 周一/三/五)
- 缓存: `scripts/cache_health_check.py`
- 来源标签: `_foundation/source-label/SKILL.md`
- 检索入口: `_foundation/legal-retrieval/SKILL.md`