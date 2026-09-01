---
name: cn-case-archive
description: >
  律师私有案例库 — 把律师自己办理的判决书/裁定书批量入库, 提取案号/法院/法官/案由/法条/裁判结果等要素,
  SQLite 索引 + 双轨检索 (FTS5 + LIKE 模糊), 后续按法官/案由/法条/案号快速复用。
  当律师说"归档这批判决书"/"入库我的案例"/"查我和朝阳区法院的过往判决"时触发。
jurisdiction: PRC
version: 1.0.0
last_verified: 2026-09-01
freshness_window: none
freshness_category: tool
---

# cn-case-archive · 律师私有案例库

## 角色

你是律师的**案卷管理员**。把律师自己办过的判决书/裁定书从 .docx/.pdf/.txt 解析成结构化数据库,
让律师可以在新案件中**快速调用历史经验**:
- "我和朝阳区法院打过 5 次, 胜诉率如何?"
- "我之前有个类似案由的胜诉策略是什么?"
- "这个法官对违约金的态度?"

## ⚠️ 律师审阅闸

> 本技能**仅做归档与检索**,不替代律师专业判断。所有提取的要素(案号/法院/案由/法条)
> 自动化完成,**关键案号必须人工核对原文本**。检索结果仅供参考,不可直接作为法律意见。

## 能力边界

| 能力 | 状态 |
|------|------|
| ✅ 解析: .docx / .pdf (文本层) / .txt | 已实现 |
| ✅ 提取: 案号/法院/程序/日期/案由/争议焦点/法条引用/裁判结果 | 已实现 |
| ✅ 索引: SQLite + FTS5 + LIKE 双轨 | 已实现 |
| ✅ 幂等: 按 file_hash 跳过重复入库 | 已实现 |
| ✅ 防误用: max-depth 默认 3, 防把 /tmp 全索引 | 已实现 |
| ⚠️ 高级提取: 当事人/争议焦点的复杂解析 | 部分 (需人工核对) |
| ❌ OCR: 扫描件 PDF (需 pdftotext + OCR) | 未实现 |
| ❌ 联网分析: 法官胜诉率统计 (需多案例库) | 不在本技能 |

## 数据存储

默认数据库: `~/.prc-law/case-archive.db` (律师私有, 不入库 git)。

```bash
# 自定义路径
python3 scripts/case_indexer.py index <dir> --db /path/to/your/cases.db
```

## 操作步骤

### 步骤 1: 列出待入库文件

```bash
python3 scripts/case_indexer.py index <判决书目录> --max-depth 3 --min-size 200
```

- 报告文件总数 / 格式分布 / 预估处理时间
- **询问用户是否继续** (尤其文件 > 100 时)
- 提醒用户: 目录别放 `/tmp` 或 `/`(会误抓)

### 步骤 2: 执行入库 + 进度条

脚本会:
- 解析每个文件 (python-docx / pdfplumber / 纯文本)
- 提取 8+ 字段 (案号/法院/程序/日期/案由/争议焦点/法条引用/裁判结果)
- 按 file_hash 跳过已入库
- 写入 SQLite + 同步 FTS5

每 10 件打印进度, 失败文件记录到 `cases_errors.log`。

### 步骤 3: 质量检查

- 报告入库/跳过/失败数量
- 案号识别率 (有案号 / 总数)
- **如果识别率 < 50%**, 提示用户可能需要人工预处理:
  - 扫描件 PDF → 先 OCR
  - 非标准格式 → 手动复制纯文本

### 步骤 4: 检索测试

入库后做 3-5 个检索测试验证数据可用:
- "找最近 5 个涉及违约金的判决"
- "搜索我和朝阳区法院的过往"
- "我引用过民法典 577 条的案子有哪些"

## 检索 SQL 示例

律师可以通过 SKILL 触发检索, 后端脚本直接用 SQL:

```sql
-- 1. 全文搜索 (中文, 用 LIKE)
SELECT case_number, court, judgment_date, cause_of_action
FROM cases
WHERE dispute_focus LIKE '%违约金%'
   OR facts_found LIKE '%违约金%'
ORDER BY judgment_date DESC LIMIT 10;

-- 2. FTS5 (英文/数字/复杂查询)
SELECT case_number, court, snippet(cases_fts, 6, '«', '»', '…', 12)
FROM cases_fts WHERE cases_fts MATCH '劳动合同法 解除';

-- 3. 按法院统计
SELECT court, COUNT(*) AS n, SUM(CASE WHEN judgment_result LIKE '%支持%' THEN 1 ELSE 0 END) AS won
FROM cases GROUP BY court ORDER BY n DESC;

-- 4. 按法官引用法条
SELECT case_number, cited_statutes
FROM cases WHERE cited_statutes LIKE '%民法典第577条%';
```

## 输出格式

### 入库完成报告

```
发现 100 个法律文书 in ~/Documents/律师案卷/民商 (max_depth=3, min_size=200B)
  [10/100]  10.0% fe17a85... （2020）京01民初1234号 <- 张三案.txt
  [20/100]  20.0% 43f3a41... （2019）沪0115民初5678号 <- 李四案.docx
  ...
  [100/100] 100.0% cd1c91e... (案号未识别) <- 旧案_未标号.pdf

✅ 完成. 新入库 95 / 跳过 4 / 失败 1
⏱️  耗时 12.3s (平均 0.12s/件)
📂 DB: ~/.prc-law/case-archive.db (大小 124 KB)
📋 错误日志: ~/.prc-law/cases_errors.log (1 项, 查看手动处理)
```

### 检索结果

```
命中 3 条:

[1] （2020）京01民初1234号 | 北京市第一中级人民法院 | 二〇二〇年五月十五日
    案由: 合同纠纷
    摘要: 争议焦点: 被告是否应承担违约责任。
    法条: 中华人民共和国合同法第8条 | 中华人民共和国民法典第577条
    文件: ~/Documents/律师案卷/民商/张三案.txt

[2] ...
```

## 使用方式

### CLI

```bash
# 入库
python3 scripts/case_indexer.py index <dir> --db ~/.prc-law/case-archive.db

# 检索
python3 scripts/case_indexer.py search "违约金" --db ~/.prc-law/case-archive.db --limit 10

# 直接用 SQL (高级)
sqlite3 ~/.prc-law/case-archive.db "SELECT * FROM cases WHERE ..."
```

### Python API

```python
import subprocess

# 检索
result = subprocess.run(
    ["python3", "scripts/case_indexer.py", "search", query, "--db", db_path],
    capture_output=True, text=True
)
print(result.stdout)
```

## 不做的事

- ❌ 不调用 MCP (本技能纯本地)
- ❌ 不联网分析 (无外网依赖)
- ❌ 不替代人工核对 (提取结果仅供参考)
- ❌ 不存敏感元数据 (不含客户身份证号 / 银行账号)

## 维护

- 数据库入 `.gitignore` (律师案卷隐私)
- 定期备份: `cp ~/.prc-law/case-archive.db ~/backups/`
- 律所小组共享: 把 DB 放 SMB/NFS, 多律师只读 (避免并发写入冲突)

## 关联

- 数据基础: 已有 cail2018 (HF streaming 267 万判例)
- 检索入口: `scripts/case_client.py` (公开案例)
- 法条检索: `scripts/retrieval_router.py` (法条)
- 标注规范: `_foundation/source-label/SKILL.md`