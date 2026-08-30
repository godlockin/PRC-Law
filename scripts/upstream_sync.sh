#!/usr/bin/env bash
# upstream_sync.sh — 真正执行 git pull 的后台脚本
#
# 设计原则:
# - **安全**: 仅 fast-forward,任何冲突/错误一律退出,不强制覆盖
# - **隔离**: 独立日志,不向父 stdout 喷任何东西
# - **幂等**: 可被多次调用,失败状态写入 ~/.prc-law/upstream-state.json
#
# 调用: 由 upstream_check.py 通过 subprocess.Popen(detached) 触发
#       或手动: bash scripts/upstream_sync.sh
#
# 环境变量:
#   UPSTREAM_REPO  — 默认 godlockin/PRC-Law
#   UPSTREAM_BRANCH — 默认 main
#   PRC_LAW_DRY_RUN=1 — 只 fetch,不 merge

set -uo pipefail   # 注意: 不用 -e,因为我们要捕获失败状态

REPO="${UPSTREAM_REPO:-godlockin/PRC-Law}"
# BRANCH 解析顺序:
#   1) UPSTREAM_BRANCH 显式覆盖(强制同步到指定分支)
#   2) 否则: 默认 main;若当前在 main 上 → fetch origin main(向后兼容)
#   3) 若当前在其他分支(如 dev/miao) → 跟随当前分支,fetch 同名远端
DEFAULT_BRANCH="main"
BRANCH="${UPSTREAM_BRANCH:-}"
if [[ -z "$BRANCH" ]]; then
    # 先定位仓库根(见下),后面会重读 CURRENT_BRANCH;此处暂定 main
    BRANCH="$DEFAULT_BRANCH"
fi

# --- 安全: 校验 REPO 格式(防 flag smuggling) ---
# 只允许 owner/repo 形式
if ! [[ "$REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
    printf 'FATAL: invalid REPO=%s\n' "$REPO" >> /tmp/prc-law-sync.log
    exit 2
fi
STATE_DIR="${HOME}/.prc-law"
STATE_FILE="${STATE_DIR}/upstream-state.json"
LOG_FILE="/tmp/prc-law-sync.log"
LOCK_DIR="${STATE_DIR}/sync.lockdir"

mkdir -p "$STATE_DIR"

# --- 日志函数 ---
log() {
    printf '[%s] %s\n' "$(date -Iseconds)" "$*" >> "$LOG_FILE"
}

# --- 防并发: mkdir 原子锁(macOS/Linux 通吃) ---
LOCK_DIR="${STATE_DIR}/sync.lockdir"
if mkdir "$LOCK_DIR" 2>/dev/null; then
    trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT
else
    log "another sync in progress, exit"
    exit 0
fi

log "==== sync start (repo=$REPO branch=$BRANCH dry_run=${PRC_LAW_DRY_RUN:-0}) ===="

# --- 定位 PRC-Law 仓库根 ---
# 优先级:
#   1) 环境变量 PRC_LAW_ROOT 显式指定
#   2) 本脚本所在目录向上找到 .claude-plugin/plugin.json
REPO_ROOT="${PRC_LAW_ROOT:-}"

if [[ -z "$REPO_ROOT" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CANDIDATE="$(cd "$SCRIPT_DIR/.." && pwd)"
    if [[ -f "$CANDIDATE/.claude-plugin/plugin.json" ]]; then
        REPO_ROOT="$CANDIDATE"
    else
        log "FATAL: cannot locate PRC-Law root (set PRC_LAW_ROOT)"
        exit 2
    fi
fi
# 安全: 强制绝对路径 + 必须存在
if ! [[ "$REPO_ROOT" =~ ^/ ]]; then
    log "FATAL: REPO_ROOT must be absolute: $REPO_ROOT"
    exit 2
fi
if [[ ! -d "$REPO_ROOT" ]]; then
    log "FATAL: REPO_ROOT not a directory: $REPO_ROOT"
    exit 2
fi

log "REPO_ROOT=$REPO_ROOT"

# --- 守卫: 不是 git 仓库 → 退出 ---
if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    log "FATAL: $REPO_ROOT is not a git repo"
    exit 2
fi

# --- 守卫 + 分支解析 ---
CURRENT_BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
# 若用户没显式 UPSTREAM_BRANCH,跟随当前分支(常见于 dev/feature 工作流)
if [[ -z "${UPSTREAM_BRANCH:-}" ]]; then
    BRANCH="$CURRENT_BRANCH"
    log "BRANCH auto-resolved to current branch '$BRANCH'"
fi
# --- 安全: BRANCH 白名单(防 argv flag smuggling, 如 -upload-pack=evil) ---
# 只允许 [A-Za-z0-9._/-], 长度 ≤ 100
if ! [[ "$BRANCH" =~ ^[A-Za-z0-9._/-]{1,100}$ ]]; then
    log "FATAL: invalid BRANCH='$BRANCH' (must match ^[A-Za-z0-9._/-]{1,100}$)"
    exit 2
fi
# 检测远端是否存在该分支(避免 fetch 失败)
if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "origin/$BRANCH" >/dev/null 2>&1; then
    log "SKIP: origin/$BRANCH does not exist"
    python3 - <<PYEOF 2>>"$LOG_FILE"
import json, os
sf = "${HOME}/.prc-law/upstream-state.json"
s = json.loads(open(sf).read()) if os.path.exists(sf) else {}
s["action"] = "manual"
s["reason"] = f"no upstream branch origin/{os.environ.get('BRANCH','?')}"
s["checked_at"] = "$(date -Iseconds)"
open(sf, "w").write(json.dumps(s, ensure_ascii=False, indent=2))
PYEOF
    exit 0
fi

# --- 检查 working tree 干净 ---
if ! git -C "$REPO_ROOT" diff --quiet HEAD 2>/dev/null; then
    log "SKIP: working tree dirty"
    python3 - <<PYEOF 2>>"$LOG_FILE"
import json
sf = "${HOME}/.prc-law/upstream-state.json"
import os
s = json.loads(open(sf).read()) if os.path.exists(sf) else {}
s["action"] = "manual"
s["reason"] = "dirty tree"
open(sf, "w").write(json.dumps(s, ensure_ascii=False, indent=2))
PYEOF
    exit 0
fi

# --- 取远端 ---
log "fetch origin $BRANCH"
if ! git -C "$REPO_ROOT" fetch --end-of-options origin "$BRANCH" >> "$LOG_FILE" 2>&1; then
    log "FATAL: git fetch failed"
    exit 3
fi

# --- 计算漂移 ---
LOCAL_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
REMOTE_SHA="$(git -C "$REPO_ROOT" rev-parse "origin/$BRANCH")"

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
    log "already up to date"
    exit 0
fi

# --- dry run 模式 ---
if [[ "${PRC_LAW_DRY_RUN:-0}" == "1" ]]; then
    log "DRY RUN: would pull $LOCAL_SHA -> $REMOTE_SHA"
    exit 0
fi

# --- 执行 fast-forward pull ---
log "pull --ff-only origin $BRANCH ($LOCAL_SHA -> $REMOTE_SHA)"
if git -C "$REPO_ROOT" pull --ff-only --end-of-options origin "$BRANCH" >> "$LOG_FILE" 2>&1; then
    NEW_VERSION="$(jq -r .version "$REPO_ROOT/.claude-plugin/plugin.json" 2>/dev/null || echo unknown)"
    log "OK: synced to $NEW_VERSION ($REMOTE_SHA)"
    # 更新 state
    python3 - <<PYEOF 2>>"$LOG_FILE"
import json
sf = "${HOME}/.prc-law/upstream-state.json"
import os
s = json.loads(open(sf).read()) if os.path.exists(sf) else {}
s["action"] = "synced"
s["synced_at"] = "$(date -Iseconds)"
s["synced_to"] = "$NEW_VERSION"
s["remote_version"] = "$NEW_VERSION"
s["drift"] = False
open(sf, "w").write(json.dumps(s, ensure_ascii=False, indent=2))
PYEOF
    exit 0
else
    log "FATAL: git pull --ff-only failed (non-fast-forward or conflict)"
    python3 - <<PYEOF 2>>"$LOG_FILE"
import json
sf = "${HOME}/.prc-law/upstream-state.json"
import os
s = json.loads(open(sf).read()) if os.path.exists(sf) else {}
s["action"] = "manual"
s["reason"] = "non-fast-forward"
open(sf, "w").write(json.dumps(s, ensure_ascii=False, indent=2))
PYEOF
    exit 4
fi