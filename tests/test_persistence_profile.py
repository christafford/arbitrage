"""Genuine archived-prefix replay and explicitly HYPOTHETICAL injected faults."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from predarb import persistence_profile as profile, ws_store
from predarb.book_stream import KalshiBookStream
from predarb.backups import readonly
from predarb.validation import dumps, load_json, utc_time
from contextlib import closing

FIXTURE=Path(__file__).parent/'fixtures/m5p-profile-live.json'


class PersistenceProfileTests(unittest.TestCase):
    def setUp(self):
        self.case=load_json(FIXTURE.read_bytes())['case']
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def mutate(self,index,change):
        self.case['hypothetical']=True
        self.case['mutation_label']='HYPOTHETICAL fault injection, not a venue response'
        row=self.case['frames'][index];frame=load_json(row['body']);change(frame)
        row['body']=dumps(frame);row['sha256']=hashlib.sha256(row['body'].encode()).hexdigest()

    def test_genuine_prefix_plain_profile_exact_parity_and_no_network(self):
        before=FIXTURE.read_bytes()
        a=profile.run_case(self.case,self.root/'timed')
        b=profile.run_case(self.case,self.root/'plain',instrumented=False)
        self.assertEqual(a['normalized_sha256'],b['normalized_sha256'])
        self.assertEqual((a['frames'],a['books']),(4,3))
        self.assertEqual(a['settings']['synchronous'],2)
        self.assertEqual(a['settings']['journal_mode'],'wal')
        self.assertEqual(a['raw_hashes_verified'],5)
        self.assertTrue(a['journal_chain_verified']);self.assertEqual(FIXTURE.read_bytes(),before)
        commits={k:v['inclusive_wall']['count'] for k,v in a['phases'].items() if k.endswith('/sqlite_commit')}
        self.assertEqual(commits['capture/archive_frame/archive_raw/sqlite_commit'],4)
        self.assertEqual(commits['capture/archive_frame/sqlite_commit'],4)
        self.assertEqual(commits['capture/record_frame/validation_status/sqlite_commit'],3)
        self.assertEqual(commits['capture/record_frame/sqlite_commit'],3)
        self.assertFalse(b['phases'])

    def test_committed_pending_is_visible_to_independent_reader_before_validation(self):
        original=KalshiBookStream.apply;seen=[];output=self.root/'visibility'
        def apply(stream,*args,**kwargs):
            with closing(readonly(output/'profile.sqlite3')) as con:
                row=con.execute('SELECT r.validation_status,b.freshness,n.observation_id FROM ws_frames f JOIN raw_observations r ON r.id=f.observation_id JOIN book_captures b ON b.observation_id=r.id LEFT JOIN normalized_books n ON n.observation_id=r.id ORDER BY r.id DESC LIMIT 1').fetchone()
                self.assertEqual(row,('PENDING','UNVERIFIED_STREAM',None));seen.append(row)
            return original(stream,*args,**kwargs)
        with patch.object(KalshiBookStream,'apply',apply):profile.run_case(self.case,output)
        self.assertEqual(len(seen),3)

    def test_missing_clock_bad_price_sequence_gap_and_stale_source_fail_closed(self):
        mutations=[lambda f:f['msg'].pop('clock'),lambda f:f['msg'].update(price_dollars='1.20'),
                   lambda f:f.update(seq=f['seq']+1),lambda f:f.update(sending_ts_ms=f['sending_ts_ms']-120000)]
        for i,mutation in enumerate(mutations):
            with self.subTest(i=i):
                self.case=load_json(FIXTURE.read_bytes())['case'];self.mutate(2,mutation)
                dest=self.root/str(i)
                with self.assertRaisesRegex(ValueError,'incomplete offline capture'):profile.run_case(self.case,dest)
                self.assertEqual(load_json((dest/'status.json').read_bytes())['status'],'FAILED')
                with closing(readonly(dest/'profile.sqlite3')) as con:
                    rejected=con.execute("SELECT count(*) FROM raw_observations WHERE validation_status='REJECTED'").fetchone()[0]
                    self.assertEqual(rejected,1)
                    self.assertEqual(con.execute('SELECT count(*) FROM normalized_books').fetchone()[0],1)

    def test_partial_liquidity_stays_partial_in_persisted_and_profiled_results(self):
        # HYPOTHETICAL: remove the YES side; retained deltas update only NO.
        self.mutate(1,lambda f:f['msg'].pop('yes_dollars_fp'))
        self.case['frames']=self.case['frames'][:3]
        stream=KalshiBookStream(self.case['pair']['kalshi_id'],load_json(self.case['metadata']['body'])['market'],metadata_received_at=self.case['metadata']['received_at'])
        stream.generation=1
        for row in self.case['frames'][1:]:
            at=utc_time(row['received_at'])
            book=stream.apply(load_json(row['body']),received_at=row['received_at'],now=at,generation=1)
            row['expected_book']=load_json(dumps(replace(book,transport='KALSHI_AUTHENTICATED_WS').as_dict(now=at)))
            self.assertIn('PARTIAL_BOOK',row['expected_book']['rejections'])
        result=profile.run_case(self.case,self.root/'partial')
        self.assertEqual(result['books'],2)
        with closing(readonly(self.root/'partial/profile.sqlite3')) as con:
            self.assertEqual(con.execute('SELECT sum(data_usable) FROM normalized_books').fetchone()[0],0)

    def test_hash_tampering_fails_before_output_is_created(self):
        self.case['frames'][2]['body']='{}'
        with self.assertRaisesRegex(ValueError,'hash'):profile.run_case(self.case,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

    def test_false_expected_book_rejected_after_capture(self):
        self.case['frames'][2]['expected_book']['sequence']=999
        with self.assertRaisesRegex(ValueError,'parity'):profile.run_case(self.case,self.root/'bad')
        self.assertEqual(load_json((self.root/'bad/status.json').read_bytes())['status'],'FAILED')

    def test_commit_failure_retains_failed_result_never_success(self):
        def broken(*args,**kwargs):raise OSError('HYPOTHETICAL storage failure')
        with patch.object(ws_store,'record_frame',broken),self.assertRaises(ValueError):
            profile.run_case(self.case,self.root/'broken')
        self.assertEqual(load_json((self.root/'broken/status.json').read_bytes())['status'],'FAILED')
        self.assertFalse((self.root/'broken/result.json').exists())

    def test_existing_destination_is_never_overwritten(self):
        p=self.root/'existing';p.mkdir();(p/'sentinel').write_text('preserve')
        with self.assertRaises(FileExistsError):profile.run_case(self.case,p)
        self.assertEqual((p/'sentinel').read_text(),'preserve')

    def test_nested_timings_do_not_double_count_child_work(self):
        t=profile.Timings()
        with patch.object(profile.time,'perf_counter_ns',side_effect=[0,10,20,30]),patch.object(profile.time,'thread_time_ns',side_effect=[0,4,8,12]):
            with t.phase('parent'):
                with t.phase('child'):pass
        r=t.report()
        self.assertEqual(r['parent']['inclusive_wall']['total_ns'],30)
        self.assertEqual(r['parent']['exclusive_wall']['total_ns'],20)
        self.assertEqual(r['parent/child']['exclusive_wall']['total_ns'],10)
        self.assertEqual(r['parent']['exclusive_thread_cpu']['total_ns'],8)

    def test_source_loader_rechecks_hashes_and_never_mutates_archive(self):
        output=self.root/self.case['pair']['id']
        profile.run_case(self.case,output)
        (output/'profile.sqlite3').rename(output/'kalshi.sqlite3')
        before=(output/'kalshi.sqlite3').read_bytes()
        case=profile.source_case(self.root,self.case['pair'],3)
        self.assertEqual(len(case['frames']),3)
        self.assertEqual(case['frames'][2]['body'],self.case['frames'][2]['body'])
        self.assertEqual((output/'kalshi.sqlite3').read_bytes(),before)
        for bad in [0,1001,True]:
            with self.assertRaises(ValueError):profile.source_case(self.root,self.case['pair'],bad)
