#!/usr/bin/env python3
"""PRC-Law 覆盖度自动对比 — 对比 spec 矩阵 vs 实际文件。

输出: 差异报告（虚报/遗漏/多余）。
CI: 失败时 exit 1。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- Spec 矩阵: 设计规格书声称的覆盖（v2 complete-cover-matrix） ----
# 格式: 领域 -> {skill_name: (实际路径_若存在, 当前状态)}

SPEC_COVERAGE = {
    # _foundation: 声称 10+3(P0新增) = 13，实际 15
    "_foundation": {
        "case-loader": "_foundation/case-loader/SKILL.md",
        "legal-retrieval": "_foundation/legal-retrieval/SKILL.md",
        "norm-verify": "_foundation/norm-verify/SKILL.md",
        "element-extraction": "_foundation/element-extraction/SKILL.md",
        "source-label": "_foundation/source-label/SKILL.md",
        "concept-comprehension": "_foundation/concept-comprehension/SKILL.md",
        "terminology": "_foundation/terminology/SKILL.md",
        "interpretation": "_foundation/interpretation/SKILL.md",
        "reasoning": "_foundation/reasoning/SKILL.md",
        "consequence-conflict": "_foundation/consequence-conflict/SKILL.md",
        "cold-start": "_foundation/cold-start/SKILL.md",
        "matter-workspace": "_foundation/matter-workspace/SKILL.md",
        "evidence-evaluation": "_foundation/evidence-evaluation/SKILL.md",  # P0
        "argument-chain": "_foundation/argument-chain/SKILL.md",            # P0
        "systematic-risk": "_foundation/systematic-risk/SKILL.md",          # P0
    },
    # 10 domains: spec claims full coverage (从 old CFZ 移植)
    # 审计反指: 声称"12/20"等但实际少; 以下写死完整期望清单
    "commercial": {
        "nda-review": "_domains/commercial/skills/nda-review/SKILL.md",
        "vendor-agreement-review": "_domains/commercial/skills/vendor-agreement-review/SKILL.md",
        "saas-msa-review": "_domains/commercial/skills/saas-msa-review/SKILL.md",
        "review": "_domains/commercial/skills/review/SKILL.md",
        "review-proposals": "_domains/commercial/skills/review-proposals/SKILL.md",
        "amendment-history": "_domains/commercial/skills/amendment-history/SKILL.md",
        "escalation-flagger": "_domains/commercial/skills/escalation-flagger/SKILL.md",
        "renewal-tracker": "_domains/commercial/skills/renewal-tracker/SKILL.md",
        "stakeholder-summary": "_domains/commercial/skills/stakeholder-summary/SKILL.md",
    },
    "corporate": {
        "board-minutes": "_domains/corporate/skills/board-minutes/SKILL.md",
        "closing-checklist": "_domains/corporate/skills/closing-checklist/SKILL.md",
        "deal-team-summary": "_domains/corporate/skills/deal-team-summary/SKILL.md",
        "diligence-issue-extraction": "_domains/corporate/skills/diligence-issue-extraction/SKILL.md",
        "entity-compliance": "_domains/corporate/skills/entity-compliance/SKILL.md",
        "integration-management": "_domains/corporate/skills/integration-management/SKILL.md",
        "material-contract-schedule": "_domains/corporate/skills/material-contract-schedule/SKILL.md",
        "tabular-review": "_domains/corporate/skills/tabular-review/SKILL.md",
        "written-consent": "_domains/corporate/skills/written-consent/SKILL.md",
        "ai-tool-handoff": "_domains/corporate/skills/ai-tool-handoff/SKILL.md",
    },
    "labor": {
        "termination-review": "_domains/labor/skills/termination-review/SKILL.md",
        "hiring-review": "_domains/labor/skills/hiring-review/SKILL.md",
        "worker-classification": "_domains/labor/skills/worker-classification/SKILL.md",
        "internal-investigation": "_domains/labor/skills/internal-investigation/SKILL.md",
        "handbook-updates": "_domains/labor/skills/handbook-updates/SKILL.md",
        "policy-drafting": "_domains/labor/skills/policy-drafting/SKILL.md",
        "wage-hour-qa": "_domains/labor/skills/wage-hour-qa/SKILL.md",
        "expansion-kickoff": "_domains/labor/skills/expansion-kickoff/SKILL.md",
        "leave-tracker": "_domains/labor/skills/leave-tracker/SKILL.md",
        "log-leave": "_domains/labor/skills/log-leave/SKILL.md",
        "expansion-update": "_domains/labor/skills/expansion-update/SKILL.md",
        "international-expansion": "_domains/labor/skills/international-expansion/SKILL.md",
    },
    "privacy": {
        "pia-generation": "_domains/privacy/skills/pia-generation/SKILL.md",
        "dpa-review": "_domains/privacy/skills/dpa-review/SKILL.md",
        "dsar-response": "_domains/privacy/skills/dsar-response/SKILL.md",
        "use-case-triage": "_domains/privacy/skills/use-case-triage/SKILL.md",
        "policy-monitor": "_domains/privacy/skills/policy-monitor/SKILL.md",
        "reg-gap-analysis": "_domains/privacy/skills/reg-gap-analysis/SKILL.md",
        "policy-starter": "_domains/privacy/skills/policy-starter/SKILL.md",
    },
    "product": {
        "launch-review": "_domains/product/skills/launch-review/SKILL.md",
        "marketing-claims-review": "_domains/product/skills/marketing-claims-review/SKILL.md",
        "is-this-a-problem": "_domains/product/skills/is-this-a-problem/SKILL.md",
        "feature-risk-assessment": "_domains/product/skills/feature-risk-assessment/SKILL.md",
    },
    "ip": {
        "clearance": "_domains/ip/skills/clearance/SKILL.md",
        "fto-triage": "_domains/ip/skills/fto-triage/SKILL.md",
        "infringement-triage": "_domains/ip/skills/infringement-triage/SKILL.md",
        "cease-desist": "_domains/ip/skills/cease-desist/SKILL.md",
        "takedown": "_domains/ip/skills/takedown/SKILL.md",
        "oss-review": "_domains/ip/skills/oss-review/SKILL.md",
        "ip-clause-review": "_domains/ip/skills/ip-clause-review/SKILL.md",
        "portfolio": "_domains/ip/skills/portfolio/SKILL.md",
    },
    "litigation": {
        "matter-intake": "_domains/litigation/skills/matter-intake/SKILL.md",
        "matter-briefing": "_domains/litigation/skills/matter-briefing/SKILL.md",
        "matter-update": "_domains/litigation/skills/matter-update/SKILL.md",
        "matter-close": "_domains/litigation/skills/matter-close/SKILL.md",
        "portfolio-status": "_domains/litigation/skills/portfolio-status/SKILL.md",
        "demand-draft": "_domains/litigation/skills/demand-draft/SKILL.md",
        "demand-intake": "_domains/litigation/skills/demand-intake/SKILL.md",
        "demand-received": "_domains/litigation/skills/demand-received/SKILL.md",
    },
    "regulatory": {
        "reg-feed-watcher": "_domains/regulatory/skills/reg-feed-watcher/SKILL.md",
        "policy-diff": "_domains/regulatory/skills/policy-diff/SKILL.md",
        "policy-redraft": "_domains/regulatory/skills/policy-redraft/SKILL.md",
        "gaps": "_domains/regulatory/skills/gaps/SKILL.md",
        "comments": "_domains/regulatory/skills/comments/SKILL.md",
    },
    "ai-governance": {
        "aia-generation": "_domains/ai-governance/skills/aia-generation/SKILL.md",
        "vendor-ai-review": "_domains/ai-governance/skills/vendor-ai-review/SKILL.md",
        "ai-inventory": "_domains/ai-governance/skills/ai-inventory/SKILL.md",
        "policy-monitor": "_domains/ai-governance/skills/policy-monitor/SKILL.md",
        "policy-starter": "_domains/ai-governance/skills/policy-starter/SKILL.md",
    },
    "legal-edu": {
        "bar-prep-questions": "_domains/legal-edu/skills/bar-prep-questions/SKILL.md",
        "case-brief": "_domains/legal-edu/skills/case-brief/SKILL.md",
        "irac-practice": "_domains/legal-edu/skills/irac-practice/SKILL.md",
        "outline-builder": "_domains/legal-edu/skills/outline-builder/SKILL.md",
        "socratic-drill": "_domains/legal-edu/skills/socratic-drill/SKILL.md",
    },
    "_compound": {
        "contract-full-review": "_compound/contract-full-review/SKILL.md",
        "due-diligence-grid": "_compound/due-diligence-grid/SKILL.md",
        "judgment-draft": "_compound/judgment-draft/SKILL.md",
        "legal-opinion": "_compound/legal-opinion/SKILL.md",
        "claim-chart": "_compound/claim-chart/SKILL.md",
        "lifecycle-planning": "_compound/lifecycle-planning/SKILL.md",
    },
}


def main() -> int:
    diffs: list[str] = []

    for domain, expected in SPEC_COVERAGE.items():
        base = ROOT / domain.replace('_compound', '_compound').replace('_foundation', '_foundation')
        if domain == '_foundation':
            base = ROOT / '_foundation'
        elif domain == '_compound':
            base = ROOT / '_compound'
        else:
            base = ROOT / '_domains' / domain

        for skill_name, rel_path in expected.items():
            full = ROOT / rel_path
            if not full.exists():
                diffs.append(f'MISSING: {rel_path} (spec claims exists)')

        # Also check for extra skills not in spec
        if domain in ('_foundation',):
            continue  # skip _foundation — it's design to have extra
        skills_dir = base / 'skills' if domain not in ('_foundation','_compound') else None
        if skills_dir and skills_dir.is_dir():
            for p in sorted(skills_dir.glob('*/SKILL.md')):
                name = p.parent.name
                if name not in expected:
                    diffs.append(f'EXTRA: {p.relative_to(ROOT)} (not in spec coverage matrix)')
        elif domain == '_compound':
            for p in sorted(base.glob('*/SKILL.md')):
                name = p.parent.name
                if name not in expected:
                    diffs.append(f'EXTRA: {p.relative_to(ROOT)} (not in spec coverage matrix)')

    if diffs:
        for d in sorted(diffs):
            print(f'  ✗ {d}', file=sys.stderr)
        print(f'\n{diffs.count("MISSING")} missing, {diffs.count("EXTRA")} extra', file=sys.stderr)
        return 1

    total = sum(len(v) for v in SPEC_COVERAGE.values())
    print(f'✓ All {total} skills in spec matrix verified — 0 missing, 0 extra')
    return 0


if __name__ == '__main__':
    sys.exit(main())
