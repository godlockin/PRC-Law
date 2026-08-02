#!/usr/bin/env bash
# PRC-Law CI gate — run before commit
set -euo pipefail

echo "=== PRC-Law CI ==="

echo ""
echo "1. Global constraint validation..."
python3 scripts/validate_skills.py || exit 1

echo ""
echo "2. Retrieval gate check (no static law article references)..."
FOUND=$(grep -rn '第[一二三四五六七八九十百千0-9]\+条' --include='SKILL.md' _domains/ _compound/ 2>/dev/null || true)
if [ -z "$FOUND" ]; then
    echo "   PASS: no static law article references in domain/compound skills"
else
    echo "   FAIL: static law references found:"
    echo "$FOUND"
    exit 1
fi

echo ""
echo "3. Lawyer Review Gate completeness..."
MISSING=""
for f in $(find _domains/ _compound/ -name 'SKILL.md' 2>/dev/null); do
    if ! grep -q '律师审阅闸' "$f"; then
        MISSING="$MISSING $f"
    fi
done
if [ -z "$MISSING" ]; then
    echo "   PASS: all domain/compound skills have Lawyer Review Gate"
else
    echo "   FAIL: missing Lawyer Review Gate in:$MISSING"
    exit 1
fi

echo ""
echo "4. Jurisdiction frontmatter check..."
MISSING_J=""
for f in $(find . -name 'SKILL.md' -not -path './docs/*' -not -path './.claude/*' 2>/dev/null); do
    if ! head -10 "$f" | grep -qE 'jurisdiction: (PRC|multi)'; then
        MISSING_J="$MISSING_J $f"
    fi
done
if [ -z "$MISSING_J" ]; then
    echo "   PASS: all skills have jurisdiction flag (PRC or multi)"
else
    echo "   FAIL: missing jurisdiction in:$MISSING_J"
    exit 1
fi

echo ""
echo "=== ALL CI CHECKS PASSED ==="
