# cn-pleading-templates · 模板索引

8 套律师常用文书模板,位于 `templates/` 目录:

| 模板 | 文件 | 程序 | 适用 |
|------|------|------|------|
| 民事起诉状 | `civil-complaint.md` (在 SKILL.md 中) | 一审 | 合同/侵权/借贷/劳动等民事 |
| **民事答辩状** | `civil-defense.md` | 一审 | 被告反驳原告诉求 |
| **民事上诉状** | `civil-appeal.md` | 二审 | 不服一审, 提起上诉 |
| **民事再审申请书** | `civil-retrial.md` | 再审 | 符合民诉法 §207 条件 |
| **劳动仲裁申请书** | `labor-arbitration.md` | 仲裁前置 | 劳动争议必须先仲裁 |
| **行政复议申请书** | `admin-review.md` | 复议 | 部分案件复议前置 |
| **律师函** | `lawyer-letter.md` | 非诉 | 催款/侵权警告/和解 |
| **调解协议** | `mediation-agreement.md` | 非诉 | 双方和解 |
| **授权委托书** | `power-of-attorney.md` | 通用 | 律师代理必备 |
| **离婚起诉状** | `divorce-complaint.md` | 一审 | 婚姻家事专项 |
| **刑事申诉状** | `criminal-appeal.md` | 申诉/再审 | 刑事案件申诉 |

> 注: 民事起诉状 (最常用) 直接在 `SKILL.md` 中, 其他 10 套在 `templates/` 子目录.

## 使用方式

律师/Claude 通过 description 字段自动触发:

```
律师: "帮我起草一份民事起诉状, 是合同纠纷, 对方欠款 200 万"
Claude: → 加载 cn-pleading-civil-complaint
      → 输出模板, 律师按 [占位符] 填写
      → 自动应用 cn-norm-verify 校验法条
```

## 模板结构 (统一)

每套模板:
1. **必填字段表** — 律师需提供的具体信息
2. **完整正文** — Markdown 格式, 可直接复制
3. **自动检查清单** — 提交前自检
4. **关联技能** — 链接到其他 SKILL
5. **实务提示** — 律师经验

## 不做的事

- ❌ 不替律师决定案由/管辖/诉讼请求
- ❌ 不绕过律师审阅闸
- ❌ 不直接提交法院 (必须律师复核)

## 扩展建议

未来可能新增:
- 民事保全申请书 (财产保全/证据保全)
- 强制执行申请书
- 破产申请书
- 公司解散之诉
- 第三人撤销之诉
- 检察院抗诉申请书

贡献模板: 复制 `templates/civil-defense.md` 结构, 提交 PR 到 `_domains/litigation/skills/cn-pleading-templates/templates/`.

## 关联

- `cn-norm-verify` — 法条现行有效校验 (必备)
- `cn-civil-claim-analysis` — 请求权基础鉴定
- `cn-element-extraction` — 案情要素提取
- `cn-evidence-evaluation` — 证据三性审查
- `cn-pleading-appeal-deadline-calc` — 上诉期计算
- `_domains/litigation/skills/brief-section-drafter` — 章节级起草