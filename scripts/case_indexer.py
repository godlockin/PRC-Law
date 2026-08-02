#!/usr/bin/env python3
"""案例库索引器 — 解析 .docx/.doc/.pdf 判决书，提取要素，写入 SQLite。

用法:
  python3 scripts/case_indexer.py <input_dir> [--db cases.db]
  python3 scripts/case_indexer.py --incremental <new_dir> --db cases.db
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    from docx import Document
except ImportError:
    Document = None
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    case_number TEXT,
    court TEXT,
    procedure TEXT,
    judgment_date TEXT,
    parties TEXT,
    cause_of_action TEXT,
    plaintiff_claims TEXT,
    defense_arguments TEXT,
    dispute_focus TEXT,
    facts_found TEXT,
    applicable_laws TEXT,
    judgment_result TEXT,
    cited_statutes TEXT,
    raw_text TEXT,
    indexed_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
    case_number, court, parties, cause_of_action,
    dispute_focus, facts_found, applicable_laws, judgment_result,
    content='cases', content_rowid='rowid'
);

CREATE INDEX IF NOT EXISTS idx_cases_court ON cases(court);
CREATE INDEX IF NOT EXISTS idx_cases_date ON cases(judgment_date);
CREATE INDEX IF NOT EXISTS idx_cases_cause ON cases(cause_of_action);
"""

CASE_NUMBER_RE = re.compile(r'[（(]\d{4}[）)][一-龥]{1,4}[初终再申监]{1,2}字第?\d+号')
COURT_RE = re.compile(r'(中华人民共和国)?([一-龥]+(?:省|市|区|县|自治州|地区))?([一-龥]+(?:高级|中级|基层)?人民法院)')
DATE_RE = re.compile(r'二[〇零一二三四五六七八九]{3}年[一二三四五六七八九十]+月[一二三四五六七八九十]+日')

def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == '.docx':
        if Document is None:
            raise ImportError('python-docx not installed. Run: pip install python-docx')
        doc = Document(str(path))
        return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
    elif ext == '.pdf':
        if pdfplumber is None:
            raise ImportError('pdfplumber not installed. Run: pip install pdfplumber')
        parts: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return '\n'.join(parts)
    else:
        return path.read_text(errors='replace')

def _guess_procedure(text: str) -> str:
    if '一审' in text or '初' in text[:200]:
        return '一审'
    if '二审' in text or '终' in text[:200]:
        return '二审'
    if '再审' in text:
        return '再审'
    return '未识别'

def _guess_cause(text: str) -> str:
    keywords = {
        '合同纠纷': ['合同', '违约', '履行', '解除合同', '协议'],
        '劳动争议': ['劳动', '解除劳动', '经济补偿', '工伤', '工资'],
        '侵权纠纷': ['侵权', '损害赔偿', '人身损害', '交通事故'],
        '公司纠纷': ['股权', '股东', '公司决议', '清算'],
        '知识产权': ['商标', '专利', '著作权', '侵权'],
        '行政纠纷': ['行政处罚', '行政复议', '行政强制'],
    }
    for cause, kws in keywords.items():
        if any(kw in text[:2000] for kw in kws):
            return cause
    return '其他'

def extract_elements(text: str) -> dict:
    case_num = ''
    m = CASE_NUMBER_RE.search(text)
    if m:
        case_num = m.group(0)

    court = ''
    m = COURT_RE.search(text)
    if m:
        court = m.group(0)

    date_str = ''
    m = DATE_RE.search(text[:500])
    if m:
        date_str = m.group(0)

    return {
        'case_number': case_num,
        'court': court,
        'judgment_date': date_str,
        'procedure': _guess_procedure(text),
        'cause_of_action': _guess_cause(text),
        'parties': '',
        'plaintiff_claims': '',
        'defense_arguments': '',
        'dispute_focus': '',
        'facts_found': '',
        'applicable_laws': '',
        'judgment_result': '',
        'cited_statutes': '',
        'raw_text': text[:50000],
    }

def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def index_case(conn: sqlite3.Connection, path: Path, elements: dict) -> str:
    case_id = hashlib.sha256(path.read_bytes()[:4096]).hexdigest()[:16]
    conn.execute("""
        INSERT OR REPLACE INTO cases
        (id, file_path, case_number, court, procedure, judgment_date,
         cause_of_action, raw_text, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (case_id, str(path), elements['case_number'], elements['court'],
          elements['procedure'], elements['judgment_date'],
          elements['cause_of_action'], elements['raw_text']))
    conn.commit()
    return case_id

def index_directory(input_dir: Path, db_path: Path = Path('cases.db')):
    conn = init_db(db_path)
    extensions = {'.docx', '.doc', '.pdf', '.txt'}
    files = [p for p in sorted(input_dir.rglob('*')) if p.suffix.lower() in extensions]
    print(f'Found {len(files)} legal documents in {input_dir}')

    indexed = 0
    errors_list: list[str] = []
    for fp in files:
        try:
            text = extract_text(fp)
            elements = extract_elements(text)
            case_id = index_case(conn, fp, elements)
            indexed += 1
            cn = elements['case_number'] or '(case number not recognized)'
            print(f'  [{indexed}/{len(files)}] {case_id} {cn} <- {fp.name}')
        except Exception as e:
            msg = f'  SKIP {fp.name}: {e}'
            print(msg, file=sys.stderr)
            errors_list.append(msg)

    conn.close()

    # Write error log
    if errors_list:
        err_path = Path('cases_errors.log')
        err_path.write_text('\n'.join(errors_list) + '\n')
        print(f'\n{len(errors_list)} errors logged to {err_path}')

    print(f'\nDone. {indexed} cases indexed -> {db_path}')
    print(f'Retrieve with: sqlite3 {db_path} "SELECT case_number, court FROM cases;"')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    input_dir = Path(sys.argv[1])
    db_path = Path('cases.db')
    for i, arg in enumerate(sys.argv[2:], start=2):
        if arg == '--db' and i + 1 < len(sys.argv):
            db_path = Path(sys.argv[i + 1])
    index_directory(input_dir, db_path)
