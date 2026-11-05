import gzip
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'/'wiki'/'dump_import'))
import import_dumps as w

class MultilineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.db=w.connect(self.root/'index.sqlite'); self.addCleanup(self.db.close)
        self.p=self.root/w.FILE_NAMES['page']

    def write(self, sql):
        with gzip.open(self.p,'wb') as z:z.write(sql.encode())

    def test_multiline_statement_and_unquoted_name(self):
        self.write("""CREATE TABLE `page` (
`page_id` int,
`page_namespace` int,
`page_title` blob,
`page_is_redirect` int,
`page_latest` int,
`page_len` int
) ENGINE=InnoDB;
INSERT INTO page VALUES
(10,0,'Right_to_education',0,1001,600),
(11,0,'Education_policy',0,1002,500),
(12,1,'Talk:Education',0,1003,50)
;
""")
        w.import_stage(self.db,'page',self.p,commit_lines=1,min_free_gib=0)
        self.assertEqual(self.db.execute('select count(*) from wiki_pages').fetchone()[0],3)
        self.assertEqual(self.db.execute('select rows_imported,completed from ingest_state where stage="page"').fetchone(),(3,1))

    def test_split_quoted_tuple_and_many_lines_checkpoint(self):
        rows=''.join(f"({n},0,'Alpha_{n}',0,{n},40),\n" for n in range(1,10003))
        sql="""CREATE TABLE `page` (
`page_id` int,
`page_namespace` int,
`page_title` blob,
`page_is_redirect` int,
`page_latest` int,
`page_len` int
);
INSERT INTO `page` VALUES
""" + rows + "(10003,0,'Educa\ntion_policy',0,10003,42);\n"
        self.write(sql)
        w.import_stage(self.db,'page',self.p,commit_lines=500,min_free_gib=0)
        self.assertEqual(self.db.execute('select count(*) from wiki_pages').fetchone()[0],10003)
        self.assertEqual(self.db.execute('select title from wiki_pages where page_id=10003').fetchone()[0], 'Educa\ntion_policy')

    def test_v1_empty_checkpoint_is_rewound(self):
        self.write("""CREATE TABLE `page` (
`page_id` int,
`page_namespace` int,
`page_title` blob,
`page_is_redirect` int,
`page_latest` int,
`page_len` int
);
INSERT INTO `page` VALUES
(10,0,'Right_to_education',0,1001,600);
""")
        inf=w.source_info(self.p)
        self.db.execute('''INSERT INTO ingest_state (stage,filename,source_bytes,source_mtime_ns,committed_line,rows_imported,completed)
                            VALUES (?,?,?,?,?,?,?)''',('page',inf['file'],inf['bytes'],inf['mtime_ns'],51000000,0,0))
        self.db.commit()
        w.import_stage(self.db,'page',self.p,min_free_gib=0)
        self.assertEqual(self.db.execute('select count(*) from wiki_pages').fetchone()[0],1)
        self.assertEqual(self.db.execute('select completed from ingest_state where stage="page"').fetchone()[0],1)

    def test_resume_inside_giant_insert(self):
        self.write("""CREATE TABLE `page` (
`page_id` int,
`page_namespace` int,
`page_title` blob,
`page_is_redirect` int,
`page_latest` int,
`page_len` int
);
INSERT INTO `page` VALUES
(10,0,'A',0,100,5),
(11,0,'B',0,200,5),
(12,0,'C',0,300,5);
""")
        inf=w.source_info(self.p)
        self.db.execute('''INSERT INTO ingest_state (stage,filename,source_bytes,source_mtime_ns,committed_line,rows_imported,completed,resume_insert,schema_json)
                            VALUES (?,?,?,?,?,?,?,?,?)''',('page',inf['file'],inf['bytes'],inf['mtime_ns'],10,1,0,1,json.dumps(['page_id','page_namespace','page_title','page_is_redirect','page_latest','page_len'])))
        self.db.execute("insert into wiki_pages values (10,0,'A',0,100,5)")
        self.db.commit()
        w.import_stage(self.db,'page',self.p,min_free_gib=0)
        self.assertEqual(self.db.execute('select count(*) from wiki_pages').fetchone()[0],3)
        self.assertEqual(self.db.execute('select rows_imported from ingest_state where stage="page"').fetchone()[0],3)

    def test_old_v1_database_schema_upgrade(self):
        old=self.root/'old_v1.sqlite'
        c=sqlite3.connect(old)
        c.execute("""CREATE TABLE ingest_state(stage TEXT PRIMARY KEY,filename TEXT NOT NULL,source_bytes INTEGER NOT NULL,source_mtime_ns INTEGER NOT NULL,committed_line INTEGER NOT NULL DEFAULT 0,rows_imported INTEGER NOT NULL DEFAULT 0,completed INTEGER NOT NULL DEFAULT 0,finished_at TEXT,sha256 TEXT,schema_json TEXT)""")
        c.commit();c.close()
        migrated=w.connect(old)
        self.addCleanup(migrated.close)
        self.assertIn('resume_insert',[r[1] for r in migrated.execute('PRAGMA table_info(ingest_state)')])

    def test_empty_multiline_insert_is_rejected(self):
        self.write("""CREATE TABLE `page` (
`page_id` int,
`page_namespace` int,
`page_title` blob,
`page_is_redirect` int,
`page_latest` int,
`page_len` int
);
INSERT INTO `page` VALUES
;
""")
        with self.assertRaisesRegex(ValueError,'Empty SQL INSERT'):
            w.import_stage(self.db,'page',self.p,min_free_gib=0)

    def test_reject_nonmatching_insert_early(self):
        self.write("""CREATE TABLE `page` (
`page_id` int,
`page_namespace` int,
`page_title` blob,
`page_is_redirect` int,
`page_latest` int,
`page_len` int
);
"""+'INSERT INTO "page" VALUES (10,0,\'A\',0,1,2);\n'*110)
        with self.assertRaisesRegex(ValueError,'Unsupported SQL data layout'):
            w.import_stage(self.db,'page',self.p,min_free_gib=0)

if __name__=='__main__': unittest.main()
