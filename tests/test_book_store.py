"""Archived normalization, provenance, migration and CLI checks; offline replay only."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from predarb import cli, kalshi, polymarket_us as poly
from predarb.book_store import inspect_book, inspect_pair, load_book, record_normalization
from predarb.collector import collect
from predarb.provider import HttpClient
from predarb.store import connect
from predarb.validation import dumps, utc_time
from helpers import fixture, real_response, Replay


class ArchivedBooksTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=str(Path(self.temp.name)/'books.sqlite3')
        self.db=connect(self.path);self.addCleanup(self.db.close)
        self.frames={}
        for adapter,prefix in ((kalshi,'kalshi'),(poly,'poly')):
            capture=fixture(prefix+'-scoped-acceptance')
            frames=capture['responses'];self.frames[prefix]=frames
            from helpers import Response
            replay=Replay(*(Response(item['body'].encode(),item['status'],item['headers']) for item in frames))
            clock=iter(item['retrieved_at'] for item in frames)
            client=HttpClient(self.db,adapter.VENUE,opener=replay,sleep=lambda delay:None,utc_now=lambda:next(clock))
            scope=json.loads(capture['run']['scope_json'])
            collect(self.db,adapter,page_size=scope['page_size'],max_pages=scope['max_pages'],scope=scope['filter'],
                    books=scope['books'],client=client,now=utc_time(capture['run']['finished_at']))
        self.ids=dict(self.db.execute('SELECT r.venue,b.observation_id FROM book_captures b JOIN raw_observations r ON r.id=b.observation_id'))
        self.now=utc_time(self.frames['poly'][-1]['retrieved_at'])+timedelta(milliseconds=10)

    def test_collectors_archive_normalization_with_exact_metadata_provenance(self):
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM normalized_books').fetchone()[0],3)
        rows=self.db.execute('SELECT data_usable,result_json FROM normalized_books ORDER BY id').fetchall()
        self.assertEqual([row[0] for row in rows],[0,0,1])
        self.assertIn('UNKNOWN_SOURCE_TIME',rows[0][1])
        result=inspect_book(self.db,self.ids['polymarket_us'],now=self.now)
        self.assertTrue(result['data_usable'])
        self.assertFalse(result['trading_authorized'])
        self.assertEqual(str(result['yes_asks'][0]['price']),'0.6290')
        self.assertEqual(result['verification'],'UNVERIFIED')

    def test_source_status_stale_data_and_cached_assessments_are_not_authority(self):
        observed=self.ids['polymarket_us']
        fresh=inspect_book(self.db,observed,now=self.now)
        stale=inspect_book(self.db,observed,now=self.now+timedelta(seconds=61))
        self.assertTrue(fresh['data_usable']);self.assertFalse(stale['data_usable'])
        with self.assertRaisesRegex(ValueError,'STALE'):
            inspect_book(self.db,observed,now=self.now+timedelta(seconds=61),side='YES',quantity='1')
        self.db.execute("UPDATE collection_runs SET status='FAILED' WHERE venue='polymarket_us'");self.db.commit()
        result=inspect_book(self.db,observed,now=self.now)
        self.assertIn('SOURCE_RUN_NOT_COMPLETE',result['rejections'])

    def test_hash_schema_endpoint_and_cross_run_metadata_mismatch_fail_closed(self):
        observed=self.ids['polymarket_us']
        for column,value in (('body_sha256','wrong'),('schema_version','unknown-v999'),
                             ('endpoint',poly.book_url('wrong')),('truncated',1),('validation_status','REJECTED')):
            previous=self.db.execute(f'SELECT {column} FROM raw_observations WHERE id=?',(observed,)).fetchone()[0]
            self.db.execute(f'UPDATE raw_observations SET {column}=? WHERE id=?',(value,observed));self.db.commit()
            with self.subTest(column=column), self.assertRaises(ValueError): load_book(self.db,observed,now=self.now)
            self.db.execute(f'UPDATE raw_observations SET {column}=? WHERE id=?',(previous,observed));self.db.commit()
        metadata=self.db.execute('SELECT metadata_observation_id FROM normalized_books WHERE observation_id=?',(self.ids['kalshi'],)).fetchone()[0]
        with self.assertRaisesRegex(ValueError,'same catalogue run'):
            load_book(self.db,observed,now=self.now,metadata_observation_id=metadata)

    def test_rejected_assessment_preserves_original_bytes(self):
        observed=self.ids['polymarket_us']
        meta=self.db.execute('SELECT metadata_observation_id FROM normalized_books WHERE observation_id=?',(observed,)).fetchone()[0]
        before=self.db.execute('SELECT raw_body FROM raw_observations WHERE id=?',(observed,)).fetchone()[0]
        self.db.execute("UPDATE raw_observations SET schema_version='hypothetical-unsupported' WHERE id=?",(observed,));self.db.commit()
        result=record_normalization(self.db,observed,meta,now=self.now)
        self.assertFalse(result['data_usable'])
        self.assertIn('unsupported provider schema',';'.join(result['rejections']))
        self.assertEqual(self.db.execute('SELECT raw_body FROM raw_observations WHERE id=?',(observed,)).fetchone()[0],before)

    def test_schema_two_migration_preserves_archive_and_does_not_claim_old_assessments(self):
        from helpers import drop_m4_tables
        drop_m4_tables(self.db)
        expected=self.db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0]
        self.db.execute('DROP TABLE normalized_books');self.db.execute('PRAGMA user_version=2');self.db.commit();self.db.close()
        self.db=connect(self.path);self.addCleanup(self.db.close)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],9)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM normalized_books').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0],expected)
        # Prior captures can be revalidated from their archived matching detail provenance.
        self.assertTrue(inspect_book(self.db,self.ids['polymarket_us'],now=self.now)['data_usable'])

    def test_unreviewed_pair_and_unknown_source_time_are_incomparable(self):
        from predarb.registry import propose
        k_source=self.db.execute('SELECT source_id FROM book_captures WHERE observation_id=?',(self.ids['kalshi'],)).fetchone()[0]
        p_source=self.db.execute('SELECT source_id FROM book_captures WHERE observation_id=?',(self.ids['polymarket_us'],)).fetchone()[0]
        pair_id=propose(self.db,k_source,p_source,'HYPOTHETICAL proposal action for rejection test',now=self.now)
        result=inspect_pair(self.db,pair_id,self.ids['kalshi'],self.ids['polymarket_us'],now=self.now)
        self.assertFalse(result['comparison_ready'])
        self.assertIn('PAIR_NOT_APPROVED',result['rejections'])
        self.assertIn('MISSING_COMPARABLE_SOURCE_TIME',result['rejections'])
        self.assertFalse(result['fees_or_profit_evaluated'])

    def test_pair_skew_and_identity_guards_with_hypothetical_inputs(self):
        # Isolated mocked gate inputs exercise future sequenced-feed comparison, not real approvals.
        pair={'status':'APPROVED','hypothetical':False,'kalshi_id':'HYPOTHETICAL-K','polymarket_us_id':'HYPOTHETICAL-P'}
        books=[{'venue':venue,'source_id':source,'data_usable':True,'received_at':self.now.isoformat(),
                'source_ts':self.now.isoformat()} for venue,source in (('kalshi','HYPOTHETICAL-K'),('polymarket_us','HYPOTHETICAL-P'))]
        with patch('predarb.registry.review',return_value=pair):
            with patch('predarb.book_store.inspect_book',side_effect=books):
                self.assertTrue(inspect_pair(self.db,1,1,2,now=self.now)['comparison_ready'])
            for change in ('source_ts','received_at','source_id'):
                bad=deepcopy(books)
                bad[1][change]='HYPOTHETICAL-WRONG' if change=='source_id' else (self.now+timedelta(seconds=3)).isoformat()
                with self.subTest(change=change), patch('predarb.book_store.inspect_book',side_effect=bad):
                    self.assertFalse(inspect_pair(self.db,1,1,2,now=self.now)['comparison_ready'])
        with self.assertRaises(ValueError): inspect_pair(self.db,1,1,2,now=self.now,max_skew_ms=-1)

    def invoke(self,*args):
        out,err=StringIO(),StringIO()
        with patch('sys.argv',['predarb','books',*args,'--db',self.path]),redirect_stdout(out),redirect_stderr(err):
            code=cli.main()
        return code,json.loads(out.getvalue()) if out.getvalue() else None,err.getvalue()

    def test_cli_inspection_depth_replay_and_stale_failure_exit_codes(self):
        now=self.now.isoformat()
        code,result,err=self.invoke('inspect',str(self.ids['polymarket_us']),'--at',now,'--side','YES','--quantity','1')
        self.assertEqual(code,0);self.assertTrue(result['historical_replay'])
        self.assertEqual(result['result']['hypothetical_depth']['covered'],'1')
        self.assertEqual(self.invoke('inspect',str(self.ids['kalshi']),'--at',now)[0],2)
        self.assertEqual(self.invoke('list','--at',now)[0],0)
        self.assertEqual(self.invoke('inspect','999999')[0],1)
        self.assertEqual(self.invoke('inspect',str(self.ids['polymarket_us']),'--at',now,'--side','YES')[0],1)
        self.assertEqual(self.invoke('list','--limit','0')[0],1)
        self.assertNotIn('Traceback',err)

    def test_newer_metadata_and_books_supersede_old_quote_depth(self):
        from helpers import Response
        capture=fixture('poly-scoped-acceptance');frames=capture['responses']
        replay=Replay(*(Response(item['body'].encode(),item['status'],item['headers']) for item in frames))
        clock=iter((utc_time(item['retrieved_at'])+timedelta(seconds=10)).isoformat() for item in frames)
        client=HttpClient(self.db,'polymarket_us',opener=replay,sleep=lambda delay:None,utc_now=lambda:next(clock))
        scope=json.loads(capture['run']['scope_json'])
        later=self.now+timedelta(seconds=10)
        collect(self.db,poly,page_size=scope['page_size'],max_pages=scope['max_pages'],scope=scope['filter'],books=1,client=client,now=later)
        old=inspect_book(self.db,self.ids['polymarket_us'],now=later)
        self.assertIn('SUPERSEDED_BOOK',old['rejections'])
        self.assertIn('NEWER_METADATA_REQUIRES_FRESH_BOOK',old['rejections'])
        new_id=self.db.execute('SELECT MAX(observation_id) FROM book_captures').fetchone()[0]
        self.assertTrue(inspect_book(self.db,new_id,now=later)['data_usable'])
