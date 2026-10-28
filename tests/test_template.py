from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from shutil import copy2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from instance_guard import check  # noqa: E402
from guard_git import check as check_git  # noqa: E402


class InstancePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.instance = base / 'mediatheque-blank'
        self.engine = base / 'mediatheque'
        self.instance.mkdir()
        self.engine.mkdir()
        (self.instance / '01_DB').mkdir()
        (self.instance / '02_STORAGE').mkdir()
        copy2(ROOT / 'mediatheque.instance.toml', self.instance / 'mediatheque.instance.toml')
        (self.engine / 'pyproject.toml').write_text('[project]\nversion = "0.5.1"\n', encoding='utf-8')
        for p in ('Start-KoaGui.ps1', '05_TOOLS/Initialize-KoaMediathequeDb.ps1',
                  '05_TOOLS/ImportEncyKHandoff.py', 'schemas/sqlite/007_source_authority.sql'):
            item = self.engine / p
            item.parent.mkdir(parents=True, exist_ok=True)
            item.write_text('fixture', encoding='utf-8')

    def test_clean_blank_ready_uninitialized(self):
        result = check(self.instance)
        self.assertEqual(result['status'], 'template_not_initialized')
        self.assertFalse(result['initialized'])
        self.assertEqual(result['engine_version'], '0.5.1')
        self.assertFalse((self.instance / '01_DB/koa_mediatheque.sqlite').exists())

    def test_require_database_refuses_missing_without_creation(self):
        with self.assertRaisesRegex(ValueError, 'n.existe pas'):
            check(self.instance, require_db=True)
        self.assertFalse((self.instance / '01_DB/koa_mediatheque.sqlite').exists())

    def test_real_structure_can_be_read_only_validated(self):
        db_path = self.instance / '01_DB/koa_mediatheque.sqlite'
        db = sqlite3.connect(db_path)
        try:
            for name in ('source_registry', 'source_snapshots', 'source_representations'):
                db.execute(f'CREATE TABLE {name}(id TEXT)')
            db.commit()
        finally:
            db.close()
        result = check(self.instance, require_db=True)
        self.assertEqual(result['status'], 'ready')
        self.assertTrue(result['initialized'])

    def test_wrong_schema_refuses(self):
        sqlite3.connect(self.instance / '01_DB/koa_mediatheque.sqlite').close()
        with self.assertRaisesRegex(ValueError, 'sans schéma'):
            check(self.instance, require_db=True)

    def test_wrong_engine_version_refuses(self):
        (self.engine / 'pyproject.toml').write_text('[project]\nversion = "0.5.0"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Moteur non qualifié'):
            check(self.instance)

    def test_wrong_engine_path_refuses(self):
        p = self.instance / 'mediatheque.instance.toml'
        p.write_text(p.read_text(encoding='utf-8').replace('../mediatheque', '../autre-moteur'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'moteur commun'):
            check(self.instance)

    def test_nonprivate_refuses(self):
        p = self.instance / 'mediatheque.instance.toml'
        p.write_text(p.read_text(encoding='utf-8').replace('visibility = "private"', 'visibility = "public"'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'visibility'):
            check(self.instance)

    def test_db_outside_refuses(self):
        p = self.instance / 'mediatheque.instance.toml'
        p.write_text(p.read_text(encoding='utf-8').replace('01_DB/koa_mediatheque.sqlite', '../mediatheque-uckk/01_DB/existing.sqlite'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'database'):
            check(self.instance)

    def test_symlink_storage_refuses(self):
        (self.instance / '02_STORAGE').rmdir()
        other = Path(self.tmp.name) / 'mediatheque-uckk'
        other.mkdir()
        try:
            (self.instance / '02_STORAGE').symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symbolic links unavailable on this host')
        with self.assertRaisesRegex(ValueError, 'Lien symbolique'):
            check(self.instance)

    def test_cli_json_no_writes(self):
        script = ROOT / 'tools/instance_guard.py'
        run = subprocess.run([sys.executable, str(script), '--instance-root', str(self.instance)],
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)['no_writes'])

    def test_cli_failure_closed(self):
        script = ROOT / 'tools/instance_guard.py'
        run = subprocess.run([sys.executable, str(script), '--instance-root', str(self.instance), '--require-db'],
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stderr)['status'], 'blocked')


class GitPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        copy2(ROOT / '.gitignore', self.root / '.gitignore')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name in ('01_DB', '02_STORAGE/source_files', '03_IMPORTS/pending_review', 'documents', 'kristals'):
            d = self.root / name
            d.mkdir(parents=True)
            (d / '.gitkeep').write_text('', encoding='utf-8')

    def test_git_stages_placeholders_not_private_content(self):
        (self.root / '01_DB/koa_mediatheque.sqlite').write_text('PRIVATE', encoding='utf-8')
        (self.root / '02_STORAGE/source_files/private.pdf').write_bytes(b'PRIVATE')
        (self.root / 'documents/private.txt').write_text('PRIVATE', encoding='utf-8')
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True)
        tracked = subprocess.run(['git', 'ls-files'], cwd=self.root, check=True,
                                 text=True, capture_output=True).stdout.splitlines()
        self.assertIn('02_STORAGE/source_files/.gitkeep', tracked)
        self.assertIn('03_IMPORTS/pending_review/.gitkeep', tracked)
        self.assertNotIn('01_DB/koa_mediatheque.sqlite', tracked)
        self.assertNotIn('02_STORAGE/source_files/private.pdf', tracked)
        self.assertNotIn('documents/private.txt', tracked)
        self.assertEqual(check_git(self.root), [])

    def test_git_force_added_private_file_refused(self):
        secret = self.root / '01_DB/koa_mediatheque.sqlite'
        secret.write_text('PRIVATE', encoding='utf-8')
        subprocess.run(['git', 'add', '-f', str(secret)], cwd=self.root, check=True)
        self.assertIn('01_DB/koa_mediatheque.sqlite', check_git(self.root))

    def test_git_previously_tracked_data_refused(self):
        p = self.root / 'documents/private-note.md'
        p.write_text('PRIVATE', encoding='utf-8')
        subprocess.run(['git', 'add', '-f', str(p)], cwd=self.root, check=True)
        self.assertIn('documents/private-note.md', check_git(self.root))


if __name__ == '__main__':
    unittest.main()
