# 律鉴快速上手指南

> **面向人类用户的 5 分钟快速上手**
> 不需要法学期权，30 分钟内可以从零开始使用律鉴

## 0. 这是什么？

律鉴（PRC-Law）是一套**法律 AI 助手**——它不替代律师，而是让律师/法务在 5 分钟内完成原本需要 2-3 小时的法律检索、案例匹配、合同审查、文书起草工作。

**核心能力**：
- 📚 **检索**：实时检索中国现行法律 + 最高法指导案例（不自创法条）
- ⚖️ **推理**：完整法律推理链（请求权基础 → 抗辩 → 抗辩的抗辩）
- 📝 **起草**：判决书、法律意见书、律师函、和解协议
- 🔄 **时间锚点**：自动识别案件发生年份，使用**当时有效**的法条（避免误用新法判定旧案）

## 1. 安装前的准备

### 必需

- ✅ Claude Code（最新版）
- ✅ 元典开放平台 API Key（[open.chineselaw.com](https://open.chineselaw.com) 注册账号 → 个人中心 → 创建 API Key）
- ✅ Python 3.10+（用于运行 MCP bridge）

### 可选（用于高级功能）

- ⚪ 北大法宝 API Key（第二数据源，建议企业级使用）
- ⚪ 实践画像（个性化定制，见 §5）

## 2. 安装步骤（3 分钟）

### 步骤 2.1：克隆仓库

```bash
git clone https://github.com/godlockin/PRC-Law.git
cd PRC-Law
```

### 步骤 2.2：配置 API Key

```bash
# 方式 A：环境变量（推荐，安全）
export YUANDIAN_API_KEY="sk_your_key_here"

# 方式 B：复制模板并编辑
cp .mcp.json.example .mcp.json
# 然后编辑 .mcp.json 把 sk_replace_with_your_yuandian_key 替换为真实 key
```

> ⚠️ **安全提示**：
> - `.mcp.json` 已在 `.gitignore` 中，不会被 git 追踪
> - 永远不要把含真实 key 的 `.mcp.json` 提交到 git
> - 如果发现 key 泄露，立即到 [open.chineselaw.com](https://open.chineselaw.com) 个人中心**轮换 key**

### 步骤 2.3：验证 MCP 连接

```bash
# 在 Claude Code 中测试
"请用律鉴检索'民法典第 537 条'"
```

如果返回法条原文，说明 MCP 已正确连接。

### 步骤 2.4（可选）：添加为 Claude Code 插件

```bash
# 方式 A：作为本地技能
cp -r _foundation _domains _compound ~/.claude/skills/prc-law

# 方式 B：作为 Claude Code 插件
/plugin marketplace add /path/to/PRC-Law
/plugin install prc-law@prc-law
```

## 3. 第一次使用（2 分钟）

### 场景 A：律师 - 快速案例分析

```
在 Claude Code 中输入：

请分析以下案件：
2024 年 6 月，我的客户（原告）与被告签订一份买卖合同，
约定货款 100 万元。被告收货后仅支付 60 万元，剩余 40 万元
拖欠至今。客户已多次催讨无果。

请按律鉴流程：
1. 检索相关法条（民法典合同编）
2. 评估胜诉可能性
3. 给出诉讼策略建议
```

律鉴会自动：
1. 调用 `cn-legal-retrieval` 检索相关法条
2. 调用 `cn-element-extraction` 提取案情要素
3. 调用 `cn-reasoning` + `cn-outcome-forecast` 评估胜诉可能性
4. 调用 `cn-argument-chain` 构建论证
5. 输出完整分析报告 + 律师审阅闸

### 场景 B：法务 - 快速合同审查

```
请审查这份 SaaS 服务协议（粘贴合同内容）
```

律鉴会自动调用 `cn-contract-full-review` 的 6-Agent 编排：
- 合规审查 / 风险量化 / 攻防设计 / 生命周期 / 商业平衡 / 校对审查
- 5 维评分（合规 30% / 财务 25% / 防御 20% / 履行 15% / 商业 10%）
- 7 章结构化报告

### 场景 C：法务总监 - 紧急数据泄露响应

```
公司用户数据库发生疑似泄露，影响约 50 万用户。
请启动律鉴的危机响应流程。
```

律鉴会自动调用：
- `cn-crisis-response` (P0 应急预案)
- `cn-data-breach-response` (数据泄露专项)
- `cn-PIA` (个人信息影响评估)
- 输出 0-24h 时间表 + 监管报告模板

### 场景 D：法学生 - 系统学习

```
我想系统学习"合同请求权基础"。
请按律鉴的学习路径生成学习计划。
```

律鉴会自动调用：
- `cn-concept-comprehension` (概念入门)
- `cn-civil-claim-analysis` (请求权基础方法论)
- 输出学习路径 + 资料清单 + 自测题

## 4. 常用命令速查

| 我想做... | 我应该说... |
|----------|------------|
| 检索法条 | "请用律鉴检索'民法典第 X 条'" |
| 审查合同 | "请用律鉴审查这份合同：[粘贴]" |
| 分析案例 | "请用律鉴分析这个案件：[案情]" |
| 起草判决书 | "请按律鉴格式起草一审判决书" |
| 法律意见 | "请用律鉴出具法律意见书" |
| 和解评估 | "对方提议 X 万和解，请用律鉴评估是否接受" |
| 数据合规 | "请用律鉴做个人信息影响评估" |
| 内部调查 | "收到员工受贿举报，请按律鉴内部调查流程处理" |
| 立法跟踪 | "请用律鉴监测民法典是否有新修订" |
| 法条学习 | "请用律鉴系统介绍'格式条款'规则" |

## 5. 个性化定制（可选，10 分钟）

律鉴支持个性化定制，根据你的执业角色调整输出风格。

### 步骤 5.1：运行冷启动面试

```
在 Claude Code 中输入：
/cn-cold-start
```

按提示回答 6-8 个问题：
1. 执业身份（法务/律师/产品律师/法学生）
2. 执业年限
3. 业务领域偏好
4. 风险偏好（保守/平衡/进取）
5. 输出格式偏好
6. 术语严格度

律鉴会自动写入 `CLAUDE.md` 的"实践画像"段。

### 步骤 5.2：手动定制

直接编辑 `CLAUDE.md`：

```yaml
---
jurisdiction: PRC
last_updated: 2026-08-04

# 实践画像
practice_type: 法务商业
industry: 互联网/科技
team_size: 5-20 人
risk_preference: 保守

# 领域偏好
domain_weights:
  commercial: 3      # 日常
  corporate: 2       # 经常
  labor: 3           # 日常
  privacy: 2         # 经常
  ...
```

### 步骤 5.3：加载本地案例库（可选）

```bash
# 把本地案例放到
mkdir -p cases/
cp my-cases/*.docx cases/

# 用 cn-case-loader 解析入库
python3 scripts/case_loader.py --input cases/ --db cases.db
```

之后律鉴会自动在本地案例库中检索。

## 6. 故障排查

| 问题 | 排查 |
|------|------|
| 检索不到法条 | 检查 `YUANDIAN_API_KEY` 是否设置、API Key 是否有效 |
| 检索结果错误 | 检查网络是否能访问 `open.chineselaw.com` |
| 总是说"未配置" | 重启 Claude Code 让其重新加载 MCP 配置 |
| 输出格式不符 | 运行 `/cn-cold-start` 更新偏好 |
| 输出有 mock 嫌疑 | 律鉴承诺**不引入 mock 数据**——若发现请举报 |

## 7. 进阶用法

### 7.1：跑 Demo 体验

律鉴有 6 个预制的演示案例，让你在 5-10 分钟内体验完整能力：

```bash
# D2 demo（可全自动运行）
python3 scripts/demo_runner.py D2

# 查看所有 demo
python3 scripts/demo_runner.py list

# 详细说明
cat docs/DEMOS.md
```

### 7.2：跑 Benchmark 看能力

```bash
# 测试 MCP API 是否正常
python3 scripts/benchmark_summary.py

# 跑 5 个最高法指导案例
python3 scripts/benchmark_runner.py

# 生成法院画像
python3 scripts/judge_pattern.py --court "最高人民法院" --cause "合同纠纷"
```

### 7.3：法条跟踪

```bash
# 添加法条到监听清单
python3 scripts/statute_monitor.py --add --fgmc "民法典" --ftnum "第五百三十七条"

# 扫描所有监听法条
python3 scripts/statute_monitor.py --scan
```

## 8. 隐私与合规

- ⚠️ **不要**在 Claude Code 中输入真实客户全名、身份证号、银行卡号
- ⚠️ **不要**上传未脱敏的真实合同、判决书、内部文件
- ✅ 可以使用案件代号（如"客户A"）
- ✅ 可以使用脱敏后的案件材料
- ✅ 律鉴所有输出均带"律师审阅闸"标记，不构成法律意见

## 9. 给非技术用户的说明

> **"我不懂技术，能用律鉴吗？"**

可以。律鉴本质上是**装在 Claude Code 里的法律助手**——你只需要像和同事聊天一样说出你的问题，律鉴会自动调用最合适的能力。

**几个使用范例**：

| 你说 | 律鉴做什么 |
|------|-----------|
| "请审查这份合同" | 6-Agent 并行审查 → 7 章报告 |
| "这是什么法律？" | 检索现行法 + 解释 + 类案 |
| "我胜诉的可能性多大？" | 类案匹配 + 概率评级 |
| "请起草一份判决书" | 完整法律文书 + 律师审阅闸 |
| "这个法条还有效吗？" | 法条状态 + 历史版本 |

## 10. 下一步

- 📖 阅读 [README.md](README.md) 了解完整能力矩阵
- 📊 阅读 [docs/DEMOS.md](docs/DEMOS.md) 查看演示案例
- 🏛️ 阅读 [CLAUDE.md](CLAUDE.md) 了解全局推理链
- 📝 个性化定制：运行 `/cn-cold-start`
- 🧪 跑 demo：`python3 scripts/demo_runner.py D2`

---

> ⚖️ **律师审阅闸**: 本快速上手指南为 AI 辅助使用说明，不构成法律意见。律鉴输出均带"律师审阅闸"标记。最终法律判断由具备执业资格的法律专业人员作出并承担责任。