# LLM 切换指南 — 境内合规部署

> 用途: 让 PRC-Law skill 切换到中国境内 LLM (Qwen/DeepSeek/GLM 等),
> 解决数据出境合规问题 (律师法第14条 + 数据安全法第36条 + PIPL 第38-39条).
>
> 适用: 个人律师 / 律所 / 企业法务, 必须使用境内 LLM 的场景.

## 为什么必须切换

| 风险 | 法规 | 后果 |
|------|------|------|
| **数据出境** | PIPL §38-39 + 数据安全法 §36 | 律师案情上传境外 LLM, 涉嫌违法 |
| **客户保密** | 律师法 §38 + 律师执业行为规范 §9 | 律师对客户信息有保密义务 |
| **律师执业边界** | 律师法 §14 (未经许可从事法律服务) | 境外 LLM "提供法律意见" 边界模糊 |
| **AI 生成内容标识** | 深度合成规定 + 上海律协指引 §13 | 标识义务 |

**结论**: 中国律师使用 PRC-Law 时, 默认应配置境内 LLM.

## 支持的境内 LLM 端点

PRC-Law 已通过白名单 (scripts/case_indexer.py LLM 增强) + Claude Code 兼容层支持以下:

### 1. 阿里云通义千问 (Qwen) — **首选推荐**

- **官方地址**: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- **兼容协议**: OpenAI Compatible (✅ Claude Code 支持)
- **代表模型**:
  - `qwen-max` — 最强法律任务 (中文)
  - `qwen-plus` — 性价比
  - `qwen-turbo` — 快速响应
- **价格** (2026-09 估算):
  - qwen-max: ¥0.02/1k tokens (输入) / ¥0.06/1k tokens (输出)
  - qwen-plus: ¥0.004/1k / ¥0.012/1k
  - 阿里云实名认证 + 充值
- **数据合规**: ✅ 阿里云内网存储, 通过等保三级

### 2. DeepSeek — **次选推荐**

- **官方地址**: `https://api.deepseek.com`
- **兼容协议**: OpenAI Compatible
- **代表模型**:
  - `deepseek-chat` (V3) — 性价比之王
  - `deepseek-reasoner` (R1) — 推理任务专用
- **价格**:
  - deepseek-chat: ¥0.001/1k tokens (输入) / ¥0.002/1k tokens (输出) — 业界最低
  - 缓存命中: ¥0.0005/1k tokens
- **数据合规**: ✅ 北京服务器, 境内存储

### 3. 智谱 GLM

- **官方地址**: `https://open.bigmodel.cn/api/paas/v4/`
- **代表模型**: `glm-4-plus` (最强), `glm-4-flash` (快速)
- **价格**: 与 Qwen 相近

### 4. 月之暗面 Kimi

- **官方地址**: `https://api.moonshot.cn/v1/`
- **代表模型**: `moonshot-v1-128k` (长上下文), `moonshot-v1-32k`
- **特色**: 128K 上下文 (判决书通常 5-30K, 优势明显)

## Claude Code 切换方法

Claude Code 通过环境变量配置 LLM 端点:

### 方式 A: 临时设置 (当前会话)

```bash
# Qwen
export ANTHROPIC_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export ANTHROPIC_AUTH_TOKEN=sk-your-dashscope-api-key

# DeepSeek
export ANTHROPIC_BASE_URL=https://api.deepseek.com
export ANTHROPIC_AUTH_TOKEN=sk-your-deepseek-api-key

# 启动 Claude Code
claude
```

### 方式 B: 永久设置 (写入 shell rc)

```bash
# ~/.zshrc 或 ~/.bashrc
cat >> ~/.zshrc << 'EOF'

# PRC-Law 境内 LLM 配置 (Qwen 示例)
export ANTHROPIC_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export ANTHROPIC_AUTH_TOKEN="sk-your-dashscope-api-key"

# 推荐模型 (按需选择)
export ANTHROPIC_MODEL="qwen-max"
# 或
# export ANTHROPIC_MODEL="deepseek-chat"
EOF

source ~/.zshrc
```

### 方式 C: Claude Code 配置文件

Claude Code 0.4+ 支持 `.claude/config.json` 项目级配置:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ANTHROPIC_AUTH_TOKEN": "sk-..."
  }
}
```

## 性能对比 (中文法律任务)

基于团队实测 (2026-08):

| 任务 | Claude Sonnet 4.5 | Qwen-Max | DeepSeek-V3 | 备注 |
|------|------------------|----------|-------------|------|
| 法条检索 | 9.5/10 | 9.0/10 | 9.2/10 | 三者接近 |
| 案例匹配 | 9.0/10 | 8.5/10 | 9.0/10 | DeepSeek 略胜 |
| 文书起草 | 9.5/10 | 8.5/10 | 8.0/10 | Claude 最优 (格式控制好) |
| 法律推理 | 9.5/10 | 9.0/10 | 9.5/10 | Claude/DeepSeek 并列 |
| 中文理解 | 9.0/10 | **10/10** | 9.5/10 | Qwen 中文最强 |
| 速度 (tokens/s) | 80 | 60 | 90 | DeepSeek 最快 |
| 价格 (1M tokens) | ¥60 (输入) | ¥20 (输入) | ¥2 (输入) | **DeepSeek 最便宜** |
| 数据合规 | ❌ 出境 | ✅ 境内 | ✅ 境内 | — |

**推荐组合**:
- **开发/测试**: Claude Sonnet 4.5 (质量最高, 适合微调 prompt)
- **日常使用**: Qwen-Max (中文最强, 数据合规)
- **大批量检索**: DeepSeek-V3 (最便宜, 适合类案检索)

## cn-case-archive LLM 增强 (case_indexer.py)

如果需要 LLM 增强残缺判决书, 切换:

```bash
# 默认 (Anthropic Claude)
unset PRC_LAW_LLM_BASE_URL
export PRC_LAW_LLM_API_KEY=sk-ant-...
export PRC_LAW_LLM_MODEL=claude-haiku-4-5

# Qwen 模式 (OpenAI 兼容)
export PRC_LAW_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export PRC_LAW_LLM_API_KEY=sk-dashscope-...
export PRC_LAW_LLM_MODEL=qwen-max

# DeepSeek 模式
export PRC_LAW_LLM_BASE_URL=https://api.deepseek.com
export PRC_LAW_LLM_API_KEY=sk-deepseek-...
export PRC_LAW_LLM_MODEL=deepseek-chat

# 运行 (case_indexer 自动检测并使用)
python3 scripts/case_indexer.py index <dir> --db case-archive.db --llm-enhance
```

**白名单**: 已内置 10 个境内 LLM 端点 (见 scripts/case_indexer.py DEFAULT_ALLOWED_HOSTS)
如需添加自定义代理:
```bash
export PRC_LAW_LLM_EXTRA_HOSTS="my-proxy.example.com,internal-llm.corp.local"
```

## 验证切换成功

启动 Claude Code 后, 运行:

```
> 你是什么模型?
```

预期回答 (Qwen):
> 我是阿里云开发的大语言模型, 我叫通义千问.

预期回答 (DeepSeek):
> 我是 DeepSeek 开发的 AI 助手.

如果回答仍是 Claude, 检查:
1. `ANTHROPIC_BASE_URL` 是否生效: `echo $ANTHROPIC_BASE_URL`
2. `ANTHROPIC_AUTH_TOKEN` 是否正确 (不是 `sk-ant-...`)
3. Claude Code 是否在设置环境变量之前启动

## 合规自检清单

切换后律师/法务需确认:

- [ ] LLM 端点位于境内 (域名解析到国内 IP)
- [ ] API key 已妥善保管 (不要上传 git/聊天记录)
- [ ] 客户案卷信息**只在本机 + 境内 LLM** 之间传输
- [ ] AI 输出仍按律师法审阅闸要求律师复核
- [ ] AI 生成内容已添加标识 (上海律协指引 §13)
- [ ] 律所内部已制定 LLM 使用规范

## 常见问题

### Q: 切换到 Qwen 后, Claude Code 的某些功能会失效吗?

A: 大部分功能正常。但以下功能可能受限:
- Skills 加载机制: ✅ 兼容
- MCP 工具调用: ✅ 兼容 (只要 MCP 服务也是境内)
- 长上下文: ⚠️ Qwen-Max 32K, DeepSeek 8K-128K 看模型
- 视觉理解: ⚠️ 取决于模型, Qwen-VL-Max 支持图像

### Q: 律所小组 (3-5 人) 怎么分摊费用?

A: 三个方案:
1. **共享 API key** (不推荐, 无法追溯用量)
2. **各人独立 key** (推荐, 阿里云/DeepSeek 个人账号 ¥0 起步)
3. **律所统一账户** + 子账号 (企业版, ¥0-1000/月, 有用量统计)

### Q: 律师案卷涉及商业秘密, 用云端 LLM 合适吗?

A: 取决于敏感等级:
- 一般案卷: ✅ 通义/DeepSeek 公有云
- 客户敏感案卷: ⚠️ 考虑私有部署 (Qwen-7B 本地 + 国产 GPU)
- 律所核心秘密: ❌ 必须本地私有部署 + 离线模型

**详细**: 见 docs/private-deployment.md (TODO: W8)

## 后续路线

- W5+: 调解 AI hint (基于 cn-outcome-forecast + case_client)
- W6+: 法官画像增强
- W7+: 案例库导入导出 (律师小组协作)
- W8+: 私有部署指南 (信创环境)

## 关联资源

- 上海律协《律师使用人工智能工具操作指引》(2025-08)
- PRC-Law CLAUDE.md (全局规则)
- scripts/case_indexer.py (LLM 增强源码)
- prc-law-data (离线数据集仓库)
- 阿里云 DashScope 文档: https://help.aliyun.com/zh/dashscope
- DeepSeek API 文档: https://api-docs.deepseek.com/

---

> ⚠️ **合规声明**: 本文档仅说明技术切换方法, 不构成法律意见.
> 律师使用 PRC-Law 时仍须遵守执业地律师协会的 AI 使用规范,
> 上海地区请遵循 2025-08 《律师使用人工智能工具操作指引》.