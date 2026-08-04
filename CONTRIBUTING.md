# 贡献指南（CONTRIBUTING）

> 欢迎为律鉴（PRC-Law）做贡献。本指南说明开发流程、规范、提交标准。

## 适用对象

- **法律从业者**: 律师、法务、法官助理 - 提交真实案例、模板、判例分析
- **开发者**: 软件工程师 - 提交 skill、脚本、CI/CD
- **学者**: 法学教师、研究生 - 提交方法论、文献综述、教学 demo
- **AI 工程师**: 提示工程、agent 系统 - 提交 skill 编排模式

## 贡献类型

### 1. 报告问题
- 在 GitHub Issues 提交 bug 报告或改进建议
- 描述清楚：复现步骤、预期结果、实际结果、环境
- 用 `bug` 或 `enhancement` 标签

### 2. 提交技能（SKILL.md）
- 新增法律领域技能
- 改进现有技能的操作步骤
- 增加案例库的真实案例

### 3. 提交代码
- 自动化脚本（`scripts/`）
- CI/CD 改进（`.github/workflows/`）
- MCP bridge 优化

### 4. 提交文档
- 改进 README/QUICKSTART
- 翻译（目前仅中文）
- 增加 demo 案例

---

## 技能开发规范

### 1. 命名规范

| 类型 | 前缀 | 例子 |
|------|------|------|
| 原子技能（基础） | `cn-` | cn-legal-retrieval, cn-reasoning |
| 领域技能 | 无 | contract-full-review, nda-review |
| 复合技能 | 无 | judgment-draft, legal-opinion |

### 2. 文件结构

```
_skill-name/
└── SKILL.md         # 唯一必需文件
```

如果需要附属文件：
```
_skill-name/
├── SKILL.md         # 主文件
├── references/      # 法规、案例参考
│   └── core-rules.md
├── templates/       # 模板（如需）
└── examples/        # 样例输出
```

### 3. SKILL.md 模板

```yaml
---
name: <kebab-case-name>
description: >
  <能力描述 + 触发条件>。
  触发："<用户可能说的关键词>"。
jurisdiction: PRC | multi
version: 1.0.0
last_verified: YYYY-MM-DD
freshness_window: <天数 | none>
freshness_category: <base | domain | tool>
---

# <skill 中文名>

> <vX.X 升级说明（如适用）>

## 角色
<这个 skill 是谁，扮演什么角色>

## 能力边界
- ✅ <能做的>
- ❌ <不能做的>

## 前置依赖
- <依赖哪些 skill>

## 操作步骤
### 步骤 N: <步骤名>
<具体操作>

## 输出格式
<Markdown 模板>

## 质量门控
- [ ] <检查项>

## 借鉴差异说明
<如借鉴外部项目：来源 + 边界 + 不引入什么>

## 特殊注意事项
<边界、风险、隐私>

> ⚠️ **律师审阅闸**：本 skill 为 AI 辅助分析工具，不构成法律意见。
```

### 4. 强制执行规范

- ❌ **禁止引入 mock 数据**（虚假案件、虚构客户）
- ❌ **禁止引用未经第三方审核的自评数据**
- ❌ **禁止硬编码 API Key**（用环境变量）
- ❌ **禁止在 SKILL.md 中写死具体法条号**（用 `[schema:retrieval-hint:...]`）
- ✅ **必须使用 [schema:retrieval-hint:领域·子项] 占位符**
- ✅ **必须标注来源（六态标签）**
- ✅ **必须包含律师审阅闸**
- ✅ **必须说明借鉴边界**（如借鉴外部项目）

---

## 开发流程

### 1. Fork & Clone
```bash
git clone https://github.com/your-fork/PRC-Law.git
cd PRC-Law
```

### 2. 创建分支
```bash
git checkout -b feat/your-skill-name
```

### 3. 开发
- 编写 `SKILL.md`（参照上面的模板）
- 如有脚本，放入 `scripts/`
- 测试你的 skill（最好用真实数据）

### 4. 提交前检查清单
- [ ] 命名符合规范（`cn-` 前缀用于原子技能）
- [ ] `SKILL.md` 包含全部必需段
- [ ] 没有硬编码 API Key
- [ ] 没有 mock 数据/虚构案例
- [ ] 没有引用未经第三方审核的自评数据
- [ ] 包含律师审阅闸
- [ ] 如果借鉴了外部项目，标注"借鉴差异说明"
- [ ] 跑过至少 1 次端到端测试

### 5. 提交 & 推送
```bash
git add <files>
git commit -m "feat(skill): <description>"
git push origin feat/your-skill-name
```

### 6. 创建 PR
- 标题：`feat(skill): <description>` 或 `fix(skill): <description>`
- 描述：说明动机、变更、测试方法
- 关联相关 Issue

---

## 测试要求

### SKILL.md 的最小测试

每个新 skill 至少要展示：
1. **真实输入样例**（不是"假设有 A 公司"）
2. **期望输出**（不是"应该返回 A"）
3. **跨能力关联**（说明与哪些 skill 协同）

### 推荐测试：跑 Benchmark

```bash
# 测试法条检索能力
python3 scripts/benchmark_summary.py

# 测试所有 6 个 demo
for i in 1 2 3 4 5 6; do
  python3 scripts/demo_nd$i.py
done
```

### CI 自动测试

律鉴的 GitHub Actions 会在 PR 时自动跑：
- benchmark.yml 跑多维能力测试
- 每周一 02:00 UTC 跑全量 Benchmark

---

## 法律内容贡献规范

### 提交真实案例时

- ✅ 仅使用**已公开**的最高法指导案例或法院公开判决
- ✅ 如有脱敏需求，使用化名但保留案号
- ✅ 标注真实出处
- ❌ 不要使用真实客户/当事人名称
- ❌ 不要使用未公开的案件细节

### 引用法条时

- ✅ 使用 `[schema:retrieval-hint:领域·子项]` 占位符
- ✅ 标注"行为时版本"或"现行版本"
- ✅ 引用法条时使用"按民法典第 X 条"（带版本）
- ❌ 不要在 SKILL.md 中写死具体条号

### 提交司法解释时

- ✅ 标注发布机关、生效日期
- ✅ 标注最新修正日期
- ✅ 如有废止/失效版本，明确说明

---

## 安全规范（重要！）

### 绝对禁止
- ❌ **永远不要**提交含真实 API Key、Token、密码的 commit
- ❌ **永远不要**提交 `.mcp.json`（已在 `.gitignore` 中）
- ❌ **永远不要**引用未公开的案件、客户、商业秘密

### 如发现安全漏洞
- 立即通过 GitHub Security Advisories 私下报告
- 不要在公开 Issue 中披露漏洞详情

### 历史教训
- ⚠️ 律鉴 v1.0 commit (50c59d3) 曾硬编码元典 API Key
- ✅ 已在 v8.3 通过 `git filter-repo` 完整删除
- ✅ 历史 commit hash 已重写（从 2fce4d7 起算）

---

## 文档贡献

### README 更新
- 添加新能力 → 更新能力矩阵
- 新增 benchmark → 更新评分
- API 变化 → 更新技术实现

### Demo 扩展
- 遵循 [docs/DEMOS.md](docs/DEMOS.md) 的格式
- 每个 demo 基于真实案例
- 提供完整输入 + 期望输出

### 翻译
- 律鉴目前仅中文
- 翻译 PR 需保持法律术语准确性
- 建议法学期术语参考全国人大法工委标准

---

## 沟通渠道

- **GitHub Issues**: 问题报告、功能建议
- **GitHub Discussions**: 一般讨论、提问
- **Pull Requests**: 代码贡献

---

## 许可证

提交即同意以律鉴自定义许可证（个人免费/商用授权）授权你的贡献。

详见 [LICENSE](LICENSE) 文件。

---

## 行为准则

- 尊重多元、包容差异
- 建设性反馈
- 专注于法律专业性
- **AI 辅助 + 人类判断** = 最佳实践

---

> ⚠️ **律师审阅闸**：本贡献指南为社区规范，不构成法律意见。最终法律判断由具备执业资格的法律专业人员作出并承担责任。