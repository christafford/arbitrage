"""Hypothetical coordinator, clock, gap and comparison tests; no live requests."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import hashlib
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from predarb import stream_comparison as c
from predarb import stream_comparison_audit as audit
from predarb.store import connect

AT=datetime(2026,11,1,18,tzinfo=timezone.utc)


def book(**changes):
    return dict(source_ts=AT.isoformat(),received_at=AT.isoformat(),rejections=[],
                data_usable=True,connected=True,**changes)


class ComparisonTests(unittest.TestCase):
    def test_fresh_overlap_never_implies_continuity_or_economics(self):
        result=c.comparison({'kalshi':book(),'polymarket_us':book()},AT)
        self.assertTrue(result['timestamp_depth_overlap'])
        self.assertEqual(result['us_continuity'],'UNKNOWN')
        self.assertFalse(result['economic_eligibility'])

    def test_missing_stale_future_partial_invalid_disconnected_and_skew(self):
        good={'kalshi':book(),'polymarket_us':book()}
        cases=[{}, {'polymarket_us':book()}]
        for field,value in [('source_ts',None),('source_ts',(AT-timedelta(seconds=3)).isoformat()),
                            ('received_at',(AT+timedelta(seconds=1)).isoformat()),
                            ('connected',False),('data_usable',False),
                            ('rejections',['PARTIAL_OR_EMPTY_BOOK']),('rejections',['INVALID_FRAME'])]:
            changed={**good,'polymarket_us':{**book(),field:value}};cases.append(changed)
        for books in cases:self.assertFalse(c.comparison(books,AT)['timestamp_depth_overlap'])
        self.assertFalse(c.comparison(good,AT+timedelta(seconds=3))['timestamp_depth_overlap'])


class CoordinatorTests(unittest.TestCase):
    def test_preflight_open_identity_and_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            markets={'kalshi':{'ticker':'HYPOTHETICAL','status':'active'},
                     'polymarket_us':{'slug':'hypothetical','active':True,'closed':False,'status':'MARKET_STATUS_OPEN'}}
            class Client:
                def __init__(self,con,venue,**kw):self.venue=venue
                def get(self,*args):return SimpleNamespace(data={'market':markets[self.venue]},id=1,received_at=AT.isoformat())
            with patch.object(c,'HttpClient',Client):
                c.preflight(root,'HYPOTHETICAL',['hypothetical'])
                self.assertEqual(set(json.loads((root/'metadata.json').read_text())),{'HYPOTHETICAL','hypothetical'})
                markets['polymarket_us']['closed']=True
                with self.assertRaisesRegex(ValueError,'not open'):c.preflight(root,'HYPOTHETICAL',['hypothetical'])
                markets['polymarket_us']['closed']=False
                markets['kalshi']['ticker']='WRONG'
                with self.assertRaisesRegex(ValueError,'identity'):c.preflight(root,'HYPOTHETICAL',['hypothetical'])
                del markets['kalshi']['ticker']
                with self.assertRaises(KeyError):c.preflight(root,'HYPOTHETICAL',['hypothetical'])

    def fake_run(self,root,seconds=5,*,early_kalshi=False,stop=None,free=2*1024**3,clock_jump=False,
                 us_error=None,missing_us_result=False,force_kill=False,launch_error=False):
        current=[0.0];children=[]
        def sleep(n):current[0]+=n
        def launch(argv,**kw):
            if launch_error:raise OSError('hypothetical launch failure')
            is_us='--slug' in argv
            duration=int(argv[argv.index('--seconds')+1]);started=current[0]
            directory=Path(argv[argv.index('--output')+1]) if is_us else None
            if directory:directory.mkdir()
            class Child:
                returncode=None
                def poll(self):
                    if self.returncode is None and ((is_us and current[0]>=started+(1 if us_error or missing_us_result else duration)) or (not is_us and early_kalshi)):
                        self.returncode=0
                        if directory and not missing_us_result:c.write_json(directory/'results.json',us_error or {'reason':'BUDGET_COMPLETE'})
                    return self.returncode
                def terminate(self):self.returncode=2
                def wait(self,timeout):
                    if force_kill and self.returncode != -9:raise c.subprocess.TimeoutExpired('hypothetical-child',timeout)
                    return self.returncode
                def kill(self):self.returncode=-9
            child=Child();children.append((argv,child));return child
        with patch.object(c.shutil,'disk_usage',return_value=SimpleNamespace(free=free)):
            result=c.run(root,'HYPOTHETICAL-TICKER',['hypothetical-market'],seconds=seconds,
                us_credentials='hypothetical-key-path',kalshi_credentials='hypothetical-key-path',
                stop=stop or threading.Event(),prepare=lambda *args:None,
                probe_clock=lambda:{'synchronized':True},launch=launch,
                monotonic=lambda:current[0],wall=lambda:AT+timedelta(seconds=current[0]*(2 if clock_jump else 1)),sleep=sleep)
        return result,children

    def test_fixed_deadline_independent_children_and_segment_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'capture';result,children=self.fake_run(root,seconds=605)
            self.assertEqual(result['reason'],'DURATION_COMPLETE')
            self.assertEqual(result['samples'],605)
            self.assertEqual(result['elapsed_seconds'],605)
            self.assertEqual(len(children),4)
            durations=[argv[argv.index('--seconds')+1] for argv,child in children]
            self.assertEqual(durations,['605','300','300','5'])
            self.assertTrue(all(child.returncode is not None for argv,child in children))
            self.assertFalse(result['economic_eligibility'])
            with self.assertRaises(FileExistsError):self.fake_run(root)

    def test_resource_clock_interrupt_and_early_exit_are_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop=threading.Event();stop.set()
            for name,kwargs,reason in [('early',{'early_kalshi':True},'KALSHI_ENDED_EARLY'),
                                      ('disk',{'free':0},'LOW_DISK'),
                                      ('signal',{'stop':stop},'INTERRUPTED'),
                                      ('clock',{'clock_jump':True},'WALL_CLOCK_JUMP')]:
                result,children=self.fake_run(Path(tmp)/name,**kwargs)
                self.assertEqual(result['reason'],reason)
                self.assertTrue(all(child.returncode is not None for argv,child in children))

    def test_bounds_and_unsynchronized_clock_fail_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            for seconds in [0,901,True]:
                with self.assertRaises(ValueError):self.fake_run(Path(tmp)/'bad',seconds=seconds)
            with self.assertRaisesRegex(ValueError,'synchronization'):
                c.run(Path(tmp)/'clock','HYPOTHETICAL',['hypothetical'],seconds=5,
                    us_credentials='unused',kalshi_credentials='unused',stop=threading.Event(),
                    probe_clock=lambda:{'synchronized':False},prepare=lambda *a:self.fail('no network'))

    def test_us_auth_schema_missing_results_and_retry_budget_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name,kwargs,reason in [
                ('auth',{'us_error':{'reason':'CAPTURE_ERROR','http_status':401}},'US_REJECTED_CAPTURE'),
                ('schema',{'us_error':{'reason':'INVALID_FRAME'}},'US_REJECTED_CAPTURE'),
                ('missing',{'missing_us_result':True},'US_MISSING_RESULT'),
                ('retry',{'us_error':{'reason':'CAPTURE_ERROR'},'seconds':100},'US_CONNECTION_LIMIT')]:
                result,children=self.fake_run(Path(tmp)/name,**kwargs)
                self.assertEqual(result['reason'],reason)
                self.assertLessEqual(len(children),21)

    def test_owned_children_forced_cleanup_and_launch_failure_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,children=self.fake_run(Path(tmp)/'kill',force_kill=True)
            self.assertEqual(result['reason'],'FORCED_CHILD_STOP')
            self.assertTrue(all(child.returncode == -9 for argv,child in children))
            root=Path(tmp)/'launch'
            with self.assertRaises(OSError):self.fake_run(root,launch_error=True)
            self.assertEqual(json.loads((root/'status.json').read_text())['reason'],'SUPERVISOR_ERROR')


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        fixture=json.loads((Path(__file__).parent/'fixtures/dual-stream-smoke-live.json').read_text())
        self.assertEqual(fixture['kind'],'GENUINE_SANITIZED_DUAL_STREAM_SMOKE')
        for name,item in fixture['files'].items():
            body=item['body'].encode();self.assertEqual(hashlib.sha256(body).hexdigest(),item['sha256'])
            path=self.root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(body)
        with connect(str(self.root/'kalshi.sqlite3')) as con:
            for table in ('collection_runs','raw_observations','catalogue_entries','book_captures',
                          'ws_connections','ws_frames','normalized_books'):
                for row in fixture['tables'][table]:
                    if 'raw_body' in row:row['raw_body']=row['raw_body'].encode()
                    columns=list(row)
                    con.execute('INSERT INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for k in columns)+')',list(row.values()))
            con.commit()

    def test_genuine_capture_replays_all_source_hashes_and_sample_comparisons(self):
        result=audit.audit(self.root)
        self.assertEqual(result['samples'],10)
        self.assertEqual(result['timestamp_depth_overlap_samples'],8)
        self.assertEqual(result['kalshi_raw_hashes_verified'],23)
        self.assertFalse(result['economic_eligibility'])
        self.assertEqual(result['us_sequence_continuity'],'UNKNOWN')
        self.assertEqual(sum(result['approval_economics_counts'].values()),0)

    def test_hypothetical_missing_segment_and_changed_frame_fail_closed(self):
        path=self.root/'us-001/results.json';original=path.read_bytes();path.unlink()
        with self.assertRaises(FileNotFoundError):audit.audit(self.root)
        path.write_bytes(original)
        (self.root/'us-001/000001.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash'):audit.audit(self.root)

    def test_hypothetical_regressed_samples_and_wrong_scope_are_rejected(self):
        path=self.root/'samples.jsonl';original=path.read_text();rows=[json.loads(x) for x in original.splitlines()]
        rows[1]['monotonic']=rows[0]['monotonic'];path.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
        with self.assertRaisesRegex(ValueError,'regressed'):audit.audit(self.root)
        path.write_text(original)
        config=json.loads((self.root/'config.json').read_text());config['ticker']='HYPOTHETICAL-WRONG'
        c.write_json(self.root/'config.json',config)
        with self.assertRaisesRegex(ValueError,'scope'):audit.audit(self.root)

    def test_hypothetical_disconnected_future_and_prior_generation_not_reused(self):
        rows=[json.loads(x) for x in (self.root/'us-001/timing.jsonl').read_text().splitlines()]
        result=json.loads((self.root/'us-001/results.json').read_text());slug=result['slugs'][0]
        first=next(row for row in rows if row.get('market')==slug)
        sample={'at':first['received_at'],'monotonic':first['receive_monotonic']}
        self.assertTrue(audit.sample_us((result,rows),slug,sample)['connected'])
        self.assertIsNone(audit.sample_us(None,slug,sample))
        sample['monotonic']-=.001
        self.assertIsNone(audit.sample_us((result,rows),slug,sample))
        sample={'at':result['finished_at'],'monotonic':result['start_monotonic']+result['elapsed_seconds']+1}
        self.assertFalse(audit.sample_us((result,rows),slug,sample)['connected'])

    def test_hypothetical_lost_clock_sync_blocks_overlap(self):
        c.write_json(self.root/'clock-after.json',{'synchronized':False})
        result=audit.audit(self.root)
        self.assertEqual(result['timestamp_depth_overlap_samples'],0)
        self.assertEqual(result['rejections']['LOCAL_CLOCK_UNVERIFIED'],10)
