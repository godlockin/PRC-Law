# 典型用例 001: 合同审查

**输入:** 一份标准软件采购合同（含保密条款、违约责任、管辖条款）
**预期:** legal-retrieval 被调用 | 输出含 source-label 标注 | 末尾有 Lawyer Review Gate
**检查项:**
- [ ] 无静态法条数字
- [ ] [schema:retrieval-hint] 使用正确
- [ ] 来源标注完整
