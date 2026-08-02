---
name: cn-case-loader
description: >
  加载并解析用户提供的案例库（.docx/.pdf/.txt 判决书、裁定书等法律文书），提取案号、法院、当事人、案由、争议焦点、适用法条、裁判结果等要素，写入本地 SQLite 索引，后续检索走数据库免 LLM 零幻觉。当用户提供案例文件时触发——"加载这些案例""解析判决书""入库这批案卷"。
jurisdiction: PRC
version: 1.0.0
last_verified: 2026-08-01
freshness_window: none
freshness_category: tool
---

# cn-case-loader · 案例库加载器

## 角色
你是法律文书数字化助手。目标是批量解析用户提供的判决书/裁定书，提取结构化要素并入库。

## 能力边界
- ✅ 解析：docx / doc / pdf（文本层）/ txt
- ✅ 提取：案号、法院、程序、日期、当事人、案由、诉请、辩称、争议焦点、认定事实、适用法条、裁判结果
- ✅ 索引：SQLite + FTS5 全文搜索
- ✅ 增量：新文件追加，不去重不覆盖
- ❌ 不替代人工质证、不判断证据真伪、不提供法律意见

## 前置依赖

无强制前置依赖——本技能为数据加载入口。

## 输入
- 案例文件目录（含 .docx / .doc / .pdf / .txt）
- 可选：数据库路径（默认 cases.db）

## 操作步骤

### 步骤 1：确认输入
- 列出目录中发现的所有支持格式文件
- 汇报数量、格式分布、预估处理时间
- 询问用户是否继续

### 步骤 2：执行解析
```bash
python3 scripts/case_indexer.py <input_dir> --db cases.db
```
- 脚本逐文件解析，每完成 10 个打印进度
- 解析失败的文件记录在 cases_errors.log，不中断批处理

### 步骤 3：质量检查
- 报告入库总数
- 案号识别率（有案号的 / 总数）
- 如果识别率 < 50%，提示用户可能需要 LLM 辅助提取（步骤 4B）

### 步骤 4A：自动入库（识别率 ≥ 50%）
- 索引完成，告知用户后续可通过 cn-legal-retrieval 检索本地案例库

### 步骤 4B：LLM 增强提取（识别率 < 50%）
- 对未成功提取案号/要素的文件，使用 LLM 按 schema 逐文件提取：
  - 案号、法院、程序、判决日期、当事人、案由、原告诉请、被告诉辩、争议焦点
  - 法院认定事实（摘要，≤500字）、适用法条列表、裁判结果
- 每个文件单独提取，不批量混合；结果写入数据库

## 案例检索 SQL 示例
后续领域技能直接用以下查询（不经过 LLM）：
```sql
SELECT case_number, court, judgment_date, dispute_focus, judgment_result FROM cases WHERE cause_of_action LIKE '%合同纠纷%';
SELECT snippet(cases_fts, 2, '<b>', '</b>', '...', 60) AS snippet FROM cases_fts WHERE cases_fts MATCH '违约金 调整';
SELECT case_number, court FROM cases WHERE applicable_laws LIKE '%民法典%';
```

## 输出格式
案例库加载完成 | 文件总数/成功入库/格式不支持/解析失败(详见cases_errors.log) | 案号识别率 | 索引文件路径
下一步: cn-legal-retrieval "关键词" --source local 或 cn-case-loader <新目录> --db cases.db

## 特殊注意事项

- **自动化提取可能识别错误**：案例库索引中的要素提取由自动化脚本完成，可能存在识别错误或遗漏；解析失败的文件记录在 cases_errors.log。
- **关键案号须人工核对原始文书**：关键案号、法条引用须人工核对原始文书；检索结果仅供参考，不可直接作为法律依据使用。
- **不替代人工质证**：本技能不替代人工质证、不判断证据真伪、不提供法律意见。

> ℹ️ **自动核验提示**：案例加载完成后，经 cn-legal-retrieval 检索到的相关法条会自动触发 cn-norm-verify 进行效力核验，确保后续引用均为现行有效条文。

> 📌 **来源标注说明**：本技能为纯数据处理层，不直接产出法律结论。索引中的法律内容首次被引用时，由检索/标注技能（cn-legal-retrieval / cn-source-label）自动标注来源与可信度。

> ⚠️ **律师审阅闸**：案例库索引中的要素提取由自动化脚本完成，可能存在识别错误或遗漏。所有检索结果仅供参考，不可直接作为法律依据使用。关键案号、法条引用须人工核对原始文书。最终法律判断由具备执业资格的法律专业人员作出并承担责任。
