"""Regression tests for MediaWiki 1.45+ categorylinks cl_target_id migration.

No downloaded dumps or production SQLite are read; only tempfile fixtures.
"""
from __future__ import annotations
import gzip
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'/'wiki'/'dump_import'))
import import_dumps as w

MODERN_COLS = [
    'cl_from','cl_sortkey','cl_sortkey_prefix','cl_timestamp',
    'cl_type','cl_collation_id','cl_target_id'
]
LEGACY_COLS = ['cl_from', 'cl_to', 'cl_type']


def fixture(path: Path, cols: list[str], records: list[tuple]):
    sql = "CREATE TABLE `categorylinks` (\n" + ''.join(f'  `{c}` TEXT,\n' for c in cols) + ") ENGINE=InnoDB;\n"
    for values in records:
        row = ','.join("'"+str(v).replace("'", "\\'")+"'" if isinstance(v,str) else str(v) for v in values)
        sql += "INSERT INTO `categorylinks` VALUES\n(" + row + ");\n"
    with gzip.open(path,'wb') as fp:
        fp.write(sql.encode('utf8'))


class CategorylinksFixTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.path = self.dir / w.FILE_NAMES['categorylinks']
        self.dbpath = self.dir / 'wiki_index.sqlite'
        self.conn = w.connect(self.dbpath)
        self.addCleanup(self.conn.close)
        self.conn.execute("INSERT INTO wiki_pages VALUES (10,0,'Right_to_education',0,1,1)")
        self.conn.execute("INSERT INTO wiki_linktargets VALUES (101,14,'Education_policy')")
        self.conn.execute("INSERT INTO wiki_linktargets VALUES (102,14,'Human_rights')")
        self.conn.execute("INSERT INTO wiki_linktargets VALUES (103,0,'Not_a_category')")
        self.conn.commit()

    def test_new_schema_imports_ids_without_modifying_previously_indexed_pages(self):
        fixture(self.path,MODERN_COLS,[
            (10,'alpha','','20261105000000','page',1,101),
            (10,'beta','','20261105000000','page',1,102),
            (11,'gamma','','20261105000000','subcat',1,999),
        ])
        w.import_stage(self.conn,'categorylinks',self.path,min_free_gib=0,commit_lines=1)
        w.create_indexes(self.conn,('categorylinks',))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM wiki_categorylink_ids').fetchone()[0],3)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM wiki_categorylinks').fetchone()[0],0)
        self.assertEqual(self.conn.execute('SELECT page_id FROM wiki_pages').fetchone(),(10,))
        self.assertEqual(self.conn.execute('SELECT source_page_id,category,type,category_target_id FROM wiki_categorylinks_resolved ORDER BY category_target_id').fetchall(),[
            (10,'Education_policy','page',101),(10,'Human_rights','page',102),(11,None,'subcat',999)
        ])
        self.assertEqual(self.conn.execute('SELECT completed,rows_imported FROM ingest_state WHERE stage="categorylinks"').fetchone(),(1,3))
        names={x[1] for x in self.conn.execute('PRAGMA index_list(wiki_categorylink_ids)').fetchall()}
        self.assertIn('idx_wiki_catid_from',names)
        self.assertIn('idx_wiki_catid_target',names)

    def test_failed_v101_empty_checkpoint_resumes_without_restarting_other_stages(self):
        fixture(self.path, MODERN_COLS, [(10,'a','','20261105','page',0,101)])
        info=w.source_info(self.path)
        self.conn.execute('''INSERT INTO ingest_state
            (stage,filename,source_bytes,source_mtime_ns,committed_line,rows_imported,completed)
            VALUES (?,?,?,?,?,?,?)''', ('categorylinks', info['file'],info['bytes'],info['mtime_ns'],0,0,0))
        self.conn.execute('''INSERT INTO ingest_state
            (stage,filename,source_bytes,source_mtime_ns,committed_line,rows_imported,completed)
            VALUES (?,?,?,?,?,?,?)''', ('pagelinks','some_archive.sql.gz',1024,9000,123,1600000000,1))
        self.conn.commit()
        w.import_stage(self.conn,'categorylinks',self.path,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT rows_imported,completed FROM ingest_state WHERE stage="categorylinks"').fetchone(),(1,1))
        self.assertEqual(self.conn.execute('SELECT rows_imported,completed FROM ingest_state WHERE stage="pagelinks"').fetchone(),(1600000000,1))
        w.import_stage(self.conn,'categorylinks',self.path,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM wiki_categorylink_ids').fetchone()[0],1)

    def test_resume_new_schema_at_checkpoint_without_duplicates(self):
        fixture(self.path, MODERN_COLS, [
            (10,'alpha','','20261105','page',0,101),
            (10,'beta','','20261105','page',0,102)
        ])
        w.import_stage(self.conn,'categorylinks',self.path,stop_after_statements=1,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM wiki_categorylink_ids').fetchone()[0],1)
        w.import_stage(self.conn,'categorylinks',self.path,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM wiki_categorylink_ids').fetchone()[0],2)
        self.assertEqual(self.conn.execute('SELECT rows_imported,completed FROM ingest_state WHERE stage="categorylinks"').fetchone(),(2,1))

    def test_legacy_cl_to_preserved_in_original_table_and_unified_view(self):
        fixture(self.path, LEGACY_COLS, [(10,'Education_policy','page')])
        w.import_stage(self.conn,'categorylinks',self.path,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT category FROM wiki_categorylinks').fetchone(),('Education_policy',))
        self.assertEqual(self.conn.execute('SELECT category,category_target_id FROM wiki_categorylinks_resolved').fetchone(),('Education_policy',None))

    def test_schema_without_both_target_fields_rejected_without_rows(self):
        fixture(self.path, ['cl_from','cl_type'],[(10,'page')])
        with self.assertRaisesRegex(ValueError,'missing cl_to/cl_target_id'):
            w.import_stage(self.conn,'categorylinks',self.path,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM wiki_categorylink_ids').fetchone()[0],0)

    def test_new_schema_null_target_rejected_without_marking_complete(self):
        fixture(self.path, MODERN_COLS, [(10,'alpha','','20261105','page',0,0)])
        with self.assertRaisesRegex(ValueError,'positive'):
            w.import_stage(self.conn,'categorylinks',self.path,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM wiki_categorylink_ids').fetchone()[0],0)
        self.assertEqual(self.conn.execute('SELECT completed FROM ingest_state WHERE stage="categorylinks"').fetchone(),(0,))

    def test_legacy_v101_db_upgrades_additively(self):
        legacy=self.dir/'old.sqlite'
        c=sqlite3.connect(legacy)
        c.execute('CREATE TABLE wiki_categorylinks(source_page_id INTEGER NOT NULL, category TEXT NOT NULL, type TEXT)')
        c.execute("INSERT INTO wiki_categorylinks VALUES(1,'Legacy_category','page')")
        c.execute('CREATE TABLE wiki_linktargets(target_id INTEGER PRIMARY KEY, ns INTEGER NOT NULL, title TEXT NOT NULL)')
        c.commit();c.close()
        newer=w.connect(legacy); self.addCleanup(newer.close)
        self.assertEqual(newer.execute('SELECT category FROM wiki_categorylinks').fetchone(),('Legacy_category',))
        self.assertEqual(newer.execute('SELECT category FROM wiki_categorylinks_resolved').fetchone(),('Legacy_category',))
        self.assertIsNotNone(newer.execute("SELECT name FROM sqlite_master WHERE name='wiki_categorylink_ids'").fetchone())

if __name__ == '__main__':
    unittest.main()
