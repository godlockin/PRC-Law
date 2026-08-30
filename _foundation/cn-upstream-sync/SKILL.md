---
name: cn-upstream-sync
description: 自检 PRC-Law plugin 上游版本。SessionStart hook 后台触发，零延迟、无打扰。当 ~/.prc-law/upstream-state.json 显示 drift=true 时，渲染更新提示横幅；用户主动询问时给出详细差距。仅在用户明确说"检查更新/同步/upgrade plugin"时也可手动触发 cn-upstream-sync。
---

# cn-upstream-sync — PRC-Law plugin 上游自同步

## 角色

读 `~/.prc-law/upstream-state.json`，决定：
- 是否需要提示用户有新版本
- 是否已自动同步完成
- 是否需要用户手动介入

**绝不**主动触发 `git pull`（仅 SessionStart hook 后台可能已 pull 完）；本 skill 是**只读**的展示层。

## 状态文件 schema

`~/.prc-law/upstream-state.json`:

```json
{
  "local_version": "8.2.0",
  "remote_version": "8.3.0",
  "drift": true,
  "checked_at": "2026-08-30T21:03:00+08:00",
  "source": "release" | "commit" | "offline",
  "action": "sync" | "wait" | "manual" | "synced",
  "reason": "branch=dev | dirty tree | non-fast-forward" // 仅 manual 时存在
}
```

## 行为表

| 条件 | 动作 |
|------|------|
| 文件不存在 | 静默（hook 未跑过，**不**主动提示，避免每次启动刷屏） |
| `source == "offline"` | 静默（无网，不打扰） |
| `drift == false` | 静默 |
| `drift == true && action == "synced"` | 提示"已自动同步到 v{remote_version}" |
| `drift == true && action == "sync"` | 提示"后台正在拉取，下次启动生效" |
| `drift == true && action == "manual"` | **强调**提示，列出 reason |
| `checked_at` > 7 天 | 静默重检一次 |

## 提示模板（仅在需要展示时输出）

```
🔔 PRC-Law plugin 更新可用
   本地: v{local_version}
   上游: v{remote_version}  (来源: {source})
   检测时间: {checked_at}
   自动同步: {action}
   原因: {reason 或 "无"}
   手动同步: cd {REPO_ROOT} && git pull --ff-only origin main
```

> ⚠️ **律师审阅闸**: 更新内容未经律所审阅前不得用于对外法律意见。

## 不做的事

- ❌ 不自动调 git（hook 已后台做过）
- ❌ 不修改 plugin.json 版本（GH workflow bump-on-push 负责）
- ❌ 不在前台 sleep/wait 后台进程
- ❌ 不在每次回答中重复提示（同 session 只一次，去重 by `checked_at`）

## 关联

- 调度入口: `hooks/hooks.json` SessionStart → `scripts/upstream_check.py`
- 实际同步: `scripts/upstream_sync.sh`
- 远端扫描: `.github/workflows/self-sync.yml`