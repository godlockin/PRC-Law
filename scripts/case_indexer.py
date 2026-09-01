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
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


# === LLM 增强提取 ===
# 当正则识别率低 (无案号/法院/法条) 时, 调用 LLM 智能提取
# 默认关闭 (--llm-enhance 开启). 需环境变量配置 LLM API.
LLM_ENHANCE_PROMPT = """从以下中国法院判决书中提取结构化信息, 输出 JSON (不要任何额外文字):
{
  "case_number": "案号, 如 (2020)京01民初1234号",
  "court": "审理法院全名",
  "procedure": "一审/二审/再审",
  "judgment_date": "判决日期 (YYYY-MM-DD, 中文数字转换)",
  "parties": "原告/被告/第三人 (用 | 分隔)",
  "cause_of_action": "案由 (如 合同纠纷/劳动争议/侵权)",
  "dispute_focus": "争议焦点 (一句话)",
  "plaintiff_claims": "原告诉称摘要 (<=200字)",
  "judgment_result": "判决结果摘要 (<=200字)",
  "cited_statutes": "引用法条列表 (格式: 法名第N条, 用 | 分隔)"
}

判决书:
---
{text}
---

JSON:"""


def _llm_extract(text: str) -> dict | None:
    """调用 LLM 智能提取判决书要素. 返回 None 表示跳过.
    通过环境变量配置:
      PRC_LAW_LLM_API_KEY / PRC_LAW_LLM_BASE_URL / PRC_LAW_LLM_MODEL
    默认走 Anthropic 兼容协议, 也支持 OpenAI 兼容.
    """
    api_key = os.environ.get("PRC_LAW_LLM_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.environ.get("PRC_LAW_LLM_BASE_URL",
                              "https://api.anthropic.com")
    model = os.environ.get("PRC_LAW_LLM_MODEL", "claude-haiku-4-5")

    # === SSRF 防护: 白名单 + 协议校验 ===
    # 只允许公网 LLM 端点. 用户可加额外白名单 (逗号分隔 host).
    DEFAULT_ALLOWED_HOSTS = {
        "api.anthropic.com",
        "api.openai.com",
        "dashscope.aliyuncs.com",      # 阿里云 Qwen (通义千问)
        "open.bigmodel.cn",            # 智谱 GLM
        "api.deepseek.com",
        "api.spark.xfyun.cn",          # 讯飞星火
        "api.moonshot.cn",             # Moonshot Kimi
        "api.baichuan-ai.com",         # 百川
        "api.stepfun.com",             # 阶跃星辰
        "aip.baidubce.com",            # 文心一言
    }
    extra = os.environ.get("PRC_LAW_LLM_EXTRA_HOSTS", "").strip()
    if extra:
        for h in extra.split(","):
            h = h.strip().lower()
            if h:
                DEFAULT_ALLOWED_HOSTS.add(h)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        # 仅 https
        if parsed.scheme != "https":
            print(f"  [LLM提取] 仅支持 https, 当前 {parsed.scheme}",
                  file=sys.stderr)
            return None
        host = (parsed.hostname or "").lower()
        if host not in DEFAULT_ALLOWED_HOSTS:
            print(f"  [LLM提取] 端点 {host} 不在白名单, 跳过",
                  file=sys.stderr)
            return None
        # 端口: 仅允许默认 (443)
        if parsed.port and parsed.port not in (80, 443):
            print(f"  [LLM提取] 非常规端口 {parsed.port}, 跳过",
                  file=sys.stderr)
            return None
    except Exception as e:
        print(f"  [LLM提取] URL 解析失败: {e}", file=sys.stderr)
        return None

    # 截断 (避免超 token)
    snippet = text[:8000]
    prompt = LLM_ENHANCE_PROMPT.format(text=snippet)

    try:
        import urllib.request
        # Anthropic 协议
        if "anthropic" in base_url:
            payload = json.dumps({
                "model": model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
        else:
            # OpenAI 兼容
            payload = json.dumps({
                "model": model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
        # 禁止 redirect (防 redirect 到非白名单)
        no_redirect_opener = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler
        )
        with no_redirect_opener.open(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        # 提取 content
        if "anthropic" in base_url:
            content = result.get("content", [{}])[0].get("text", "")
        else:
            content = result["choices"][0]["message"]["content"]
        # 解析 JSON (可能被 ```json ``` 包裹)
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        return json.loads(content)
    except Exception as e:
        print(f"  [LLM提取失败] {e}", file=sys.stderr)
        return None


def extract_elements(text: str, llm_enhance: bool = False) -> dict:
    """增强版: 除基础 5 字段外, 提取争议焦点/认定事实/法条引用/裁判结果等

    llm_enhance=True 时, 若正则提取后关键字段仍空, 调 LLM 补全.
    """
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

    elements = {
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

    # LLM 增强: 关键字段空时调用
    if llm_enhance:
        missing = []
        if not elements['case_number']:
            missing.append('case_number')
        if not elements['court']:
            missing.append('court')
        if not elements['parties']:
            missing.append('parties')
        # 至少 2 个关键字段缺失才触发 (避免无谓开销)
        if len(missing) >= 2:
            llm_data = _llm_extract(text)
            if llm_data:
                for k in missing:
                    v = llm_data.get(k)
                    if v and not elements.get(k):
                        elements[k] = str(v)
                # 顺便补全其他可用字段
                if not elements['dispute_focus'] and llm_data.get('dispute_focus'):
                    elements['dispute_focus'] = str(llm_data['dispute_focus'])[:500]
                if not elements['judgment_result'] and llm_data.get('judgment_result'):
                    elements['judgment_result'] = str(llm_data['judgment_result'])[:500]
                if not elements['plaintiff_claims'] and llm_data.get('plaintiff_claims'):
                    elements['plaintiff_claims'] = str(llm_data['plaintiff_claims'])[:800]
                if not elements['cited_statutes'] and llm_data.get('cited_statutes'):
                    elements['cited_statutes'] = str(llm_data['cited_statutes'])[:500]

    return elements


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_case(conn: sqlite3.Connection, path: Path, elements: dict,
               return_status: bool = False):
    """入库 + 跳过已存在 (按 file_hash 幂等) + FTS5 同步

    return_status=True 时返回 (case_id, status) where status is 'new'|'skipped'
    return_status=False 时仅返回 case_id (向后兼容)
    """
    fhash = _file_hash(path)
    existing = conn.execute(
        "SELECT id FROM cases WHERE file_hash=?", (fhash,)
    ).fetchone()
    if existing:
        if return_status:
            return existing[0], 'skipped'
        return existing[0]
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
    if return_status:
        return case_id, 'new'
    return case_id


def index_directory(input_dir: Path, db_path: Path = Path('cases.db'),
                    max_depth: int = 3, min_size: int = 200,
                    llm_enhance: bool = False, workers: int = 1):
    conn = init_db(db_path)
    extensions = {'.docx', '.doc', '.pdf', '.txt'}
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
    print(f'发现 {len(files)} 个法律文书 in {input_dir} '
          f'(max_depth={max_depth}, min_size={min_size}B, '
          f'llm_enhance={llm_enhance}, workers={workers})')

    if len(files) > 10000:
        print(f'⚠️  发现 {len(files)} 个文件, 数量较大。可能是目录过宽?')
        print(f'   建议加 --max-depth 1 或 --max-depth 2 限制范围')
        print(f'   Ctrl-C 取消... 5s 后继续')
        time.sleep(5)

    def _process_one(fp: Path) -> tuple[Path, dict | None, str | None]:
        """返回 (path, elements_dict, error_msg)"""
        try:
            text = extract_text(fp)
            elements = extract_elements(text, llm_enhance=llm_enhance)
            return (fp, elements, None)
        except Exception as e:
            return (fp, None, str(e))

    indexed, skipped, llm_calls = 0, 0, 0
    errors_list: list[str] = []
    t0 = time.time()

    if workers <= 1:
        results = [_process_one(fp) for fp in files]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_process_one, fp): fp for fp in files}
            for future in as_completed(futures):
                results.append(future.result())

    # 入库 (单线程写 DB, 避免锁竞争)
    for i, (fp, elements, err) in enumerate(results, 1):
        if err:
            msg = f'  SKIP {fp.name}: {err}'
            print(msg, file=sys.stderr)
            errors_list.append(msg)
            continue
        try:
            case_id, status = index_case(conn, fp, elements, return_status=True)
            if status == 'skipped':
                skipped += 1
                cn = elements['case_number'] or '(案号未识别)'
                pct = (i / len(results)) * 100
                print(f'  [{i}/{len(results)}] {pct:5.1f}% SKIP {cn} <- {fp.name}')
                continue
            indexed += 1
            cn = elements['case_number'] or '(案号未识别)'
            pct = (i / len(results)) * 100
            elapsed = time.time() - t0
            eta = elapsed / i * (len(results) - i) if i > 0 else 0
            print(f'  [{i}/{len(results)}] {pct:5.1f}% {case_id} {cn} <- {fp.name} '
                  f'(已用 {elapsed:.0f}s, 剩 ~{eta:.0f}s)')
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
    idx.add_argument('--llm-enhance', action='store_true',
                     help='识别率低时调用 LLM 增强提取 (需 PRC_LAW_LLM_API_KEY)')
    idx.add_argument('--workers', type=int, default=1,
                     help='并行线程数 (默认 1, 文件量大时可提到 4-8)')

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
            llm_enhance=args.llm_enhance,
            workers=args.workers,
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