from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

SRC=Path(__file__).resolve().parents[1]/'tools'/'wiki'/'dump_import'
sys.path.insert(0,str(SRC))
import import_dumps as w

SCHEMAS={
 'page': [('page_id','int'),('page_namespace','int'),('page_title','blob'),('page_is_redirect','int'),('page_latest','int'),('page_len','int')],
 'page_props':[('pp_page','int'),('pp_propname','blob'),('pp_value','blob')],
 'linktarget':[('lt_id','int'),('lt_namespace','int'),('lt_title','blob')],
 'externallinks':[('el_id','int'),('el_from','int'),('el_to_domain_index','blob'),('el_to_path','blob')],
 'pagelinks':[('pl_from','int'),('pl_target_id','int'),('pl_from_namespace','int')],
 'categorylinks':[('cl_from','int'),('cl_to','blob'),('cl_type','blob')]
}
INSERTS={
 'page':["(10,0,'Right_to_education',0,1001,600)","(11,0,'Education_policy',0,1002,500)","(12,1,'Talk:Education',0,1003,50)"],
 'page_props':["(10,'wikibase_item','Q69370')","(10,'unrelated','test')","(11,'wikibase_item','Q452348')"],
 'linktarget':["(101,0,'Education_policy')","(102,0,'Right_to_education')"],
 'externallinks':["(100,10,'https://org.unesco.', '/reports/a?x=1')","(101,11,'https://org.unesco.','/reports/a?x=1')"],
 'pagelinks':["(10,101,0)","(11,102,0)"],
 'categorylinks':["(10,'Human_rights','page')","(11,'Education_policy','page')"]
}


def write_fixture(folder):
    for stage in w.ORDER:
        cols=SCHEMAS[stage]
        sql=f'CREATE TABLE `{stage}` (\n'+''.join(f'  `{name}` {dtype},\n' for name,dtype in cols)+') ENGINE=InnoDB;\n'
        for row in INSERTS[stage]:
            sql+=f'INSERT INTO `{stage}` VALUES {row};\n'
        with gzip.open(folder/w.FILE_NAMES[stage],'wb') as out:out.write(sql.encode('utf8'))
    (folder/w.XML_NAME).write_bytes(b'not a parsed XML test, source archive only')

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.dumps=self.base/'dumps';self.dumps.mkdir()
        write_fixture(self.dumps)
        self.db=self.base/'bulk.sqlite'
        self.conn=w.connect(self.db)

    def tearDown(self):
        self.conn.close();self.tmp.cleanup()

    def test_mysql_quoted_escaping(self):
        raw=b"INSERT INTO `page` VALUES (1,0,'L\\'education',0,12,42),(2,0,'A, B (C)',0,13,100);\n"
        tab,cols,pos=w._columns_for_line(raw)
        self.assertEqual(tab,'page')
        rows=list(w._sql_rows(raw,pos))
        self.assertEqual(rows[0][2],"L'education")
        self.assertEqual(rows[1][2],'A, B (C)')
        self.assertEqual(w.unescape_mysql(b'a\\nb'), 'a\nb')

    def test_complete_sql_import_and_lookup(self):
        for st in w.ORDER:
            w.import_stage(self.conn,st,self.dumps/w.FILE_NAMES[st],commit_lines=1,min_free_gib=0)
            w.create_indexes(self.conn,(st,))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_pages').fetchone()[0],3)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_qid').fetchone()[0],2)
        self.assertEqual(self.conn.execute('SELECT qid FROM wiki_qid WHERE page_id=10').fetchone()[0],'Q69370')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_externallinks').fetchone()[0],2)
        self.assertEqual(self.conn.execute('SELECT COUNT(DISTINCT target_url) FROM wiki_externallinks').fetchone()[0],1)
        self.assertEqual(self.conn.execute('SELECT target_url FROM wiki_externallinks LIMIT 1').fetchone()[0], 'https://unesco.org/reports/a?x=1')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_pagelinks').fetchone()[0],2)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_categorylinks').fetchone()[0],2)
        self.assertTrue(all(self.conn.execute('SELECT completed,sha256 FROM ingest_state WHERE stage=?',(s,)).fetchone()[0]==1 for s in w.ORDER))

    def test_interruption_then_resume_without_duplicates(self):
        p=self.dumps/w.FILE_NAMES['pagelinks']
        w.import_stage(self.conn,'pagelinks',p,commit_lines=50,stop_after_statements=1,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_pagelinks').fetchone()[0],1)
        w.import_stage(self.conn,'pagelinks',p,commit_lines=50,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_pagelinks').fetchone()[0],2)
        w.import_stage(self.conn,'pagelinks',p,commit_lines=50,min_free_gib=0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM wiki_pagelinks').fetchone()[0],2)

    def test_reject_changed_source_mid_import(self):
        p=self.dumps/w.FILE_NAMES['page']
        w.import_stage(self.conn,'page',p,stop_after_statements=1,min_free_gib=0)
        with p.open('ab') as out:out.write(b'bad')
        with self.assertRaisesRegex(ValueError,'Archive changed'):
            w.import_stage(self.conn,'page',p,min_free_gib=0)

    def test_truncated_gzip_fails_and_recovery(self):
        p=self.dumps/w.FILE_NAMES['page']
        payload=p.read_bytes();p.write_bytes(payload[:-8])
        with self.assertRaises(Exception):
            w.import_stage(self.conn,'page',p,commit_lines=1,min_free_gib=0)
        self.assertFalse(self.conn.execute('SELECT completed FROM ingest_state WHERE stage="page"').fetchone()[0])

    def test_main_full_automatic_workflow(self):
        instance=self.base/'instance';instance.mkdir()
        with mock.patch.object(w,'check_space',return_value=500):
            status=w.main(['run','--test-allow-custom','--instance',str(instance),
                           '--dumps',str(self.dumps),'--index',str(self.db)])
        self.assertEqual(status,0)
        report=json.loads((instance/'04_EXPORTS/wikipedia/dump_index_status.json').read_text())
        self.assertEqual(report['status'],'COMPLETE_SQL_INDEX')
        self.assertEqual(len(report['stages']),6)
        self.assertIn('sha256',json.loads((instance/'03_IMPORTS/wikipedia/dumps/archive_catalog.json').read_text()))

    def test_xml_catalog_only_no_duplication(self):
        instance=self.base/'private';instance.mkdir()
        result=w.xml_archive_register(self.dumps/w.XML_NAME, instance,self.db)
        self.assertFalse(result['content_extracted'])
        self.assertTrue((instance/'03_IMPORTS/wikipedia/dumps/archive_catalog.json').exists())

    def test_scope_report(self):
        w.import_stage(self.conn,'page',self.dumps/w.FILE_NAMES['page'],commit_lines=1,min_free_gib=0)
        instance=self.base/'instance';instance.mkdir()
        report=w.manifest_export(self.conn,instance,self.dumps,self.db)
        self.assertEqual(report['status'],'PARTIAL')
        self.assertIn('sha256',report['stages']['page'])

if __name__=='__main__':unittest.main()
