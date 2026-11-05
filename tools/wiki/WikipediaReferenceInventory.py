#!/usr/bin/env python3
"""Wikipedia reference discovery owned by the mediatheque-references INSTANCE only.

Harvest -> a portable JSON manifest plus raw API captures (no DB writes).
Plan -> validate a manifest and an EXISTING local Médiathèque DB (no writes).
Import --accept -> backup DB and record *declared* source URLs + discovery edges.

No automatic public export, Wikipedia text -> claims, KS/KA, or remote URL fetching.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

INSTANCE_ROOT = Path(__file__).resolve().parents[2]
SQL_FILE = Path(__file__).resolve().parent / 'wiki_inventory.sql'
EXPECTED_INSTANCE_ID = 'encyklopedia-references'
sys.path.insert(0, str(INSTANCE_ROOT / 'tools'))
from instance_guard import check as instance_guard_check
API = 'https://en.wikipedia.org/w/api.php'
SCOPE = 'unesco-educational-policy-en'
MAX_PAGES = 40
MAX_LINKS_PER_PAGE = 8000
MAX_MANIFEST_BYTES = 24 * 1024 * 1024


def get_instance(require_db: bool = False) -> dict:
    """Strictly bind every operation to the sibling-engine private instance."""
    context = instance_guard_check(INSTANCE_ROOT, require_db=require_db)
    if context['instance_id'] != EXPECTED_INSTANCE_ID:
        raise ValueError('Instance identity mismatch: do not run against a different library')
    return context


def require_within_private_imports(path: Path):
    """Prevent referencing manifests and captures outside this private instance."""
    imports = (INSTANCE_ROOT / '03_IMPORTS').resolve()
    candidate = path.resolve()
    if not candidate.is_relative_to(imports):
        raise ValueError('Manifest must live inside the instance 03_IMPORTS directory')
    # No symbolic links or junctions along the relative path.
    for part in [path, *path.parents]:
        if part == imports:
            break
        if part.is_symlink() or bool(getattr(part, 'is_junction', lambda: False)()):
            raise ValueError('Symlink or junction forbidden for private manifest and captures')


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def canonical_url(url: str) -> str:
    """Conservative normalization. Never remove semantically meaningful query params."""
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
        raise ValueError(f'Only absolute HTTP(S) links accepted: {url[:120]}')
    if parts.username or parts.password:
        raise ValueError('URLs with credentials are not supported')
    host = parts.hostname.lower().encode('idna').decode('ascii')
    port = parts.port
    if port and not ((parts.scheme.lower() == 'https' and port == 443) or (parts.scheme.lower() == 'http' and port == 80)):
        host += f':{port}'
    path = parts.path or '/'
    return urllib.parse.urlunsplit((parts.scheme.lower(), host, path, parts.query, ''))


def wikipedia_url(title: str):
    return 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(title.replace(' ', '_'), safe='()_,:')


def safe_href(href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(('#', 'mailto:', 'javascript:', 'data:', 'tel:')):
        return None
    abs_url = urllib.parse.urljoin('https://en.wikipedia.org/', href)
    try:
        return canonical_url(abs_url)
    except (ValueError, UnicodeError):
        return None


class LinkExtractor(HTMLParser):
    """Classify links by HTML context. Citation = anchor within rendered cite_note.

    Intentionally marks uncertain non-citation URLs as 'body_external', never
    automatically as bibliographic evidence. Navigation links can be filtered.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []
        self.active_a = None

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = set((attr.get('class') or '').split())
        ctx = {'tag': tag, 'cite': '', 'navigation': bool(classes & {'navbox','vertical-navbox','metadata','toc','navigation-not-searchable'})}
        if tag == 'li' and (attr.get('id') or '').startswith('cite_note-'):
            ctx['cite'] = attr['id']
        self.stack.append(ctx)
        if tag != 'a' or self.active_a is not None:
            return
        url = safe_href(attr.get('href') or '')
        if not url:
            return
        cite = next((x['cite'] for x in reversed(self.stack) if x['cite']), '')
        navigation = any(x['navigation'] for x in self.stack)
        host = urllib.parse.urlsplit(url).hostname
        internal = host in ('en.wikipedia.org', 'en.m.wikipedia.org')
        if cite and not internal:
            kind = 'citation_external'
        elif navigation:
            kind = 'navigation'
        elif internal:
            kind = 'internal'
        else:
            kind = 'body_external'
        self.active_a = {'url':url, 'kind':kind, 'citation_marker':cite or None, 'anchor_text':'', 'href_fragment':urllib.parse.urlsplit(attr.get('href') or '').fragment or None}

    def handle_data(self, data):
        if self.active_a is not None:
            self.active_a['anchor_text'] = (self.active_a['anchor_text'] + data)[:250]

    def handle_endtag(self, tag):
        if tag == 'a' and self.active_a is not None:
            self.active_a['anchor_text'] = self.active_a['anchor_text'].strip()
            self.links.append(self.active_a)
            self.active_a = None
        # HTML from MediaWiki is generally well formed; recover from malformed nesting.
        for idx in range(len(self.stack)-1, -1, -1):
            if self.stack[idx]['tag'] == tag:
                del self.stack[idx:]
                break


def parse_api_response(raw: bytes, title_expected: str) -> dict:
    response = json.loads(raw)
    if 'error' in response:
        raise ValueError(str(response['error']))
    item = response.get('parse', {})
    if not isinstance(item.get('pageid'), int) or not isinstance(item.get('revid'), int):
        raise ValueError(f'Page or revision not available: {title_expected}')
    rendered = item.get('text', '')
    if isinstance(rendered, dict):
        rendered = rendered.get('*', '')
    if not isinstance(rendered, str):
        raise ValueError('Unexpected MediaWiki text response')
    ex = LinkExtractor()
    ex.feed(rendered)
    # Avoid unbounded import and maintain occurrence identity by stable order.
    links = ex.links
    if len(links) > MAX_LINKS_PER_PAGE:
        raise ValueError('Too many links on page; narrow the scope')
    return {
        'pageid': item['pageid'], 'revid': item['revid'],
        'title': item.get('title') or title_expected,
        'canonical_url': wikipedia_url(item.get('title') or title_expected),
        'revision_url': f'https://en.wikipedia.org/w/index.php?oldid={item["revid"]}',
        'links': links,
    }


def _api_request(title: str, user_agent: str, retries: int=3) -> bytes:
    args = urllib.parse.urlencode({'action':'parse', 'format':'json', 'formatversion':2,
        'page':title, 'prop':'text|revid', 'maxlag':5, 'redirects':1})
    request = urllib.request.Request(API+'?'+args, headers={
        'User-Agent': user_agent, 'Accept':'application/json', 'Accept-Encoding':'identity'})
    for attempt in range(retries+1):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read(8 * 1024 * 1024 + 1)
                if len(data) > 8 * 1024 * 1024:
                    raise ValueError('API result too large; narrow scope')
                return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt >= retries:
                raise
            retry = exc.headers.get('Retry-After', '')
            try:
                seconds = min(90, max(5, int(retry)))
            except ValueError:
                seconds = min(90, 5 * 2 ** attempt)
            time.sleep(seconds)
    raise RuntimeError('Unexpected retry state')


def collect(titles_file: Path, output: Path, contact: str, delay: float, max_pages: int):
    if not (contact.startswith('https://') or ('@' in contact and ' ' not in contact)):
        raise ValueError('Provide a real contact email or https URL for Wikimedia User-Agent')
    titles = [line.strip() for line in titles_file.read_text(encoding='utf-8-sig').splitlines()
              if line.strip() and not line.lstrip().startswith('#')]
    if not titles or len(titles) > max_pages or max_pages > MAX_PAGES:
        raise ValueError(f'Choose between 1 and {min(max_pages,MAX_PAGES)} article titles')
    if delay < 1.0:
        raise ValueError('Minimum 1 second between API calls')
    if output.exists():
        raise FileExistsError('Manifest already exists; use a new output filename to preserve old snapshots')
    output.parent.mkdir(parents=True, exist_ok=True)
    capturedir = output.parent / (output.stem + '-captures')
    capturedir.mkdir(exist_ok=False)
    manifest = {'format':'koa.wikipedia-reference-inventory/1.0','scope':SCOPE,
                'created_at': now(), 'license_notice':'Wikipedia page text: CC BY-SA 4.0; verify page-specific exceptions.',
                'pages':[]}
    user_agent = f'EncyKlopediaUNESCObot/0.1 ({contact}) Python-urllib'
    for i, title in enumerate(titles):
        if i:
            time.sleep(delay)
        raw = _api_request(title, user_agent)
        item = parse_api_response(raw, title)
        filename = f'page-{item["pageid"]}-rev-{item["revid"]}.api.json'
        raw_file = capturedir / filename
        if raw_file.exists():
            raise FileExistsError(str(raw_file))
        raw_file.write_bytes(raw)
        item.update({'capture_path': capturedir.name + '/' + filename,
                     'capture_sha256': digest(raw), 'retrieved_at':now()})
        manifest['pages'].append(item)
    output.write_text(dump_json(manifest), encoding='utf-8')
    return {'manifest':str(output),'pages':len(titles),
            'links':sum(len(p['links']) for p in manifest['pages'])}


def checked_manifest(path: Path):
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('Manifest missing or too large')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('format') != 'koa.wikipedia-reference-inventory/1.0' or manifest.get('scope') != SCOPE:
        raise ValueError('Unexpected inventory format or scope')
    pages = manifest.get('pages')
    if not isinstance(pages,list) or not (1 <= len(pages) <= MAX_PAGES):
        raise ValueError('Manifest must contain 1 to 40 pages')
    page_keys = set()
    for page in pages:
        for field in ('title','canonical_url','revision_url','capture_sha256','capture_path','retrieved_at'):
            if not isinstance(page.get(field),str) or not page[field]:
                raise ValueError(f'Missing page field: {field}')
        if not isinstance(page.get('pageid'),int) or not isinstance(page.get('revid'),int):
            raise ValueError('Invalid page/revision IDs')
        page_key = (page['pageid'],page['revid'])
        if page_key in page_keys:
            raise ValueError('Duplicate revision in manifest')
        page_keys.add(page_key)
        if not page['revision_url'].startswith('https://en.wikipedia.org/w/index.php?oldid='):
            raise ValueError('Invalid Wikipedia revision permalink')
        if canonical_url(page['canonical_url']) != page['canonical_url']:
            raise ValueError('Page URL not canonical')
        rel = Path(page['capture_path'])
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0].startswith('.'):
            raise ValueError('Invalid capture path')
        capture_source = path.parent / rel
        if capture_source.is_symlink() or capture_source.parent.is_symlink():
            raise ValueError('Symlinked capture forbidden')
        captured = capture_source.resolve()
        if not captured.is_relative_to(path.parent.resolve()) or not captured.is_file():
            raise ValueError('Missing capture file')
        raw = captured.read_bytes()
        if digest(raw) != page['capture_sha256']:
            raise ValueError('Captured response SHA-256 mismatch')
        # Re-derive links from the immutable captured response; a JSON manifest
        # alone must not be allowed to invent a citation or change its type.
        parsed = parse_api_response(raw, page['title'])
        for invariant in ('pageid','revid','title','canonical_url','revision_url','links'):
            if parsed[invariant] != page[invariant]:
                raise ValueError(f'Manifest does not match captured response: {invariant}')
        links = page.get('links')
        if not isinstance(links,list) or len(links) > MAX_LINKS_PER_PAGE:
            raise ValueError('Too many links or invalid links')
        for link in links:
            if link.get('kind') not in ('citation_external','body_external','internal','navigation'):
                raise ValueError('Unexpected link kind')
            if not isinstance(link.get('url'),str) or canonical_url(link['url']) != link['url']:
                raise ValueError('Unnormalized link URL')
    return manifest


def _db_connect(path: Path, readonly=False):
    if not path.is_file():
        raise FileNotFoundError(f'Existing initialized Médiathèque database required: {path}')
    con = sqlite3.connect(f'file:{path.resolve().as_posix()}?mode={"ro" if readonly else "rw"}', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    required = {'source_registry','source_consumer_registry','source_bindings','source_snapshots','source_representations'}
    existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required.issubset(existing):
        con.close()
        raise ValueError('Médiathèque source authority v4 schema required; initialize instance first')
    return con


def plan(path: Path, db: Path):
    manifest = checked_manifest(path)
    con = _db_connect(db, readonly=True)
    try:
        registered = con.execute('SELECT COUNT(*) FROM source_registry').fetchone()[0]
    finally:
        con.close()
    kinds = {}
    unique_urls = set()
    for page in manifest['pages']:
        unique_urls.add(page['canonical_url'])
        for link in page['links']:
            unique_urls.add(link['url'])
            kinds[link['kind']] = kinds.get(link['kind'],0) + 1
    return {'status':'PLAN_ONLY_NO_WRITES', 'instance_db':str(db),
            'existing_sources':registered,'pages':len(manifest['pages']),
            'unique_referenced_urls':len(unique_urls),'links_by_kind':kinds,
            'note':'Links are not validated evidence; snapshots not created in v1.'}


def _upsert_source(con, url, title, publisher, kind):
    key = canonical_url(url)
    row = con.execute('SELECT source_uuid FROM source_registry WHERE canonical_url_key=?',(key,)).fetchone()
    if row:
        return row['source_uuid']
    sid = str(uuid.uuid4())
    con.execute('''INSERT INTO source_registry(
        source_uuid,canonical_url,canonical_url_key,title,publisher,source_kind,source_family,status,source_metadata_json)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (sid,key,key,title,publisher,kind,'wikipedia-discovery','declared',
         '{"validation":"unreviewed","provenance":"wikipedia-discovery-only"}'))
    return sid


def _bind(con, source_uuid, ext_id, role):
    con.execute('''INSERT OR IGNORE INTO source_bindings(
        consumer_system,consumer_instance,source_uuid,external_source_id,role,evidence_class,authority_class,category,priority,declared_in_current_consumer)
        VALUES(?,?,?,?,?,?,?,?,?,1)''',
        ('encyklopedia',SCOPE,source_uuid,ext_id,role,'discovery_only','not_verified','wikipedia_links','review'))


def import_manifest(path: Path, db: Path, backup_dir: Path):
    manifest = checked_manifest(path)
    con = _db_connect(db)
    try:
        # SQLite's online backup API protects live files including active WAL data.
        backup_dir.mkdir(parents=True, exist_ok=True)
        bpath = backup_dir / ('koa_mediatheque_before_wikipedia_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite')
        destination = sqlite3.connect(bpath)
        try:
            con.backup(destination)
        finally:
            destination.close()
        before = con.total_changes
        manifest_digest = digest(path.read_bytes())
        try:
            # Extension only. Do not modify schema_meta or existing source tables' definitions.
            con.executescript('BEGIN IMMEDIATE;\n' + SQL_FILE.read_text(encoding='utf-8'))
            con.execute('''INSERT OR IGNORE INTO source_consumer_registry(
                consumer_system,consumer_instance,last_seen_at,metadata_json)
                VALUES(?,?,?,?)''', ('encyklopedia',SCOPE,now(),'{}'))
            pages_added = 0
            edges_added = 0
            for page in manifest['pages']:
                source_uuid = _upsert_source(con,page['canonical_url'],page['title'],'Wikipedia', 'wikipedia_article')
                _bind(con, source_uuid,'wiki:en:'+str(page['pageid']),'wikipedia_article')
                page_key = f'en:{page["pageid"]}:{page["revid"]}:{SCOPE}'
                con.execute('''INSERT OR IGNORE INTO wikipedia_discovered_pages(
                    page_key,source_uuid,wiki_language,page_id,revision_id,title,revision_url,retrieved_at,
                    captured_json_sha256,captured_relative_path,manifest_path,manifest_sha256,discovery_scope)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
                    page_key,source_uuid,'en',page['pageid'],page['revid'],page['title'],
                    page['revision_url'],page['retrieved_at'],page['capture_sha256'],
                    page['capture_path'],str(path.resolve()),manifest_digest,SCOPE))
                pages_added += con.execute('SELECT changes()').fetchone()[0]
                for index,link in enumerate(page['links']):
                    url = link['url']
                    kind = link['kind']
                    is_internal = kind == 'internal'
                    target = _upsert_source(con,url, urllib.parse.urlsplit(url).hostname or 'Web reference',
                                            'Wikipedia' if is_internal else None,
                                            'wikipedia_article' if is_internal else 'external_reference')
                    _bind(con, target, 'url:'+digest(url.encode('utf-8'))[:32], 'reference_discovery_candidate')
                    occ = digest(f'{page_key}|{index}|{url}|{kind}'.encode('utf-8'))
                    con.execute('''INSERT OR IGNORE INTO wikipedia_discovered_links(
                        occurrence_id,page_key,target_source_uuid,observed_url,link_kind,citation_marker,anchor_text,href_fragment)
                        VALUES(?,?,?,?,?,?,?,?)''', (occ,page_key,target,url,kind,
                        link.get('citation_marker'),link.get('anchor_text','')[:250],link.get('href_fragment')))
                    edges_added += con.execute('SELECT changes()').fetchone()[0]
            con.commit()
        except Exception:
            con.rollback()
            raise
        return {'status':'IMPORTED_PRIVATE_DISCOVERY_ONLY','backup':str(bpath),
                'pages_added':pages_added,'links_added':edges_added,
                'db_changes':con.total_changes-before,
                'note':'No KQ/KP/KA/KS approved; no source snapshots/representations created.'}
    finally:
        con.close()



def export_csv(db: Path, output: Path):
    con = _db_connect(db, readonly=True)
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wikipedia_discovered_links'").fetchone():
            raise ValueError('No Wikipedia inventory has been imported into this instance')
        if output.exists():
            raise FileExistsError('CSV export already exists; select a new filename')
        output.parent.mkdir(parents=True, exist_ok=True)
        rows=con.execute('''SELECT p.discovery_scope,p.wiki_language,p.title,p.revision_url,
            l.link_kind,l.citation_marker,l.observed_url,l.anchor_text,
            s.source_uuid,s.status AS source_status,l.review_state
            FROM wikipedia_discovered_links l
            JOIN wikipedia_discovered_pages p ON p.page_key=l.page_key
            JOIN source_registry s ON s.source_uuid=l.target_source_uuid
            ORDER BY p.title,l.link_kind,l.observed_url''')
        count=0
        with output.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f)
            writer.writerow(['scope','language','wikipedia_article','wikipedia_revision_url',
                             'link_kind','citation_marker','discovered_url','anchor_text',
                             'source_uuid','source_status','review_state'])
            for row in rows:
                writer.writerow(list(row))
                count+=1
        return {'status':'CSV_EXPORTED_NO_DB_WRITES','csv':str(output),'rows':count}
    finally:
        con.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest='command', required=True)
    harvest = subs.add_parser('collect', help='Collect curated Wikipedia EN pages into this instance')
    harvest.add_argument('--titles', type=Path, default=Path(__file__).resolve().parent / 'educational_policy_en.txt')
    harvest.add_argument('--output', type=Path)
    harvest.add_argument('--contact', required=True, help='Real contact email or https:// URL for Wikimedia User-Agent')
    harvest.add_argument('--delay', type=float, default=2.0)
    harvest.add_argument('--max-pages', type=int, default=6)
    review = subs.add_parser('plan', help='Check captured hashes and DB, with no writes')
    review.add_argument('--manifest', required=True, type=Path)
    push = subs.add_parser('import', help='Back up and add discovery-only sources into THIS instance')
    push.add_argument('--manifest', required=True, type=Path)
    push.add_argument('--accept', action='store_true', help='Required explicit authorization')
    export = subs.add_parser('export', help='CSV export of private Wikipedia source references')
    export.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        context = get_instance(require_db=args.command in ('plan', 'import', 'export'))
        db = Path(context['database'])
        if args.command == 'collect':
            out = INSTANCE_ROOT / '03_IMPORTS' / 'wikipedia' / (
                'educational-policy-en-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%f') + '.json')
            if args.output:
                out = args.output.resolve()
                require_within_private_imports(out)
            result = collect(args.titles, out, args.contact, args.delay, args.max_pages)
        elif args.command == 'export':
            out = args.output or (INSTANCE_ROOT / '04_EXPORTS' / 'wikipedia' /
                ('references-en-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%f') + '.csv'))
            out = out.resolve()
            if not out.is_relative_to((INSTANCE_ROOT / '04_EXPORTS').resolve()):
                raise ValueError('CSV must remain inside 04_EXPORTS of this instance')
            result = export_csv(db, out)
        else:
            require_within_private_imports(args.manifest)
            if args.command == 'plan' or not args.accept:
                result = plan(args.manifest, db)
            else:
                result = import_manifest(args.manifest, db, INSTANCE_ROOT / '07_BACKUPS')
        print(dump_json(result), end='')
        return 0
    except Exception as exc:
        print(dump_json({'status': 'ERROR_NO_APPROVAL', 'error': str(exc)}), end='', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
