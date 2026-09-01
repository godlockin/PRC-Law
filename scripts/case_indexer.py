#!/usr/bin/env python3
"""案例库索引器 — 解析 .docx/.doc/.pdf 判决书，提取要素，写入 SQLite。

用法:
  python3 scripts/case_indexer.py <input_dir> [--db cases.db] [--search "律师函"]
  python3 scripts/case_indexer.py --incremental <new_dir> --db cases.db
  python3 scripts/case_indexer.py --search "违约" --db cases.db
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
import time
from pathlib import Path

try:
    from docx import Document
except ImportError:
    Document = None
try:
    import pdfplumber
except ImportError:
    pdfplumber = None


# === Schema ===
SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
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
    content='cases', content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE INDEX IF NOT EXISTS idx_cases_court ON cases(court);
CREATE INDEX IF NOT EXISTS idx_cases_date ON cases(judgment_date);
CREATE INDEX IF NOT EXISTS idx_cases_cause ON cases(cause_of_action);
CREATE INDEX IF NOT EXISTS idx_cases_hash ON cases(file_hash);
"""


# === 提取正则 ===
# 中国案号: (YYYY)法院代字+序列类型+编号+号
# 例: (2020)京01民初1234号 / (2024)最高法民申5678号 / (2019)沪0115民初5678号
# 法院代字: 汉字+数字混合 (京01 / 最高法 / 沪0115)
CASE_NUMBER_RE = re.compile(r'[（(]\d{4}[）)](?:[一-鿿]+\d*|\d+)[一-鿿]{1,6}[初终再申监执]\d+号')
COURT_RE = re.compile(r'(中华人民共和国)?([一-龥]+(?:省|市|区|县|自治州|地区))?([一-龥]+(?:高级|中级|基层)?人民法院)')
DATE_RE = re.compile(r'二[〇零一二三四五六七八九]{3}年[一二三四五六七八九十]+月[一二三四五六七八九十]+日')
# 引用法条: 《XXX法》第XXX条 / 第XXX条 / 民法典第577条
LAW_REF_RE = re.compile(r'《([^》]+)》第([一二三四五六七八九十百零\d]+)条')

CN_DIGITS = "零一二三四五六七八九"
CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _cn_to_int(cn: str) -> int | None:
    if cn.isdigit():
        return int(cn)
    if cn == "十":
        return 10
    if all(c in CN_DIGITS or c in CN_UNITS for c in cn):
        total, current = 0, 0
        for c in cn:
            if c in CN_DIGITS:
                current = CN_DIGITS.index(c)
            else:
                unit = CN_UNITS[c]
                if current == 0:
                    current = 1
                total += current * unit
                current = 0
        total += current
        return total
    return None


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in ('.docx', '.doc'):
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
    if '再审' in text:
        return '再审'
    if '二审' in text or '终审' in text:
        return '二审'
    if '一审' in text or '初审' in text:
        return '一审'
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


def _extract_section(text: str, start_kw: str, end_kws: list[str], max_chars: int = 500) -> str:
    """从判决书提取特定段落 (例如 '争议焦点:' 到 '本院认为' 之间)"""
    start = text.find(start_kw)
    if start < 0:
        return ''
    end = len(text)
    for ek in end_kws:
        idx = text.find(ek, start)
        if 0 < idx < end:
            end = idx
    return text[start:end].strip()[:max_chars]


def extract_elements(text: str) -> dict:
    """增强版: 除基础 5 字段外, 提取争议焦点/认定事实/法条引用/裁判结果等"""
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

    # 引用法条 (去重 + 标准化)
    cited = set()
    for m in LAW_REF_RE.finditer(text):
        law_name = m.group(1)
        article_num = m.group(2)
        # 标准化为数字
        n = _cn_to_int(article_num)
        if n is not None:
            cited.add(f"{law_name}第{n}条")
    cited_statutes = '|'.join(sorted(cited))

    # 段落提取
    dispute_focus = _extract_section(
        text, '争议焦点', ['本院认为', '本院查明', '本院认定'], max_chars=500)
    facts_found = _extract_section(
        text, '本院查明', ['本院认为', '裁判理由'], max_chars=1000)
    plaintiff_claims = _extract_section(
        text, '原告诉称', ['被告辩称', '本院查明'], max_chars=800)
    defense_arguments = _extract_section(
        text, '被告辩称', ['本院查明', '本院认为'], max_chars=800)
    judgment_result = _extract_section(
        text, '判决如下', ['如不服', '上诉于'], max_chars=500)

    return {
        'case_number': case_num,
        'court': court,
        'judgment_date': date_str,
        'procedure': _guess_procedure(text),
        'cause_of_action': _guess_cause(text),
        'parties': '',  # 复杂,留给后续 LLM 增强
        'plaintiff_claims': plaintiff_claims,
        'defense_arguments': defense_arguments,
        'dispute_focus': dispute_focus,
        'facts_found': facts_found,
        'applicable_laws': cited_statutes,  # 存引用法条列表
        'judgment_result': judgment_result,
        'cited_statutes': cited_statutes,
        'raw_text': text[:50000],
    }


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_case(conn: sqlite3.Connection, path: Path, elements: dict) -> str:
    """入库 + 跳过已存在 (按 file_hash 幂等) + FTS5 同步"""
    fhash = _file_hash(path)
    existing = conn.execute(
        "SELECT id FROM cases WHERE file_hash=?", (fhash,)
    ).fetchone()
    if existing:
        return existing[0]  # 已存在, 跳过
    case_id = fhash[:16]
    conn.execute("""
        INSERT INTO cases
        (id, file_path, file_hash, case_number, court, procedure, judgment_date,
         parties, cause_of_action, plaintiff_claims, defense_arguments,
         dispute_focus, facts_found, applicable_laws, judgment_result,
         cited_statutes, raw_text, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (case_id, str(path), fhash,
          elements['case_number'], elements['court'],
          elements['procedure'], elements['judgment_date'],
          elements['parties'], elements['cause_of_action'],
          elements['plaintiff_claims'], elements['defense_arguments'],
          elements['dispute_focus'], elements['facts_found'],
          elements['applicable_laws'], elements['judgment_result'],
          elements['cited_statutes'], elements['raw_text']))
    # 同步到 FTS5 (content 表 / rowid 模式必须手动触发)
    rowid = conn.execute("SELECT rowid FROM cases WHERE id=?", (case_id,)).fetchone()[0]
    conn.execute("""
        INSERT INTO cases_fts(rowid, case_number, court, parties, cause_of_action,
                              dispute_focus, facts_found, applicable_laws, judgment_result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (rowid, elements['case_number'], elements['court'],
          elements['parties'], elements['cause_of_action'],
          elements['dispute_focus'], elements['facts_found'],
          elements['applicable_laws'], elements['judgment_result']))
    conn.commit()
    return case_id


def index_directory(input_dir: Path, db_path: Path = Path('cases.db'),
                    max_depth: int = 3, min_size: int = 200):
    conn = init_db(db_path)
    extensions = {'.docx', '.doc', '.pdf', '.txt'}
    # 限深度防误用 (例: 用户输入 /tmp 会扫到几千杂文件)
    files = []
    for p in sorted(input_dir.rglob('*')):
        try:
            rel = p.relative_to(input_dir)
            depth = len(rel.parts)
        except ValueError:
            continue
        if depth > max_depth:
            continue
        if p.suffix.lower() not in extensions:
            continue
        if not p.is_file() or p.stat().st_size < min_size:
            continue
        files.append(p)
    print(f'发现 {len(files)} 个法律文书 in {input_dir} (max_depth={max_depth}, min_size={min_size}B)')

    if len(files) > 10000:
        print(f'⚠️  发现 {len(files)} 个文件, 数量较大。可能是目录过宽?')
        print(f'   建议加 --max-depth 1 或 --max-depth 2 限制范围')
        print(f'   Ctrl-C 取消... 5s 后继续')
        time.sleep(5)

    indexed, skipped = 0, 0
    errors_list: list[str] = []
    t0 = time.time()
    for i, fp in enumerate(files, 1):
        try:
            fhash = _file_hash(fp)
            existing = conn.execute(
                "SELECT id FROM cases WHERE file_hash=?", (fhash,)
            ).fetchone()
            if existing:
                skipped += 1
                print(f'  [{i}/{len(files)}] SKIP (已入库) {fp.name}')
                continue
            text = extract_text(fp)
            elements = extract_elements(text)
            case_id = index_case(conn, fp, elements)
            indexed += 1
            cn = elements['case_number'] or '(案号未识别)'
            pct = (i / len(files)) * 100
            elapsed = time.time() - t0
            print(f'  [{i}/{len(files)}] {pct:5.1f}% {case_id} {cn} <- {fp.name}')
        except Exception as e:
            msg = f'  SKIP {fp.name}: {e}'
            print(msg, file=sys.stderr)
            errors_list.append(msg)

    conn.close()

    if errors_list:
        err_path = db_path.parent / 'cases_errors.log'
        err_path.write_text('\n'.join(errors_list) + '\n')
        print(f'\n{len(errors_list)} errors logged to {err_path}')

    elapsed = time.time() - t0
    print(f'\n✅ 完成. 新入库 {indexed} / 跳过 {skipped} / 失败 {len(errors_list)}')
    print(f'⏱️  耗时 {elapsed:.1f}s (平均 {elapsed/max(len(files), 1):.2f}s/件)')
    print(f'📂 DB: {db_path} (大小 {db_path.stat().st_size // 1024} KB)')


def search_cases(db_path: Path, query: str, limit: int = 10) -> list[dict]:
    """检索: FTS5 (英数关键词) + LIKE (中文模糊) 双轨"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # FTS5 模式 (适合英文/数字/含空格的复杂查询)
    try:
        fts_rows = conn.execute("""
            SELECT c.id, c.case_number, c.court, c.judgment_date,
                   c.cause_of_action, c.dispute_focus, c.judgment_result,
                   c.cited_statutes, c.idx_at := c.indexed_at,
                   snippet(cases_fts, 6, '«', '»', '…', 12) AS snippet,
                   'fts' AS src
            FROM cases c JOIN cases_fts ON c.rowid = cases_fts.rowid
            WHERE cases_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
    except sqlite3.OperationalError:
        fts_rows = []
    # LIKE 模式 (中文模糊匹配 - 跨多字段)
    like_query = f"%{query}%"
    like_rows = conn.execute("""
        SELECT id, case_number, court, judgment_date, cause_of_action,
               dispute_focus, judgment_result, cited_statutes, indexed_at,
               substr(dispute_focus, 1, 60) AS snippet, 'like' AS src
        FROM cases
        WHERE case_number LIKE ? OR court LIKE ? OR cause_of_action LIKE ?
           OR dispute_focus LIKE ? OR facts_found LIKE ?
           OR applicable_laws LIKE ? OR judgment_result LIKE ?
           OR parties LIKE ?
        ORDER BY judgment_date DESC
        LIMIT ?
    """, (like_query, like_query, like_query, like_query, like_query,
          like_query, like_query, like_query, limit)).fetchall()
    # 合并去重 (FTS 优先)
    seen = set()
    merged = []
    for r in fts_rows + like_rows:
        rid = r['id']
        if rid in seen:
            continue
        seen.add(rid)
        merged.append(dict(r))
        if len(merged) >= limit:
            break
    return merged


def main():
    parser = argparse.ArgumentParser(
        description="律师私有案例库索引器 + 检索")
    sub = parser.add_subparsers(dest='cmd', required=True)

    idx = sub.add_parser('index', help='批量入库')
    idx.add_argument('input_dir', help='判决书目录')
    idx.add_argument('--db', default='cases.db', help='数据库路径 (默认 cases.db)')
    idx.add_argument('--max-depth', type=int, default=3,
                     help='目录递归深度 (防误用, 默认 3)')
    idx.add_argument('--min-size', type=int, default=200,
                     help='文件最小字节数 (防空文件, 默认 200)')

    srch = sub.add_parser('search', help='检索案例')
    srch.add_argument('query', help='关键词 (支持 FTS5 语法)')
    srch.add_argument('--db', default='cases.db')
    srch.add_argument('--limit', type=int, default=10)

    args = parser.parse_args()

    if args.cmd == 'index':
        index_directory(
            Path(args.input_dir),
            Path(args.db),
            max_depth=args.max_depth,
            min_size=args.min_size,
        )
    elif args.cmd == 'search':
        results = search_cases(Path(args.db), args.query, args.limit)
        if not results:
            print(f'未命中 "{args.query}"')
            return
        print(f'命中 {len(results)} 条:\n')
        for i, r in enumerate(results, 1):
            print(f'[{i}] {r["case_number"] or "(案号?)"} | {r["court"]} | {r["judgment_date"] or "?"}')
            print(f'    案由: {r["cause_of_action"]}')
            if r.get("snippet"):
                print(f'    摘要: {r["snippet"]}')
            if r.get("cited_statutes"):
                print(f'    法条: {r["cited_statutes"][:80]}')
            print()


if __name__ == '__main__':
    main()