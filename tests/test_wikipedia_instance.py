"""Offline contract tests: Wikipedia extension belongs to a private Blank instance."""
from __future__ import annotations
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT.parent / 'mediatheque'
SCRIPT = ROOT / 'tools/wiki/WikipediaReferenceInventory.py'
SPEC = importlib.util.spec_from_file_location('wikipedia_instance_inventory', SCRIPT)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def api_response():
    return json.dumps({'parse': {'pageid': 123, 'revid': 9876, 'title': 'Right to education',
        'text': '<div class="mw-parser-output"><p>See '
            '<a href="/wiki/Education_policy">Education policy</a> and '
            '<a href="https://example.org/intro">an outside site</a>.</p>'
            '<div class="reflist"><ol class="references">'
            '<li id="cite_note-1"><span class="reference-text">'
            '<a href="https://doi.org/10.1000/demo#chapter">Study</a>'
            '</span></li></ol></div>'
            '<div class="navbox"><a href="https://example.org/other">Navigation</a></div>'
            '</div>'}}).encode('utf-8')


class InstanceIntegration(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.base = Path(td.name)
        self.instance = self.base / 'mediatheque-references'
        self.engine = self.base / 'mediatheque'
        for d in ('01_DB','02_STORAGE','03_IMPORTS/wikipedia','04_EXPORTS','07_BACKUPS','tools'):
            (self.instance / d).mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/'mediatheque.instance.toml', self.instance/'mediatheque.instance.toml')
        shutil.copy2(ROOT/'tools/instance_guard.py', self.instance/'tools/instance_guard.py')
        for name in ('pyproject.toml','Start-KoaGui.ps1','05_TOOLS/Initialize-KoaMediathequeDb.ps1',
                     '05_TOOLS/ImportEncyKHandoff.py'):
            p = self.engine / name
            p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ENGINE/name, p)
        schema = self.engine / 'schemas/sqlite'
        schema.mkdir(parents=True)
        for f in (ENGINE/'schemas/sqlite').glob('*.sql'):
            shutil.copy2(f,schema/f.name)
        self.db = self.instance/'01_DB/koa_mediatheque.sqlite'
        with sqlite3.connect(self.db) as con:
            for no in range(1,8):
                file = next(schema.glob(f'{no:03}_*.sql'))
                con.executescript(file.read_text(encoding='utf-8-sig'))
        self.manifest = self.instance/'03_IMPORTS/wikipedia/test.json'
        self.titles = self.instance/'titles.txt'
        self.titles.write_text('Right to education\n',encoding='utf-8')
        # Replace only the private instance location, never touch the real instance.
        self.patch=mock.patch.object(M,'INSTANCE_ROOT',self.instance)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        with mock.patch.object(M,'_api_request',return_value=api_response()):
            M.collect(self.titles,self.manifest,'contact@example.com',1.0,6)

    def test_preflight_private_engine_and_schema(self):
        result=M.get_instance(True)
        self.assertEqual(result['instance_id'],'encyklopedia-references')
        self.assertEqual(Path(result['database']),self.db)
        with sqlite3.connect(self.db) as con:
            self.assertFalse(con.execute("SELECT 1 FROM sqlite_master WHERE name='wikipedia_discovered_pages'").fetchone())

    def test_manifest_link_types_and_revision(self):
        page=M.checked_manifest(self.manifest)['pages'][0]
        self.assertEqual([a['kind'] for a in page['links']], ['internal','body_external','citation_external','navigation'])
        self.assertEqual(page['links'][2]['citation_marker'],'cite_note-1')
        self.assertEqual(page['links'][2]['url'],'https://doi.org/10.1000/demo')
        self.assertTrue(page['revision_url'].endswith('oldid=9876'))

    def test_plan_and_import_without_accept_no_writes(self):
        data=self.db.read_bytes()
        with redirect_stdout(io.StringIO()) as stdout:
            status=M.main(['import','--manifest',str(self.manifest)])
        self.assertEqual(status,0)
        self.assertEqual(json.loads(stdout.getvalue())['status'],'PLAN_ONLY_NO_WRITES')
        self.assertEqual(self.db.read_bytes(), data)

    def test_accept_then_idempotency_and_no_approved_evidence(self):
        with redirect_stdout(io.StringIO()) as stdout:
            status=M.main(['import','--accept','--manifest',str(self.manifest)])
        self.assertEqual(status,0)
        r=json.loads(stdout.getvalue()); self.assertEqual(r['pages_added'],1)
        self.assertEqual(r['links_added'],4)
        self.assertTrue(Path(r['backup']).is_file())
        self.assertTrue(Path(r['backup']).is_relative_to(self.instance/'07_BACKUPS'))
        again=M.import_manifest(self.manifest,self.db,self.instance/'07_BACKUPS')
        self.assertEqual(again['pages_added'],0)
        self.assertEqual(again['links_added'],0)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM source_registry').fetchone()[0],5)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM wikipedia_discovered_links').fetchone()[0],4)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM source_snapshots').fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM source_bindings WHERE authority_class='not_verified'").fetchone()[0],5)

    def test_csv_export_is_private(self):
        M.import_manifest(self.manifest,self.db,self.instance/'07_BACKUPS')
        csv_file=self.instance/'04_EXPORTS/wikipedia/export.csv'
        with redirect_stdout(io.StringIO()) as stdout:
            status=M.main(['export','--output',str(csv_file)])
        self.assertEqual(status,0,stdout.getvalue())
        self.assertIn('cite_note-1',csv_file.read_text(encoding='utf-8-sig'))

    def test_reject_external_manifest_location(self):
        other=self.base/'outside.json'
        other.write_bytes(self.manifest.read_bytes())
        with redirect_stderr(io.StringIO()) as errs:
            status=M.main(['plan','--manifest',str(other)])
        self.assertEqual(status,2)
        self.assertIn('03_IMPORTS',errs.getvalue())

    def test_tampered_capture_rejected(self):
        page=M.checked_manifest(self.manifest)['pages'][0]
        (self.manifest.parent/page['capture_path']).write_bytes(b'TAMPERED')
        with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
            M.checked_manifest(self.manifest)

    def test_wrong_instance_id_blocked(self):
        manifest=self.instance/'mediatheque.instance.toml'
        manifest.write_text(manifest.read_text().replace('encyklopedia-references','blank'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Instance identity mismatch'):
            M.get_instance(True)

    def test_no_db_side_effect_when_uninitialized(self):
        self.db.unlink()
        with redirect_stderr(io.StringIO()) as errs:
            status=M.main(['plan','--manifest',str(self.manifest)])
        self.assertEqual(status,2)
        self.assertFalse(self.db.exists())

    def test_export_outside_instance_refused(self):
        with redirect_stderr(io.StringIO()) as errs:
            status=M.main(['export','--output',str(self.base/'escape.csv')])
        self.assertEqual(status,2)
        self.assertFalse((self.base/'escape.csv').exists())

    def test_collect_outside_instance_refused(self):
        with redirect_stderr(io.StringIO()) as errs:
            status=M.main(['collect','--contact','contact@example.com','--output',str(self.base/'escape.json')])
        self.assertEqual(status,2)
        self.assertFalse((self.base/'escape.json').exists())

if __name__=='__main__':
    unittest.main()
