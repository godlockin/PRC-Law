#!/usr/bin/env python3
"""
upstream_check.py — 联网时检查 plugin 上游版本

设计原则:
- **后台运行** — 通过 nohup & 启动,不阻塞调用方
- **容错** — 任何步骤失败只写 state,绝不抛异常
- **轻量** — 单次 HTTPS GET,无依赖 requests(用 urllib)
- **去重** — state 文件带时间戳,1h 内不重复检查

输出: ~/.prc-law/upstream-state.json
    {
      "local_version": "8.2.0",
      "remote_version": "8.3.0" | null,
      "drift": true | false,
      "checked_at": "2026-08-30T21:03:00+08:00",
      "source": "release" | "commit" | "offline",
      "action": "sync" | "wait" | "manual"
    }

环境变量:
  UPSTREAM_REPO — 默认 "godlockin/PRC-Law"
  PRC_LAW_SKIP_SYNC=1 — 跳过(测试/CI)
  PRC_LAW_FORCE_SYNC=1 — 忽略 1h 缓存,强制重检
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- 配置 ---
DEFAULT_REPO = "godlockin/PRC-Law"
STATE_DIR = Path.home() / ".prc-law"
STATE_FILE = STATE_DIR / "upstream-state.json"
LOG_FILE = Path("/tmp/prc-law-upstream-check.log")
CACHE_TTL = 3600  # 1 小时

PLUGIN_JSON_CANDIDATES = [
    Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json",
    Path.cwd() / ".claude-plugin" / "plugin.json",
]


def log(msg: str) -> None:
    """静默写日志,绝不向 stdout 喷(后台运行时被 pipe 也无害)"""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


def read_local_version() -> str:
    """从 .claude-plugin/plugin.json 读 version;失败回退 unknown"""
    for path in PLUGIN_JSON_CANDIDATES:
        if path.exists():
            try:
                return json.loads(path.read_text()).get("version", "unknown")
            except Exception as e:
                log(f"parse plugin.json failed at {path}: {e}")
    return "unknown"


def fetch_remote_version(repo: str) -> tuple[str, str]:
    """
    返回 (version, source)
    source ∈ {"release", "commit", "offline"}
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "prc-law-upstream-check",
    }

    # 1) 试 release
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            tag = data.get("tag_name") or data.get("name")
            if tag:
                return tag.lstrip("v"), "release"
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        log(f"releases/latest failed: {e}")

    # 2) fallback: 最新 commit SHA
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/commits?per_page=1",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            sha = data[0]["sha"][:7]
            return sha, "commit"
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, KeyError, IndexError) as e:
        log(f"commits failed: {e}")

    return "", "offline"


def should_skip_cache() -> bool:
    if os.environ.get("PRC_LAW_FORCE_SYNC") == "1":
        return True
    if not STATE_FILE.exists():
        return True
    try:
        state = json.loads(STATE_FILE.read_text())
        checked_at = datetime.fromisoformat(state["checked_at"])
        age = (datetime.now(timezone.utc) - checked_at).total_seconds()
        return age > CACHE_TTL
    except Exception:
        return True


def main() -> int:
    if os.environ.get("PRC_LAW_SKIP_SYNC") == "1":
        log("skip by env")
        return 0

    if not should_skip_cache():
        log("within cache TTL, skip")
        return 0

    repo = os.environ.get("UPSTREAM_REPO", DEFAULT_REPO)
    local = read_local_version()

    remote_ver, source = fetch_remote_version(repo)
    drift = bool(remote_ver) and remote_ver != local

    # 决策
    if source == "offline":
        action = "wait"
    elif drift:
        action = "sync"
    else:
        action = "wait"

    state = {
        "local_version": local,
        "remote_version": remote_ver or None,
        "drift": drift,
        "checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "source": source,
        "action": action,
        "repo": repo,
    }

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        # 原子写: tmp + rename
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        tmp.replace(STATE_FILE)
        log(f"state written: {state}")
    except Exception as e:
        log(f"state write failed: {e}")
        return 1

    # drift 时主动触发 sync(后台 detached,不阻塞返回)
    if action == "sync":
        sync_script = Path(__file__).resolve().parent / "upstream_sync.sh"
        if sync_script.exists():
            try:
                import subprocess
                # 关键:stdout/stderr 重定向到 /tmp,start_new_session 完全脱离父进程
                subprocess.Popen(
                    ["/bin/bash", str(sync_script)],
                    stdout=open("/tmp/prc-law-sync.log", "ab"),
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
                log("upstream_sync.sh dispatched in background")
            except Exception as e:
                log(f"dispatch sync failed: {e}")

    return 0


if __name__ == "__main__":
    # 退出码不影响调用方 — 后台进程没人看 $?
    sys.exit(main())