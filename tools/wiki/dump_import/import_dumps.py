#!/usr/bin/env python3
"""Offline, resumable Wikimedia EN SQL-dump indexer for the private mediatheque-references instance.

No network, no calls into the shared mediatheque engine, and no writes to its core DB.
Bulk index lives on D:; every SQL stage is resumable at committed INSERT-statement boundaries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
import zipfile

DEFAULT_INSTANCE = Path(r'C:\mycode\EncyKlopedia\mediatheque-references')
DEFAULT_DUMPS = Path(r'D:\EncyKlopedia\10_sources\wikipedia\enwiki\2026-10')
DEFAULT_INDEX = Path(r'D:\EncyKlopedia\80_search_indexes\mediatheque-references\wikipedia_en.sqlite')
ORDER = ('page', 'page_props', 'linktarget', 'externallinks', 'pagelinks', 'categorylinks')
FILE_NAMES = {name: f'enwiki-latest-{name}.sql.gz' for name in ORDER}
XML_NAME = 'enwiki-latest-pages-articles-multistream.xml.bz2'
TOOL_VERSION = '1.0.1'


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def print_event(kind: str, **kw):
    print(json.dumps({'at': stamp(), 'event': kind, **kw}, ensure_ascii=False), flush=True)


def json_write_atomic(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    os.replace(tmp, path)


def secure_instance(instance: Path, enforce_layout: bool = True):
    if not enforce_layout:
        return {'database': 'fixture'}
    instance = instance.resolve(strict=True)
    sys.path.insert(0, str(instance / 'tools'))
    from instance_guard import check
    info = check(instance, require_db=True)
    if info['instance_id'] != 'encyklopedia-references':
        raise ValueError('Wrong instance ID; only encyklopedia-references is supported')
    if not (instance / 'tools/wiki/WikipediaReferenceInventory.py').exists():
        raise ValueError('Wikipedia References v2 overlay missing from this private instance')
    return info


def source_info(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f'Archive absente: {path}')
    s = path.stat()
    if s.st_size == 0:
        raise ValueError(f'Archive vide: {path}')
    return {'file': path.name, 'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns}


def check_space(target: Path, min_free_gib: float = 10.0) -> float:
    target.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(target).free / 1024**3
    if free < min_free_gib:
        raise RuntimeError(f'Espace libre insuffisant sur le volume de l’index: {free:.1f} GiB (minimum de sécurité {min_free_gib:.0f} GiB)')
    return free


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=120)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA temp_store=FILE')
    conn.execute('PRAGMA cache_size=-65536')
    conn.execute('PRAGMA wal_autocheckpoint=4096')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS ingest_state (
          stage TEXT PRIMARY KEY, filename TEXT NOT NULL, source_bytes INTEGER NOT NULL,
          source_mtime_ns INTEGER NOT NULL, committed_line INTEGER NOT NULL DEFAULT 0,
          rows_imported INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
          finished_at TEXT, sha256 TEXT, schema_json TEXT);
        CREATE TABLE IF NOT EXISTS wiki_pages (
          page_id INTEGER PRIMARY KEY, ns INTEGER NOT NULL, title TEXT NOT NULL,
          redirect INTEGER NOT NULL, latest_revision INTEGER, content_bytes INTEGER);
        CREATE TABLE IF NOT EXISTS wiki_qid (
          page_id INTEGER PRIMARY KEY, qid TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS wiki_linktargets (
          target_id INTEGER PRIMARY KEY, ns INTEGER NOT NULL, title TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS wiki_externallinks (
          link_id INTEGER PRIMARY KEY, source_page_id INTEGER NOT NULL,
          target_url TEXT NOT NULL, raw_domain_index TEXT);
        CREATE TABLE IF NOT EXISTS wiki_pagelinks (
          source_page_id INTEGER NOT NULL, target_id INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS wiki_categorylinks (
          source_page_id INTEGER NOT NULL, category TEXT NOT NULL, type TEXT);
    ''')
    # The first v1 importer saved zero-row checkpoints even though it ignored
    # continuation lines. Store statement state for safe checkpoints mid-INSERT.
    existing = {row[1] for row in conn.execute('PRAGMA table_info(ingest_state)')}
    if 'resume_insert' not in existing:
        conn.execute('ALTER TABLE ingest_state ADD COLUMN resume_insert INTEGER NOT NULL DEFAULT 0')
    conn.commit()
    return conn


_CREATE_RE = re.compile(rb'^CREATE TABLE `([^`]+)` \(')
_COLUMN_RE = re.compile(rb'^\s*`([^`]+)` ')
_INSERT_RE = re.compile(rb'^\s*INSERT\s+INTO\s+(?:`([^`]+)`|([A-Za-z_][A-Za-z_0-9]*))(?:\s*\(([^)]*)\))?\s+VALUES\s*', re.I)
_QID_RE = re.compile(r'^Q[1-9][0-9]*$')


def unescape_mysql(b: bytes) -> str:
    # MySQL SQL dump backslash escaping. Values are byte-oriented UTF-8.
    out = bytearray()
    escape = {48:0, 98:8, 110:10, 114:13, 116:9, 90:26}
    i = 0
    while i < len(b):
        if b[i] == 92 and i+1 < len(b):
            n = b[i+1]
            out.append(escape.get(n, n)); i += 2
        else:
            out.append(b[i]); i += 1
    return out.decode('utf-8', errors='replace')


def _sql_rows(raw: bytes, start: int):
    """Parse a mysqldump INSERT line using scanning, never evaluating SQL.

    Supports MySQL escaped single-quoted strings, backslash escapes and NULL.
    Lines can contain many tuples; yielded rows contain decoded str or None.
    """
    n = len(raw); i = start
    while i < n:
        while i < n and raw[i] in b' \t\r\n,;': i += 1
        if i >= n: return
        if raw[i] != 40:
            raise ValueError(f'Unexpected SQL tuple byte {raw[i]!r} at {i}')
        i += 1; fields = []
        while True:
            while i < n and raw[i] in b' \t\n': i += 1
            if i >= n: raise ValueError('Truncated SQL INSERT')
            if raw[i] == 39:
                i += 1; start_v = i
                # Fast path: scan to next quote, skip escaped quotes by parity.
                while True:
                    q = raw.find(b"'", i)
                    if q < 0: raise ValueError('Unterminated SQL quote')
                    bs = q - 1
                    while bs >= start_v and raw[bs] == 92: bs -= 1
                    if (q - 1 - bs) % 2 == 0: break
                    i = q + 1
                fields.append(unescape_mysql(raw[start_v:q])); i = q + 1
            else:
                j = i
                while j < n and raw[j] not in b',)\r\n': j += 1
                val = raw[i:j].strip()
                if val.upper() == b'NULL': fields.append(None)
                else:
                    try: fields.append(int(val))
                    except ValueError: fields.append(val.decode('utf8', errors='replace'))
                i = j
            if i >= n: raise ValueError('Truncated tuple')
            if raw[i] == 44: i += 1; continue
            if raw[i] == 41: i += 1; yield fields; break
            raise ValueError(f'Unexpected field separator at {i}')


def _columns_for_line(buf: bytes):
    # INSERT INTO `table` (`col`,...) VALUES (...) supported; conventional dump has bare VALUES.
    m = _INSERT_RE.match(buf)
    if not m: return None
    cols = None
    if m.group(3):
        cols = [x.decode('ascii').strip(' `') for x in m.group(3).split(b',')]
    table = m.group(1) or m.group(2)
    return table.decode('ascii'), cols, m.end()


def _pick(cols: list[str], row: list, field: str):
    try: return row[cols.index(field)]
    except ValueError as e: raise ValueError(f'Missing required column {field!r}, got {cols}') from e


def _int(v):
    return int(v) if v is not None else None


def reconstruct_external(domain: str, path: str | None) -> str:
    """MediaWiki >=1.40 domain reversed by labels: https://org.example.sub."""
    if not domain: return ''
    # documentation: 'http://org.wikipedia.en.' is the domain index for http://en.wikipedia.org
    m = re.match(r'^(https?://|//)(.*)$', domain)
    if not m: return ''
    scheme, rest = m.group(1), m.group(2).rstrip('.')
    labels = rest.split('.')
    if not all(labels): return ''
    host = '.'.join(reversed(labels))
    return (scheme if scheme != '//' else 'https://') + host + (path or '/')


def convert(stage: str, cols: list[str], row: list):
    d = dict(zip(cols, row))
    if stage == 'page':
        return (_int(d['page_id']), _int(d['page_namespace']), str(d['page_title']),
                _int(d['page_is_redirect']), _int(d.get('page_latest')), _int(d.get('page_len')))
    if stage == 'page_props':
        if d['pp_propname'] != 'wikibase_item': return None
        qid = str(d['pp_value'])
        if not _QID_RE.fullmatch(qid): return None
        return (_int(d['pp_page']), qid)
    if stage == 'linktarget':
        return (_int(d['lt_id']), _int(d['lt_namespace']), str(d['lt_title']))
    if stage == 'externallinks':
        if 'el_to_domain_index' in d:
            dom = str(d['el_to_domain_index'])
            url = reconstruct_external(dom, d.get('el_to_path'))
        elif 'el_to' in d:
            dom = ''
            url = str(d['el_to'])
        else: raise ValueError('Unsupported externallinks schema')
        if not url or not url.startswith(('https://', 'http://')): return None
        return (_int(d['el_id']), _int(d['el_from']), url, dom)
    if stage == 'pagelinks':
        if d.get('pl_target_id') is None:
            raise ValueError('This pagelinks dump lacks pl_target_id; cannot safely reconstruct with provided linktarget schema')
        return (_int(d['pl_from']), _int(d['pl_target_id']))
    if stage == 'categorylinks':
        return (_int(d['cl_from']), str(d['cl_to']), str(d.get('cl_type') or ''))
    raise ValueError('Unknown stage')


INSERT_SQL = {
    'page': 'INSERT OR REPLACE INTO wiki_pages VALUES(?,?,?,?,?,?)',
    'page_props': 'INSERT OR REPLACE INTO wiki_qid VALUES(?,?)',
    'linktarget': 'INSERT OR REPLACE INTO wiki_linktargets VALUES(?,?,?)',
    'externallinks': 'INSERT OR REPLACE INTO wiki_externallinks VALUES(?,?,?,?)',
    'pagelinks': 'INSERT INTO wiki_pagelinks VALUES(?,?)',
    'categorylinks': 'INSERT INTO wiki_categorylinks VALUES(?,?,?)',
}


class HashingReader:
    """Hash the exact compressed bytes while gzip decodes; no second 40GB read."""
    def __init__(self, raw):
        self.raw=raw
        self.hash=hashlib.sha256()

    def read(self, count=-1):
        block=self.raw.read(count)
        if block: self.hash.update(block)
        return block


def _tuple_prefix(fragment: bytes) -> tuple[bytes, bytes]:
    """Split values into whole SQL tuples and a bounded incomplete tail.

    Handles `(x,...),\n(y,...)` and even tuples split within a quoted field.
    Only completed tuples are ever passed to SQLite/checkpointed.
    """
    quoted = False
    escaped = False
    depth = 0
    last_end = 0
    for i, b in enumerate(fragment):
        if quoted:
            if escaped:
                escaped = False
            elif b == 92:  # MySQL backslash
                escaped = True
            elif b == 39:
                quoted = False
        elif b == 39:
            quoted = True
        elif b == 40:
            depth += 1
            if depth > 1:
                raise ValueError('Unexpected nested SQL tuple (unsupported format)')
        elif b == 41:
            if depth != 1:
                raise ValueError('SQL tuple has an unmatched closing parenthesis')
            depth = 0
            last_end = i + 1
    prefix = fragment[:last_end]
    tail = fragment[last_end:]
    if depth == 0 and not quoted and not tail.strip(b' \t\r\n,;'):
        tail = b''
    if len(tail) > 16 * 1024 * 1024:
        raise ValueError('A SQL tuple exceeds the safe 16 MiB size limit')
    return prefix, tail


def _values_has_semicolon(fragment: bytes) -> bool:
    # mysqldump terminates an INSERT on a semicolon, outside its quoted fields.
    return fragment.rstrip().endswith(b';')


def _checkpoint(conn, stage, line_no, imported, cols, inside_insert):
    conn.execute("""UPDATE ingest_state SET committed_line=?, rows_imported=?,
                   schema_json=?, resume_insert=? WHERE stage=?""",
                 (line_no, imported, json.dumps(cols), int(inside_insert), stage))
    conn.commit()


def import_stage(conn, stage: str, path: Path, *, commit_lines=25, progress_seconds=15,
                 stop_after_statements: int | None = None, min_free_gib=10.0):
    info = source_info(path)
    state = conn.execute("""SELECT filename,source_bytes,source_mtime_ns,
                           committed_line,rows_imported,completed,resume_insert,schema_json
                           FROM ingest_state WHERE stage=?""",(stage,)).fetchone()
    if state:
        if state[:3] != (info['file'],info['bytes'],info['mtime_ns']):
            raise ValueError(f'Archive changed after first import of {stage}; use a fresh index, do not mix dumps')
        if state[5]:
            print_event('already_complete',stage=stage,rows=state[4]); return
        checkpoint, imported = state[3], state[4]
        continuation = bool(state[6])
        restored_cols = json.loads(state[7]) if state[7] else None
        if isinstance(restored_cols,dict):
            restored_cols = restored_cols.get('active_columns')
        if checkpoint and imported == 0:
            # v1 bug: it committed millions of ignored lines while importing no
            # rows. Rewind safely; no actual page entries were inserted.
            table = {'page':'wiki_pages','page_props':'wiki_qid',
                     'linktarget':'wiki_linktargets','externallinks':'wiki_externallinks',
                     'pagelinks':'wiki_pagelinks','categorylinks':'wiki_categorylinks'}[stage]
            if conn.execute(f'SELECT EXISTS(SELECT 1 FROM {table})').fetchone()[0]:
                raise ValueError('Zero-row checkpoint conflicts with existing data; manual review required')
            print_event('rewind_empty_v1_checkpoint',stage=stage,old_line=checkpoint)
            checkpoint=0; continuation=False; restored_cols=None
            _checkpoint(conn,stage,0,0,None,False)
    else:
        conn.execute('INSERT INTO ingest_state(stage,filename,source_bytes,source_mtime_ns) VALUES (?,?,?,?)',
                     (stage, info['file'],info['bytes'],info['mtime_ns']))
        conn.commit();checkpoint=0;imported=0;continuation=False;restored_cols=None
    print_event('stage_start',stage=stage,resume_line=checkpoint,already_imported=imported,source=path.name)
    ddl_table=None; raw_cols=[]; cols=None
    line_no=0; pending=0; batch=[]; stmts=0
    insert_active=False; active_cols=None; carry=b''
    missed=0; stmt_row_count=0; last_emit=time.monotonic(); last_commit_line=checkpoint
    try:
        with path.open('rb') as raw_file:
          hashing_reader=HashingReader(raw_file)
          with gzip.GzipFile(fileobj=hashing_reader,mode='rb') as fh:
            for line in fh:
                line_no+=1
                if ddl_table:
                    m=_COLUMN_RE.match(line)
                    if m: raw_cols.append(m.group(1).decode('ascii'))
                    elif line.startswith(b')'):
                        if ddl_table==stage: cols=raw_cols
                        ddl_table=None
                    continue
                cm=_CREATE_RE.match(line)
                if cm:
                    ddl_table=cm.group(1).decode('ascii'); raw_cols=[];continue
                if line_no<=checkpoint: continue
                if checkpoint and line_no==checkpoint+1 and continuation:
                    insert_active=True;active_cols=restored_cols or cols
                    if not active_cols: raise ValueError('Cannot resume an INSERT without saved columns')
                ins=_columns_for_line(line)
                if ins:
                    if insert_active:
                        raise ValueError(f'New INSERT began while a previous one is unfinished at line {line_no}')
                    if ins[0] != stage: continue
                    active_cols=ins[1] or cols
                    if not active_cols:
                        raise ValueError(f'Missing column definitions in {stage} before INSERT')
                    insert_active=True; fragment=line[ins[2]:]
                    missed=0
                elif insert_active:
                    fragment=line
                else:
                    if line.lstrip().startswith((b'(',b'INSERT ',b'REPLACE ',b'insert ',b'replace ')):
                        missed+=1
                        if missed>=100:
                            sample=line[:100].decode('utf8','replace').strip()
                            raise ValueError(f'Unsupported SQL data layout in {stage}, example prefix: {sample!r}')
                    continue
                # A single INSERT can have millions of tuples over many lines.
                # Stream each line and commit at safe whole-tuple boundaries.
                payload=carry+fragment
                complete,carry=_tuple_prefix(payload)
                if complete:
                    batch.clear()
                    for row in _sql_rows(complete,0):
                        stmt_row_count+=1
                        item=convert(stage,active_cols,row)
                        if item is not None: batch.append(item)
                        if len(batch)>=10000:
                            conn.executemany(INSERT_SQL[stage],batch)
                            pending+=len(batch);batch.clear()
                    if batch:
                        conn.executemany(INSERT_SQL[stage],batch)
                        pending+=len(batch);batch.clear()
                ended=_values_has_semicolon(fragment)
                if ended:
                    if not stmt_row_count:
                        raise ValueError(f'Empty SQL INSERT for {stage} at line {line_no}; unknown dump format')
                    stmt_row_count=0
                    if carry:
                        raise ValueError(f'Unfinished SQL tuple at end of INSERT in {stage} line {line_no}')
                    insert_active=False;stmts+=1
                if not carry and (line_no-last_commit_line>=5000 or (ended and stmts%commit_lines==0)):
                    imported+=pending;pending=0
                    _checkpoint(conn,stage,line_no,imported,active_cols,insert_active)
                    last_commit_line=line_no
                    if time.monotonic()-last_emit>=progress_seconds:
                        print_event('progress',stage=stage,line=line_no,rows=imported,
                                    sqlite_bytes=conn.execute('PRAGMA page_count').fetchone()[0]*conn.execute('PRAGMA page_size').fetchone()[0])
                        last_emit=time.monotonic()
                        check_space(Path(conn.execute('PRAGMA database_list').fetchone()[2]).parent,min_free_gib)
                if stop_after_statements is not None and stmts>=stop_after_statements:
                    if pending:
                        imported+=pending;pending=0
                        _checkpoint(conn,stage,line_no,imported,active_cols,insert_active)
                    print_event('stopped_for_test',stage=stage,line=line_no);return
            if insert_active or carry:
                raise ValueError(f'Dump ended during a SQL INSERT in {stage}, line {line_no}')
    except (OSError,EOFError) as e:
        conn.rollback()
        raise RuntimeError(f'Compressed dump read/CRC failed in {stage}, no partial transaction accepted: {e}') from e
    except Exception:
        conn.rollback();raise
    imported+=pending
    if imported==0:
        conn.rollback()
        raise ValueError(f'No usable rows extracted from {stage}; refusing to mark it complete')
    conn.execute("""UPDATE ingest_state SET committed_line=?,rows_imported=?,completed=1,
                    finished_at=?,schema_json=?,resume_insert=0,sha256=? WHERE stage=?""",
                 (line_no,imported,stamp(),json.dumps(active_cols or cols),hashing_reader.hash.hexdigest(),stage))
    conn.commit()
    print_event('stage_complete',stage=stage,rows=imported,lines=line_no,sha256=hashing_reader.hash.hexdigest())

def create_indexes(conn, stages=ORDER):
    # Create searchable indices separately so crashes can resume from completed data stages.
    indexes = {
        'page': ["CREATE INDEX IF NOT EXISTS idx_wiki_pages_title ON wiki_pages(ns,title)",
                 "CREATE INDEX IF NOT EXISTS idx_wiki_pages_latest ON wiki_pages(latest_revision)"],
        'page_props': ["CREATE INDEX IF NOT EXISTS idx_wiki_qid_qid ON wiki_qid(qid)"],
        'linktarget': ["CREATE INDEX IF NOT EXISTS idx_wiki_lt_title ON wiki_linktargets(ns,title)"],
        'externallinks': ["CREATE INDEX IF NOT EXISTS idx_wiki_external_from ON wiki_externallinks(source_page_id)",
                          "CREATE INDEX IF NOT EXISTS idx_wiki_external_url ON wiki_externallinks(target_url)"],
        'pagelinks': ["CREATE INDEX IF NOT EXISTS idx_wiki_pagelinks_from ON wiki_pagelinks(source_page_id)"],
        'categorylinks': ["CREATE INDEX IF NOT EXISTS idx_wiki_cat_from ON wiki_categorylinks(source_page_id)"]
    }
    for stage in stages:
        if not conn.execute('SELECT completed FROM ingest_state WHERE stage=?',(stage,)).fetchone() == (1,):
            continue
        for sql in indexes[stage]:
            print_event('creating_index', stage=stage, name=sql.split(' EXISTS ')[-1].split(' ')[0])
            conn.execute(sql); conn.commit()
            check_space(Path(conn.execute('PRAGMA database_list').fetchone()[2]).parent)


def xml_archive_register(path: Path, instance: Path, index_path: Path):
    # XML is kept compressed on D:; SQL already exposes latest revision IDs.
    # Compute content hash of actual compressed bytes once, no full XML duplication.
    info = source_info(path)
    print_event('xml_archive_hashing', file=path.name, size=info['bytes'])
    sha=hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(8*1024*1024), b''): sha.update(block)
    obj={**info,'sha256':sha.hexdigest(),'archive_path':str(path), 'index_path':str(index_path),
         'content_extracted':False,'note':'XML source retained compressed; article text not duplicated; SQL index supports page title, page_id, revision_id'}
    pointer=instance/'03_IMPORTS'/'wikipedia'/'dumps'/'archive_catalog.json'
    json_write_atomic(pointer,obj)
    print_event('xml_registered', file=path.name, sha256=obj['sha256'], pointer=str(pointer))
    return obj


def manifest_export(conn, instance: Path, dumps: Path, index: Path):
    stages={}
    for r in conn.execute('SELECT stage,filename,source_bytes,source_mtime_ns,committed_line,rows_imported,completed,finished_at,sha256 FROM ingest_state'):
        stages[r[0]]={'filename':r[1], 'bytes':r[2], 'mtime_ns':r[3], 'line':r[4], 'rows':r[5], 'complete':bool(r[6]), 'at':r[7], 'sha256':r[8]}
    report={'tool':'wikipedia_en_offline_dump_importer','version':TOOL_VERSION,'written_at':stamp(),
            'instance_root':str(instance),'dump_root':str(dumps),'bulk_sqlite':str(index),
            'stages':stages,'status':'COMPLETE_SQL_INDEX' if all(stages.get(s,{}).get('complete') for s in ORDER) else 'PARTIAL',
            'note':'Discovered links are not verified references, content claims, KS/KA or approved publication'}
    out=instance/'04_EXPORTS'/'wikipedia'/'dump_index_status.json'
    json_write_atomic(out,report)
    return report


def create_shareable_report(instance: Path, report: dict) -> Path:
    """Small support bundle only; NEVER packages the giant SQLite or copyrighted XML."""
    path=Path.home()/'Downloads'/('Wikipedia_EN_Import_'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip')
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('import_status.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        catalog=instance/'03_IMPORTS'/'wikipedia'/'dumps'/'archive_catalog.json'
        if catalog.exists():z.write(catalog,'archive_catalog.json')
        z.writestr('README.txt','Rapport d’import privé Wikimedia EN. Ne contient aucun article ni aucune base SQLite.\n')
    return path


def main(argv=None):
    ap=argparse.ArgumentParser(description='Private, offline Wikipedia English dump indexer (Wikimedia SQL + XML archive)')
    ap.add_argument('action',choices=('plan','run','status','lookup','verify-source'))
    ap.add_argument('--instance',type=Path,default=DEFAULT_INSTANCE)
    ap.add_argument('--dumps',type=Path,default=DEFAULT_DUMPS)
    ap.add_argument('--index',type=Path,default=DEFAULT_INDEX)
    ap.add_argument('--stage',choices=ORDER)
    ap.add_argument('--title',default='Right_to_education')
    ap.add_argument('--qid',default=None)
    ap.add_argument('--test-allow-custom',action='store_true',help=argparse.SUPPRESS)
    ap.add_argument('--test-stop-after',type=int,default=None,help=argparse.SUPPRESS)
    args=ap.parse_args(argv)
    instance=args.instance; dumps=args.dumps; index=args.index
    if not args.test_allow_custom:
        if (instance.resolve() != DEFAULT_INSTANCE.resolve() or dumps.resolve()!=DEFAULT_DUMPS.resolve() or index.resolve()!=DEFAULT_INDEX.resolve()):
            raise ValueError('Hardcoded production paths cannot be overridden; use supplied Windows layout')
    secure_instance(instance, enforce_layout=not args.test_allow_custom)
    paths={k:dumps/v for k,v in FILE_NAMES.items()}
    paths['xml']=dumps/XML_NAME
    if args.action in ('plan','verify-source'):
        results={}
        for k,p in paths.items():
            try: results[k]={**source_info(p),'status':'present'}
            except (FileNotFoundError,ValueError) as e: results[k]={'status':'missing','error':str(e)}
        free=shutil.disk_usage(dumps).free/1024**3 if dumps.is_dir() else 0
        print_event('preflight', sources=results, index=str(index), free_gib=round(free,2), all_present=all(x['status']=='present' for x in results.values()))
        return 0 if all(x['status']=='present' for x in results.values()) else 2
    if not index.is_file() and args.action in ('lookup','status'):
        print_event('not_started', index=str(index)); return 2
    if args.action == 'run':
        missing=[str(p) for p in paths.values() if not p.is_file()]
        if missing: raise FileNotFoundError('Missing archives: '+', '.join(missing))
        free=check_space(index.parent)
        print_event('ready', free_gib=round(free,1), disk_warning='Bulk graph indexes may occupy hundreds of GiB; space checked continuously')
    # Keep SQLite spill files off C: while sorting very large indexes.
    tmp=index.parent/'sqlite_temp'
    tmp.mkdir(parents=True,exist_ok=True)
    os.environ['TMP']=str(tmp); os.environ['TEMP']=str(tmp); os.environ['SQLITE_TMPDIR']=str(tmp)
    conn=connect(index)
    try:
        if args.action=='lookup':
            if args.qid:
                sql='''SELECT p.page_id,p.title,q.qid,p.latest_revision FROM wiki_qid q JOIN wiki_pages p ON p.page_id=q.page_id WHERE q.qid=? AND p.ns=0 LIMIT 20'''
                rows=conn.execute(sql,(args.qid,)).fetchall()
            else:
                sql='''SELECT p.page_id,p.title,q.qid,p.latest_revision FROM wiki_pages p LEFT JOIN wiki_qid q ON q.page_id=p.page_id WHERE p.ns=0 AND p.title=? LIMIT 20'''
                rows=conn.execute(sql,(args.title.replace(' ','_'),)).fetchall()
            print_event('lookup_results', rows=[dict(zip(('page_id','title','qid','revision'),r)) for r in rows]); return 0
        if args.action=='status':
            report=manifest_export(conn,instance,dumps,index)
            print_event('status', **report); return 0
        stages=(args.stage,) if args.stage else ORDER
        for stage in stages:
            import_stage(conn,stage,paths[stage],stop_after_statements=args.test_stop_after)
            if args.test_stop_after: break
            create_indexes(conn,(stage,))
        if not args.stage and not args.test_stop_after:
            catalog=instance/'03_IMPORTS'/'wikipedia'/'dumps'/'archive_catalog.json'
            old=json.loads(catalog.read_text('utf8')) if catalog.is_file() else None
            if not old or old.get('bytes')!=source_info(paths['xml'])['bytes'] or old.get('mtime_ns')!=source_info(paths['xml'])['mtime_ns']:
                xml_archive_register(paths['xml'],instance,index)
        report=manifest_export(conn,instance,dumps,index)
        if not args.stage and not args.test_stop_after:
            bundle=create_shareable_report(instance,report)
            print_event('support_bundle',zip=str(bundle))
        print_event('finish', status=report['status'], index=str(index)); return 0
    finally:
        conn.close()


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError,OSError,RuntimeError,sqlite3.Error) as e:
        print_event('error', error=str(e), error_type=type(e).__name__)
        sys.exit(2)
