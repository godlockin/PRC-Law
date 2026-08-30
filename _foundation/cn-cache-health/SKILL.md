---
name: cn-cache-health
description: 展示 PRC-Law 法条缓存健康度（覆盖率 + 新鲜度 + 已省/将花费用）。当用户问"缓存状态/我缓存了多少/元典用得怎样/为什么这个法律找不到"时触发。SessionStart hook 也可后台调用，结果写入 ~/.prc-law/cache-health.json + cache-alert.json。
---

# cn-cache-health — 法条缓存健康度

## 角色

只读展示层。读两个 state 文件：

- `~/.prc-law/cache-health.json` — 整体健康度 + 每部法律覆盖
- `~/.prc-law/cache-alert.json` — fail/warn 列表（含 reason）

**不**主动拉 API，**不**修改缓存。同步执行入口在 `scripts/cache_health_check.py`。

## 输出格式

### 概览

```
📊 PRC-Law cache health: GOOD / WARN / FAIL
   laws: 12 good / 2 warn / 0 fail
   saved ¥142.50 (2850 API calls cached)
   fill missing: ¥8.20 (164 calls)
   ⚠ 2 alerts → see ~/.prc-law/cache-alert.json
```

### 详细（用户主动查询时）

每部法律一行：

```
[GOOD] 民法典              1260/1260 (100%)   freshness 30天
[WARN] 公司法              240/266  (90%)    freshness 210天 ← 新鲜度超期
[FAIL] 反不正当竞争法        5/33   (15%)    freshness 90天  ← 覆盖率过低
```

## 行为表

| 条件 | 动作 |
|------|------|
| `cache-health.json` 不存在 | 静默，提示运行检查 |
| `overall_health == "good"` | 静默（同 session 不重复） |
| `overall_health == "warn"` | 简明一行横幅 |
| `overall_health == "fail"` | **强调** + 列出 fail 法律 + 提示补 fill |
| 用户主动问"缓存状态" | 始终详细输出 |

## 推荐补缓存命令

```bash
# 按优先级填充(优先级 1 = 高频法)
python3 scripts/fill_cache_batch.py --priority 1

# 单部法律
python3 scripts/statute_cache.py pull --law 民法典

# 刷新过期(>90 天)
python3 scripts/statute_cache.py refresh
```

## 成本估算口径

- `cost_per_api = ¥0.05`（元典平均单次 API 估价，可通过 `PRC_LAW_COST_PER_API` 覆盖）
- `saved_yuan = articles_cached × cost_per_api`
- `fill_cost = missing × cost_per_api`

> ⚠️ **成本估算仅供参考**：实际元典/北大法宝按套餐计费，不一定按调用次数。

## 关联

- 扫描入口: `scripts/cache_health_check.py`
- 缓存写入: `scripts/fill_cache_batch.py` + `scripts/statute_cache.py`
- 数据源: `references/.cache/statutes.json` + `references/_freshness.yaml`
- 后台触发: 可选在 `hooks/hooks.json` SessionStart 追加一行（见 README）