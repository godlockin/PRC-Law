#!/usr/bin/env bash
# sync_check.sh — 定期校对 references/laws/*.md 与 flk.npc.gov.cn 是否一致
#
# 设计:
# - 每周一/周三/周五 cron 触发(或手动)
# - 对比 .manifest.json 中每部法律的 sha256_16 与最新 fetch 的 hash
# - 不一致 → 单条强制 fetch 更新
# - 完全一致 → 跳过
# - 网络失败 → 写 alert, 不抛
#
# 用法:
#   bash scripts/sync_check.sh                # 校对全部
#   bash scripts/sync_check.sh --law 民法典   # 单部
#   bash scripts/sync_check.sh --force         # 强制重拉所有(忽略 hash)
#   bash scripts/sync_check.sh --dry-run       # 只显示计划
#
# cron 建议(添加到 crontab -e):
#   0 2 * * 1,3,5 bash /path/to/PRC-Law/scripts/sync_check.sh >> /tmp/prc-law-sync.log 2>&1

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAW_DIR="${ROOT}/references/laws"
MANIFEST="${LAW_DIR}/.manifest.json"
FETCH_SCRIPT="${ROOT}/scripts/fetch_flk_npc.py"
LOG="/tmp/prc-law-sync-check.log"
ALERT_FILE="${HOME}/.prc-law/sync-alert.json"

mkdir -p "${HOME}/.prc-law"

log() {
    printf '[%s] %s\n' "$(date -Iseconds)" "$*" >> "$LOG"
}

# --- 参数解析 ---
FORCE=0
DRY_RUN=0
SINGLE_LAW=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --law) SINGLE_LAW="$2"; shift 2 ;;
        *) log "unknown arg: $1"; shift ;;
    esac
done

log "==== sync_check start (force=${FORCE} dry_run=${DRY_RUN}) ===="

if [[ ! -f "$MANIFEST" ]]; then
    log "FATAL: manifest not found, run fetch_flk_npc.py first"
    [[ "$DRY_RUN" -eq 1 ]] || echo "❌ manifest missing — run scripts/fetch_flk_npc.py first"
    exit 2
fi

# --- 用 python 解析 manifest + 做 hash 对比 ---
python3 - "$MANIFEST" "$LAW_DIR" "$FORCE" "$DRY_RUN" "$SINGLE_LAW" "$FETCH_SCRIPT" <<'PYEOF'
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

manifest_path, law_dir, force, dry_run, single_law, fetch_script = sys.argv[1:7]
force = bool(int(force))
dry_run = bool(int(dry_run))

manifest_file = Path(manifest_path)
laws_dir = Path(law_dir)

try:
    manifest = json.loads(manifest_file.read_text())
except Exception as e:
    print(f"❌ manifest parse: {e}")
    sys.exit(2)

laws = manifest.get("laws", {})
targets = [(slug, info) for slug, info in laws.items()
           if not single_law or slugify_zh(single_law) == slug or info.get("title") == single_law]

# 引入 slugify (与 fetch_flk_npc 保持一致)
def slugify_zh(name):
    MAP = {
        "民法典": "civil-code", "刑法": "criminal-law",
        "民事诉讼法": "civil-procedure-law", "刑事诉讼法": "criminal-procedure-law",
        "行政诉讼法": "administrative-litigation-law", "公司法": "company-law",
        "数据安全法": "data-security-law", "个人信息保护法": "personal-information-protection-law",
        "网络安全法": "cyber-security-law", "劳动合同法": "labor-contract-law",
        "劳动法": "labor-law", "社会保险法": "social-insurance-law",
        "行政处罚法": "administrative-penalty-law", "行政复议法": "administrative-reconsideration-law",
        "行政许可法": "administrative-licensing-law", "行政强制法": "administrative-coercion-law",
        "商标法": "trademark-law", "专利法": "patent-law", "著作权法": "copyright-law",
        "反不正当竞争法": "anti-unfair-competition-law",
        "消费者权益保护法": "consumer-protection-law", "产品质量法": "product-quality-law",
        "广告法": "advertising-law", "合同法": "contract-law", "物权法": "property-law",
    }
    return MAP.get(name, name.replace("/", "-"))

drift_list = []
error_list = []

for slug, info in targets:
    md_path = laws_dir / f"{slug}.md"
    if not md_path.exists():
        drift_list.append((slug, info["title"], "file missing"))
        continue
    if force:
        drift_list.append((slug, info["title"], "force flag"))
        continue
    # 算 hash
    try:
        content = md_path.read_text(encoding="utf-8")
        new_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        old_hash = info.get("sha256_16", "")
        if new_hash != old_hash:
            drift_list.append((slug, info["title"], f"hash drift {old_hash}→{new_hash}"))
    except Exception as e:
        error_list.append((slug, info["title"], str(e)))

print(f"📊 sync_check: {len(targets)} checked, {len(drift_list)} drift, {len(error_list)} errors")
if drift_list:
    print("\n🔔 Drift detected:")
    for slug, title, reason in drift_list:
        print(f"   - {title} ({slug}): {reason}")

if error_list:
    print("\n⚠ Errors:")
    for slug, title, err in error_list:
        print(f"   - {title} ({slug}): {err}")

# 写 alert
if (drift_list or error_list) and not dry_run:
    alert = {
        "ts": datetime.now().isoformat(),
        "drift_count": len(drift_list),
        "error_count": len(error_list),
        "drifts": [{"law": t, "slug": s, "reason": r} for s, t, r in drift_list],
        "errors": [{"law": t, "slug": s, "reason": r} for s, t, r in error_list],
    }
    alert_path = Path.home() / ".prc-law" / "sync-alert.json"
    alert_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = alert_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(alert, ensure_ascii=False, indent=2))
    tmp.replace(alert_path)
    print(f"\n📝 alert written → {alert_path}")

# dry run 不触发 fetch
if dry_run:
    sys.exit(0)

# 触发 fetch: 每部 drift 单条跑 fetch_flk_npc.py --law
for slug, title, reason in drift_list:
    print(f"\n📥 refetching {title}...")
    try:
        r = subprocess.run(
            ["python3", fetch_script, "--law", title, "--force"],
            cwd=Path(fetch_script).parent.parent,
            timeout=120,
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            print(f"   ✓ {title} refreshed")
        else:
            print(f"   ⚠ {title} failed: {r.stderr or r.stdout}")
            error_list.append((slug, title, "fetch failed"))
    except Exception as e:
        print(f"   ⚠ {title} error: {e}")
        error_list.append((slug, title, str(e)))

print(f"\n📊 final: {len(targets)} checked, {len(drift_list)} refetched, {len(error_list)} errors")
PYEOF

log "==== sync_check done ===="
exit 0