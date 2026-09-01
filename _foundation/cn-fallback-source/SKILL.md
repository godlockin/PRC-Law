---
name: cn-fallback-source
description: 告诉 cn-legal-retrieval 等检索类技能如何调用 retrieval_router.py, 以及各来源标签的语义 (元典/法宝/prc-law-data/政府源/缓存)。当用户问"为什么不用元典/有没有免费源/为什么这个法条标[已确认: prc-law-data]"时触发。当 L1 MCP 不可用时, 自动 fallback 到 prc-law-data 离线数据集 + 本地 cache + 爬虫 + 政府公开源。
---

# cn-fallback-source · 检索源层级与 fallback 协议

## 角色

只读协调层。在 `cn-legal-retrieval` 中执行时, **调用** `scripts/retrieval_router.py` 而不是直接调 MCP。本技能定义:

1. **6 级 fallback 链**
2. **各来源标签语义**
3. **何时使用每层**

## 6 级 fallback 链 (v8.3.0+)

按 `retrieval_router.py` 实现:

| 级别 | 数据源 | 调用方式 | 标签 | 成本 | 适用 |
|------|--------|---------|------|------|------|
| **L1** | 元典/法宝 MCP | HTTPS SSE / stdio bridge | `[已确认: 元典+北大法宝 YYYY-MM-DD]` | 消耗 credit | 有 API key, 在线, 商业权威 |
| **L2** | **prc-law-data 数据集** (v8.3.0+) | 本地文件 / HTTP API | `[已确认: prc-law-data 离线数据集 YYYY-MM-DD]` | **零 credit** | 离线 / 高频核心法条 |
| **L3** | 本地 cache (`references/.cache/statutes.json`) | 文件读 | `[本地缓存 YYYY-MM-DD—需运行时核验]` | 零 credit | 离线 / 已知法条快速命中 |
| **L4** | 爬虫结果 (`references/laws/<slug>.md`) | 文件读 | `[已确认: 国家法律法规数据库 YYYY-MM-DD]` | 零 credit | 全新法律 / 元典不可用 |
| **L5** | 政府公开源 (v8.3.0+) | HTTP GET | `[已确认: 最高人民检察院/国务院 YYYY-MM-DD]` | 零 credit | 时效补丁 / 指导性案例 |
| **L6** | 无可用源 | — | `[待检索—所有源均不可用]` | — | 阻塞输出 (参考 cn-legal-retrieval L3 规则) |

## 各标签权威等级

### `[已确认: 元典+北大法宝 YYYY-MM-DD]` (L1)

- **权威等级**: **最高** (商业维护, 多源交叉)
- **适用场景**: 有元典/法宝 API key + 在线 + 需要多源核验
- **风险**: 消耗 credit

### `[已确认: prc-law-data 离线数据集 YYYY-MM-DD]` (L2) ⭐ 新增

- **权威等级**: **高** (聚合 laws-data + LawRefBook + HF parquet 三源, 已校验)
- **适用场景**: 默认首选. 离线工作 / 不想消耗商业 credit / 高频核心法条 (民法典/刑法/公司法/数据三法等)
- **覆盖**: **18525 部**法律 (v8.3.0 实际导入)
- **数据来源**:
  - [13098806890/laws-data](https://github.com/13098806890/laws-data) (MIT, 结构化 + 中英 + RAG 增强)
  - [LawRefBook/Laws](https://github.com/LawRefBook/Laws) (1.8k⭐, 1688 部 + 459 部司法解释)
  - [twang2218/chinese-law-and-regulations](https://huggingface.co/datasets/twang2218/chinese-law-and-regulations) (Apache-2.0, 22.5K 条)
- **风险**: 数据集有快照滞后 → 配 L5 政府源补时效
- **仓库**: https://github.com/your-org/prc-law-data (独立仓库)

### `[本地缓存 YYYY-MM-DD—需运行时核验]` (L3)

- **权威等级**: 次档 (缓存可能过期)
- **适用场景**: 离线模式 / 已知法条快速命中
- **使用前提**: cache 必须标 `pulled_at` 日期, >180 天自动降级到 `[模型知识—需验证]`

### `[已确认: 国家法律法规数据库 YYYY-MM-DD]` (L4)

- **权威等级**: 与元典同档 (全国人大官方源)
- **适用场景**: MCP 不可用时; 或新法律元典未及时收录
- **使用前提**: 本文件已被 `sync_check.sh` 定期校对 (最近 7 天内)
- **风险**: 人工维护的 markdown, 偶尔可能有 OCR/排版错误 → 律师审阅闸不可省

### `[已确认: 最高人民检察院/国务院 YYYY-MM-DD]` (L5) ⭐ 新增

- **权威等级**: 高 (政府公开)
- **适用场景**: 数据集滞后 / 实时补丁 (指导性案例 / 政策文件)
- **来源**:
  - `https://www.spp.gov.cn/spp/jczdal/` — 最高检指导性案例 (实测 117 条最新批次可达)
  - `https://www.gov.cn/zhengce/` — 国务院政策文件 (实测 6 条最新可达)
- **限制**: 仅列表/标题级匹配, 不直接返回法律全文

## 核心设计: prc-law-data 数据集 (v8.3.0+)

### 为什么独立仓库 + submodule

PRC-Law skill 仓库与 prc-law-data 数据集**解耦**:

| 维度 | PRC-Law | prc-law-data |
|------|---------|--------------|
| 性质 | 技能代码 (SKILL.md) | 法律全文数据 |
| 更新节奏 | 月度 (技能迭代) | 每周 (新法出台即拉) |
| 大小 | ~MB | ~250MB (18525 部法律) |
| 许可 | 项目本身 | 数据 = 公共领域, 代码 = MIT |
| 独立性 | — | 可独立 git clone / HTTP API |

### 三种对接模式

**1. Vendor submodule** (默认推荐)

```bash
cd PRC-Law
git submodule add https://github.com/your-org/prc-law-data.git vendor/prc-law-data
git submodule update --init --recursive
```

PRC-Law 自动从 vendor/prc-law-data/data/ 读取 (优先).

**2. 环境变量自定义路径**

```bash
export PRC_LAW_DATA_DIR=/path/to/prc-law-data/data
```

**3. HTTP API 模式**

```bash
# 启动 prc-law-data 服务
python3 prc-law-data/scripts/serve.py --port 8765

# PRC-Law 通过环境变量连接
export PRC_LAW_DATA_URL=http://localhost:8765
```

### 更新数据集

```bash
cd prc-law-data
./scripts/update.sh         # 增量更新 (默认)
./scripts/update.sh --full  # 全量重建
./scripts/update.sh --check # 仅检测上游版本
./scripts/verify.py         # 校验完整性
```

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

输出示例 (v8.3.0+):

```
✅ 找到 (L2)
   来源链: prc_law_data
   标签: [已确认: prc-law-data 离线数据集 2026-09-01]
   法律: 中华人民共和国民法典 第577条
   ...
```

## 不做的事

- ❌ 不主动调 MCP (让 `retrieval_router` 决定是否走到 L1)
- ❌ 不绕过来源标注 (即便 L2 命中, 仍须标 `[已确认: prc-law-data]`)
- ❌ 不修改 prc-law-data 数据集 (那是独立仓库的事)
- ❌ 不缓存 MCP 结果到 prc-law-data (避免法律更新漏)

## 维护

- **新增爬虫源**: 扩展 `retrieval_router.py` 的 `try_*` 函数, 并在 `LABEL_BY_LEVEL` 加映射
- **新增 fallback 级别**: 在 `LABEL_BY_LEVEL` 添加, 向后兼容
- **数据集更新**: `cd vendor/prc-law-data && ./scripts/update.sh`
- **测试**: `python3 scripts/retrieval_router.py --explain`

## 关联

- 路由器: `scripts/retrieval_router.py`
- 数据集客户端: `scripts/dataset_client.py`
- 数据集仓库: `vendor/prc-law-data/` (submodule)
- 爬虫: `scripts/fetch_flk_npc.py` + `scripts/fetch_court_guides.py` + `scripts/fetch_gov_cn.py`
- 校对: `scripts/sync_check.sh` (cron 周一/三/五)
- 缓存: `scripts/cache_health_check.py`
- 来源标签: `_foundation/source-label/SKILL.md`
- 检索入口: `_foundation/legal-retrieval/SKILL.md`