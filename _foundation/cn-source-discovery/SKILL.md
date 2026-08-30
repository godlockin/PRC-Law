---
name: cn-source-discovery
description: 当 PRC-Law 数据源路径变更或新增时,告诉开发者如何在最高法/最高检/国法库/北大法宝 官网手动找到正确的栏目 URL 或 API 端点。包括浏览器开发者工具拦截 fetch、抓包、看 SPA 路由、识别 captcha 触发点等方法。当脚本 fetch_court_guides.py / fetch_flk_npc.py 返回 0 条或 HTTP 500 时使用。
---

# cn-source-discovery · 手动发现数据源端点

## 为什么需要这个

PRC-Law 的爬虫脚本 (`scripts/fetch_*.py`) 依赖外部数据源的 URL/API 端点。**官方源会变**：
- 国法库 (`flk.npc.gov.cn`) 是 Vue SPA, JS bundle 升级 → endpoint 路径变
- 最高法 (`court.gov.cn`) 栏目路径可能重组
- 北大法宝 (`pkulaw.com`) 不对个人开放 API, 仅机构订阅

每 3-12 个月需要重新探测。本 skill 是给开发者(不是用户)用的。

## 工具准备

| 工具 | 用途 |
|------|------|
| **Chrome DevTools (Network tab)** | 看 SPA 实际请求的 XHR/fetch |
| **Playwright MCP** (`browser_*`) | 在 Claude Code 里用, 渲染 SPA + 监听 fetch |
| **curl / `urllib.request`** | 测试单 endpoint 是否通 |
| **View Page Source + 找 JS bundle** | 静态分析 (SPA 找不到 data 走这条) |

## 场景 1: 国法库 (flk.npc.gov.cn)

### 反爬虫现状 (2026-08 实测)

- ❌ **纯 HTTP POST `/law-search/search/list` 返 500 "系统异常"** — 需要 captcha session
- ❌ **SPA 详情页正文加载 JS error** — captcha 通过才显示
- ❌ **绕过 captcha = 违反国法库 ToS**, 不建议尝试
- ✅ **主页搜索 + 热门查询可访问** — 仅元数据

### 替代方案 (推荐)

不要爬国法库。改用以下任一公开源:

| 替代源 | URL | 格式 | 工作量 |
|--------|-----|------|--------|
| **国务院政策文件库** | `https://www.gov.cn/zhengce/` | 静态 HTML, **无反爬虫** | 中 |
| **北大法宝免费版** | `https://www.chinalawinfo.com` | 部分法律免费 (需注册) | 低 |
| **GitHub 法律数据集** | `https://github.com/cn-docs/civil-code` (民间) | markdown | 低 |
| **学术合作 (大学 IP)** | 知网/万方 | 全文 | 0 (已有 IP) |

### 如果仍要爬国法库 (需要人力 captcha)

1. 用浏览器打开 `https://flk.npc.gov.cn/`
2. 通过 captcha 验证
3. F12 → Network → 找 `/law-search/` 开头的 XHR 请求
4. 复制 **Request Headers** 里的 Cookie / XSRF-TOKEN
5. 把 Cookie 写进 `scripts/fetch_flk_npc.py` 的 `NPCSession.__init__`

⚠️ Cookie 通常 1-24h 过期, 需要定期更新; **无法工程化自动化**

## 场景 2: 最高法 (court.gov.cn)

### 找正确栏目 URL

1. 打开 `https://www.court.gov.cn/`
2. 看顶部导航: **"法院新闻 > 指导案例" / "公报案例" / "典型案例"**
3. 进入栏目页, F12 → Network → 翻页看 XHR
4. 复制 `Request URL` + `Query String` 模板
5. 通常是 `https://www.court.gov.cn/xxx/xxxData.json` 或 `?page=N`

### 当前 `scripts/fetch_court_guides.py` 走的路径

```python
COURT_GUIDE_PATHS = [
    "/fabu/gengduo/15/",   # 猜测, 实测 0 条
    "/fabuduanbai/",      # 猜测
]
```

**修正步骤**:
1. 去 court.gov.cn 手动看导航, 复制**真实**的"指导案例"栏目链接
2. 替换 `COURT_GUIDE_PATHS`
3. 重跑 `python3 scripts/fetch_court_guides.py --list`

### 用 Playwright MCP 探测 (推荐)

```
mcp__plugin_playwright_playwright__browser_navigate https://www.court.gov.cn/
mcp__plugin_playwright_playwright__browser_snapshot depth=3
→ 看导航菜单, 找"指导案例"按钮
mcp__plugin_playwright_playwright__browser_click element=指导案例
mcp__plugin_playwright_playwright__browser_evaluate function=() => {
  window.__captured = [];
  const origFetch = window.fetch;
  window.fetch = (...args) => {
    window.__captured.push(typeof args[0]==='string'?args[0]:args[0].url);
    return origFetch(...args);
  };
  return 'listener installed';
}
→ 翻页触发 fetch
mcp__plugin_playwright_playwright__browser_evaluate function=() => window.__captured
→ 拿到真实 API URL
```

## 场景 3: 北大法宝 (pkulaw.com)

- **不对个人开放 API**
- 机构订阅用户: 浏览器登录 → F12 Network → 复制 search 请求模板
- 个人唯一路径: 用 `chinalawinfo.com` 免费版(仅少量法律)

## 场景 4: 元典 (open.chineselaw.com)

✅ **已认证**: `/law-search/search/list` 风格的 endpoint 在 `scripts/yuandian_mcp_bridge.py`

### 当 method 找不到时修复

`retrieval_router.py` 当前用 `law.search`, 实测返 `-32601 Method not found`:

```
$ python3 /tmp/trace-l1.py
L1: {'jsonrpc': '2.0', 'id': 0, 'error': {'code': -32601, 'message': 'Method not found: law.search'}}
```

**修复**:
1. 看 `scripts/yuandian_mcp_bridge.py` 支持的 method 列表
2. 替换 `retrieval_router.py:88` 的 `"law.search"`
3. 真实常见名: `tools/call`, `yuandian.law.search`, `case.search` 等

## 反爬虫应对清单

| 信号 | 应对 |
|------|------|
| HTTP 500 "系统异常" | 后端反爬虫, 改用 HTML 公开源 |
| HTTP 403 Forbidden | IP 黑名单, 换 IP/VPN 或停止 |
| HTTP 419 / XSRF | 需要 captcha, 不能工程化 |
| SPA 详情页空白 | captcha 未通过 |
| 翻页后突然返 HTML | 风控触发, 降速 (`PRC_LAW_RATE_LIMIT`) |

## 决策树

```
fetch_*.py 失败
├─ 0 条结果?
│  └─ 栏目路径猜错 → 用 Playwright MCP 重新发现
├─ HTTP 500?
│  └─ 反爬虫 → 放弃爬, 改用 gov.cn / 学术 IP
├─ HTTP 403?
│  └─ IP 黑名单 → 暂停 24h 或换网络
└─ method not found?
   └─ 改 method 名 (看 bridge.py)
```

## 维护 checklist

- [ ] 每季度手动访问国法库, 看是否升级接口
- [ ] 每月手动访问 court.gov.cn, 看栏目是否重组
- [ ] 每年检查元典 method 列表
- [ ] 北大法宝每 6 个月检查机构订阅状态

## 关联

- `scripts/fetch_flk_npc.py` — 国法库 HTTP 爬虫 (实测被反爬虫挡)
- `scripts/fetch_court_guides.py` — 最高法/最高检 (栏目路径待修)
- `scripts/fetch_gov_cn.py` (TODO) — gov.cn 政策文件, 最稳
- `scripts/retrieval_router.py` — 4 级 fallback 路由器
- `_foundation/cn-fallback-source/SKILL.md` — fallback 协议