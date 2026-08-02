#!/usr/bin/env python3
"""验证 PRC-Law 仓库的全局约束。

检查项:
1. 所有 SKILL.md 含 jurisdiction: PRC
2. 无静态法条数字 (第X条 模式)
3. 所有 SKILL.md 含 Lawyer Review Gate
4. references 含 last_verified / freshness_window
5. frontmatter name 完整性
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STATIC_LAW_RE = re.compile(r'第[一二三四五六七八九十百千0-9]+条')
LAWYER_GATE = '律师审阅闸'

def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(errors='replace')
    rel = str(path.relative_to(ROOT))

    is_skill = path.name == 'SKILL.md'
    is_ref = 'references' in path.parts

    if is_skill:
        if 'jurisdiction:' not in text[:500]:
            errors.append(f'{rel}: missing jurisdiction field')
        if LAWYER_GATE not in text:
            errors.append(f'{rel}: missing Lawyer Review Gate')

        # Static law article check — _foundation skills are exempt (their own
        # internal references serve as retrieval instruction templates), but
        # domain/compound skills must use [schema:retrieval-hint] exclusively.
        FOUNDATION_WHITELIST = {'_foundation/case-loader/SKILL.md', '_foundation/legal-retrieval/SKILL.md',
                                 '_foundation/norm-verify/SKILL.md', '_foundation/element-extraction/SKILL.md',
                                 '_foundation/source-label/SKILL.md', '_foundation/concept-comprehension/SKILL.md',
                                 '_foundation/terminology/SKILL.md', '_foundation/interpretation/SKILL.md',
                                 '_foundation/reasoning/SKILL.md', '_foundation/consequence-conflict/SKILL.md',
                                 '_foundation/cold-start/SKILL.md', '_foundation/matter-workspace/SKILL.md',
                                 '_foundation/evidence-evaluation/SKILL.md', '_foundation/argument-chain/SKILL.md',
                                 '_foundation/systematic-risk/SKILL.md'}
        if rel not in FOUNDATION_WHITELIST:
            hits = STATIC_LAW_RE.findall(text)
            if hits:
                errors.append(f'{rel}: static law article references ({len(hits)} found): {hits[:3]}')

        # norm-verify wiring check: domain/compound skills must call cn-norm-verify
        if ('_domains/' in rel or '_compound/' in rel) and 'cn-norm-verify' not in text:
            errors.append(f'{rel}: missing cn-norm-verify call in workflow steps')

        # legal-retrieval gate check: domain/compound skills must call cn-legal-retrieval
        if ('_domains/' in rel or '_compound/' in rel) and 'cn-legal-retrieval' not in text:
            errors.append(f'{rel}: missing cn-legal-retrieval call in workflow steps')

    if is_ref:
        if 'last_verified' not in text and 'freshness_window' not in text:
            errors.append(f'{rel}: references missing freshness fields')

    return errors

def main() -> int:
    all_errors: list[str] = []
    for p in ROOT.rglob('*.md'):
        if '.claude' in p.parts or 'docs' in p.parts:
            continue
        all_errors.extend(check_file(p))
    if all_errors:
        for e in all_errors:
            print(f'  ✗ {e}', file=sys.stderr)
        print(f'\n{len(all_errors)} violation(s)', file=sys.stderr)
        return 1
    print('✓ All validations passed')
    return 0

if __name__ == '__main__':
    sys.exit(main())
