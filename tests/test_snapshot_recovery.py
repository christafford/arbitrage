"""HYPOTHETICAL in-band recovery transport and cadence faults, no live I/O."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
import unittest
from unittest.mock import patch

import test_kalshi_ws as helpers
from predarb import snapshot_recovery as recovery, ws_store, kalshi_ws
from predarb.cadence import summarize, decision, screen
from predarb.quality_capture import State
from predarb.validation import dumps, utc_time
from test_continuous_research import hypothetical


class RecoveryTransportTests(unittest.TestCase):
    def setUp(self):
        self.e=helpers.StreamCaptureTests();self.e.setUp();self.addCleanup(self.e.doCleanups)

    def run_mode(self, response='snapshot', duration=12):
        e=self.e;seen=[]
        class ResponsiveSocket(helpers.Socket):
            def __init__(self):
                super().__init__([e.ack(),e.snapshot()],e.clock);self.seq=10;self.clock_value=100
            def send(self,raw):
                super().send(raw);cmd=helpers.loads(raw)
                if cmd['cmd']=='subscribe':return
                # A raw request must be committed before any network send.
                assert e.db.execute('SELECT count(*) FROM raw_observations WHERE schema_version=?',(recovery.COMMAND_SCHEMA,)).fetchone()[0]>0
                if response=='timeout':return
                sent=int(e.clock.now().timestamp()*1000)
                if response in {'ack','ack-only','duplicate','wrong-id','gap'}:
                    self.seq+=1
                    ack=dict(type='ok',id=cmd['id']+(1 if response=='wrong-id' else 0),sid=7,seq=self.seq,
                        sending_ts_ms=sent,msg=dict(market_tickers=[e.source]))
                    if response=='gap':ack['seq']+=1
                    self.frames.append(ack)
                    if response=='duplicate':self.frames.append(ack)
                    if response=='ack-only':return
                self.seq+=1;self.clock_value+=1
                f=e.snapshot(seq=self.seq);f['sending_ts_ms']=sent;f['msg']['clock']=self.clock_value
                if response=='partial':f['msg'].pop('no_dollars_fp')
                if response=='missing-clock':f['msg'].pop('clock')
                if response=='invalid-price':f['msg']['yes_dollars_fp']=[['1.20','1.00']]
                if response=='stale':f['sending_ts_ms']-=61000
                self.frames.append(f)
        sock=ResponsiveSocket()
        result=kalshi_ws.capture(e.db,e.source,helpers.FakeCredentials(),seconds=duration,max_connections=1,
            directory=e.tmp.name,metadata_loader=e.metadata,connect_socket=lambda _:sock,
            now=e.clock.now,monotonic=e.clock.monotonic,sleep=e.clock.sleep,
            recovery_policy='inband-snapshot',on_state=lambda db,event,book:seen.append((event,book)))
        return result,seen,sock

    def test_quiet_books_recover_on_same_socket_and_requests_are_readonly(self):
        r,events,sock=self.run_mode()
        self.assertEqual(r['connections'],1);self.assertEqual(r['failures'],[])
        self.assertEqual(r['snapshot_requests'],2);self.assertEqual(r['snapshot_responses'],2)
        self.assertEqual([x['params'].get('action') for x in sock.sent[1:]],['get_snapshot','get_snapshot'])
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM pairs').fetchone()[0],0)

    def test_control_sequence_continues_without_refreshing_book_clock(self):
        r,events,_=self.run_mode('ack')
        self.assertEqual(r['control_acknowledgments'],2);self.assertEqual(r['failures'],[])
        state=State();old=None
        for event,book in events:
            if event['kind']=='book':
                event=dict(event,at=book.received_at,channel='kalshi');state.apply(event,book);old=state.source_timestamp
            if event['kind']=='control':
                state.apply(dict(event,at=event['received_at'],channel='kalshi'))
                self.assertEqual(state.source_timestamp,old)
        self.assertEqual(len([e for e,b in events if e['kind']=='control']),2)

    def test_timeout_and_ack_without_snapshot_fail_closed(self):
        for mode in ['timeout','ack-only']:
            with self.subTest(mode=mode):
                self.setUp();r,_,_=self.run_mode(mode)
                self.assertEqual(r['failures'],['SNAPSHOT_RESPONSE_TIMEOUT'])
                self.assertEqual(r['snapshot_responses'],0)

    def test_unknown_malformed_stale_or_noncontiguous_responses_fail_closed(self):
        for mode in ['missing-clock','invalid-price','stale','wrong-id','gap','duplicate']:
            with self.subTest(mode=mode):
                self.setUp();r,_,_=self.run_mode(mode)
                self.assertTrue(r['failures'])
                self.assertLess(self.e.clock.monotonic(),12)

    def test_empty_side_stays_partial_and_can_recover_on_same_connection(self):
        r,events,_=self.run_mode('partial')
        self.assertEqual(r['failures'],[])
        books=[b for e,b in events if b]
        self.assertIn('PARTIAL_BOOK',books[-1].issues(now=utc_time(books[-1].received_at)))

    def test_default_and_production_consumers_cannot_enable_control_path(self):
        e=self.e
        with self.assertRaisesRegex(ValueError,'isolated'):
            kalshi_ws.capture(e.db,e.source,helpers.FakeCredentials(),recovery_policy='inband-snapshot')
        with self.assertRaisesRegex(ValueError,'policy'):
            kalshi_ws.capture(e.db,e.source,helpers.FakeCredentials(),recovery_policy='unknown')
        raw=dumps(dict(type='ok',id=2,msg=dict(market_tickers=[e.source])))
        self.assertEqual(ws_store.safe_frame(raw)[2],'REDACTED')
        self.assertEqual(ws_store.safe_frame(raw,allow_control=True)[2],'EXACT_WIRE')
        unsafe=dumps(dict(type='ok',id=2,msg=dict(account_id='HYPOTHETICAL_PRIVATE')))
        self.assertEqual(ws_store.safe_frame(unsafe,allow_control=True)[2],'REDACTED')

    def test_periodic_snapshot_uses_existing_connection_then_rotates_metadata(self):
        r,_,_=self.run_mode('snapshot',duration=50)
        self.assertEqual(r['connections'],1)
        self.assertEqual(r['failures'],[])
        self.assertEqual(self.e.db.execute('SELECT end_reason FROM ws_connections').fetchone()[0],'METADATA_OR_FRAME_ROTATION')
        self.assertLess(self.e.clock.monotonic(),46)

    def test_raw_command_provenance_connection_time_and_hash_are_required(self):
        r,events,_=self.run_mode('ack')
        event=next(e for e,b in events if e['kind']=='control')
        args=(self.e.db,event['command_observation_id'],event['connection_id'],self.e.source,7,event['received_at'])
        self.assertEqual(recovery.load_command(*args)['params']['action'],'get_snapshot')
        with self.assertRaisesRegex(ValueError,'identity'):
            recovery.load_command(args[0],args[1],999,*args[3:])
        with self.assertRaisesRegex(ValueError,'after response'):
            recovery.load_command(*args[:-1],self.e.case['clock'])
        self.e.db.execute('UPDATE raw_observations SET raw_body=? WHERE id=?',(b'{}',args[1]));self.e.db.commit()
        with self.assertRaisesRegex(ValueError,'provenance'):recovery.load_command(*args)

    def test_response_deadline_request_spacing_and_stop_bounds(self):
        r=recovery.Recovery(0)
        self.assertFalse(r.due(5,None));self.assertTrue(r.due(5,7))
        r.sent(5,1);self.assertFalse(r.due(9,7));self.assertFalse(r.timed_out(9))
        self.assertTrue(r.timed_out(10));r.book(6,False);self.assertTrue(r.timed_out(10))
        r.book(10,True);self.assertFalse(r.timed_out(11));self.assertFalse(r.due(11,7))
        self.assertTrue(r.due(15,7))


class CadenceTests(unittest.TestCase):
    def setUp(self):
        self.data,self.at,self.books,self.pair=hypothetical()

    def test_no_updates_keeps_entire_window_and_unknown_interarrival(self):
        c=summarize([],self.at.isoformat(),(self.at+timedelta(seconds=300)).isoformat())
        self.assertEqual(c['max_gap_including_startup_and_tail_seconds'],300)
        self.assertIsNone(c['interarrival_seconds']['p95'])

    def test_repeats_restarts_and_quiet_tail_do_not_inflate_cadence(self):
        events=[]
        for i,g in [(1,1),(2,1),(10,2)]:
            events.append((dict(kind='book',channel='us_ws',generation=g,at=(self.at+timedelta(seconds=i)).isoformat()),self.books[1]))
        c=summarize(events,self.at.isoformat(),(self.at+timedelta(seconds=300)).isoformat())
        self.assertEqual(c['counts']['repeated_source_timestamps'],2)
        self.assertEqual(c['counts'].get('observed_depth_changes',0),0)
        self.assertEqual(c['max_gap_including_startup_and_tail_seconds'],290)
        self.assertEqual(c['interarrival_seconds']['p95'],8)
        self.assertEqual(c['interarrival_seconds']['median'],D('4.5'))

    def test_invalid_or_partial_books_do_not_count_as_valid_update_cadence(self):
        for reasons in [('INVALID_BOOK:off-grid',),('PARTIAL_BOOK',)]:
            event=dict(kind='book',channel='us_ws',generation=1,at=self.at.isoformat())
            c=summarize([(event,replace(self.books[1],rejections=reasons))],self.at.isoformat(),(self.at+timedelta(seconds=300)).isoformat())
            self.assertEqual(c['counts']['rejected_books'],1)
            self.assertEqual(c['interarrival_seconds']['count'],0)
            self.assertEqual(c['max_gap_including_startup_and_tail_seconds'],300)

    def test_selection_requires_full_window_halves_sample_and_wall_targets(self):
        r=dict(samples=dict(us_ws=dict(samples=300,valid_samples=180)),valid_local_market_state_percent=dict(us_ws='60'),
            status='DEADLINE_REACHED',errors=[],early_receivers={})
        cadence=dict(counts=dict(observed_depth_changes=10))
        self.assertTrue(decision(r,cadence,300,[D(60),D(60)])['eligible_for_further_observation'])
        self.assertFalse(decision(r,cadence,299,[D(60),D(60)])['eligible_for_further_observation'])
        self.assertFalse(decision(r,cadence,300,[D(100),D(20)])['eligible_for_further_observation'])
        r['valid_local_market_state_percent']['us_ws']='49'
        self.assertIn('WALL_COVERAGE_LT_50_PERCENT',decision(r,cadence,300,[D(49),D(49)])['rejections'])
        r['status']='INTERRUPTED';r['samples']['us_ws']['valid_samples']=0
        d=decision(r,dict(counts={}),300,[D(0),D(0)])
        self.assertIn('INCOMPLETE_OR_FAILED_WORKER',d['rejections'])
        self.assertIn('SAMPLE_COVERAGE_LT_50_PERCENT',d['rejections'])
        self.assertIn('FEWER_THAN_FIVE_OBSERVED_US_DEPTH_CHANGES',d['rejections'])

    def test_invalid_window_or_missing_book_cannot_rank(self):
        event=dict(kind='book',channel='us_ws',at=(self.at+timedelta(seconds=301)).isoformat())
        with self.assertRaisesRegex(ValueError,'outside'):summarize([(event,self.books[1])],self.at.isoformat(),(self.at+timedelta(seconds=300)).isoformat())
        event['at']=self.at.isoformat()
        with self.assertRaisesRegex(ValueError,'missing'):summarize([(event,None)],self.at.isoformat(),(self.at+timedelta(seconds=300)).isoformat())


import test_quality_recovery
from predarb.validation import load_json

class GenuineRecoveryReplay(test_quality_recovery.GenuineEventReplay):
    fixture_name='m5p-inband-live.json'

    def test_actual_quiet_feed_requested_snapshots_replay_without_reconnection(self):
        result=load_json(self.fixture['files']['result.json']['body'])
        stats=result['receiver_results']['kalshi']
        self.assertEqual(stats['connections'],1)
        self.assertEqual(stats['snapshot_requests'],3)
        self.assertEqual(stats['snapshot_responses'],3)
        self.assertEqual(stats['failures'],[])
        self.assertEqual(self.replay()['replay'],'PASS')

    def test_short_successful_smoke_is_not_selected_as_five_minute_screen(self):
        from predarb.cadence import decision,summarize
        result=load_json(self.fixture['files']['result.json']['body'])
        d=decision(result,dict(counts=dict(observed_depth_changes=100)),20,[D(100),D(100)])
        self.assertFalse(d['eligible_for_further_observation'])
        self.assertIn('SCREEN_SHORTER_THAN_300S',d['rejections'])


class SelectionTests(unittest.TestCase):
    def test_supplied_scope_preserves_discovery_and_exact_source_bindings(self):
        import tempfile
        import scripts.m5p_select as select
        from predarb.provider import Observation
        from predarb.store import archive_response,validate_observation
        from predarb.validation import load_json
        fixture=load_json((Path(__file__).parent/'fixtures/m5p-selection-live.json').read_bytes())
        original=load_json((Path(__file__).parent/'fixtures/m5p-event-replay-live.json').read_bytes())
        proposals=deepcopy(original['config']['pairs'])
        for pair in proposals:
            pair['classification']='DISCOVERY';pair['ordinary_basis']='HYPOTHETICAL selection workflow test over genuine source bytes'
        responses={r['endpoint']:r for r in fixture['responses']}
        class Client:
            def __init__(self,con,venue,**kw):self.con,self.venue=con,venue
            def get(self,url,schema,validator):
                r=responses[url];body=r['body'].encode();data=load_json(body)
                oid=archive_response(self.con,self.venue,url,body,200,{},r['received_at'],schema)
                validator(data);validate_observation(self.con,oid,'VALID',None)
                return Observation(oid,url,r['received_at'],data)
        from contextlib import redirect_stdout
        from io import StringIO
        at=max(utc_time(r['received_at']) for r in fixture['responses'])
        with tempfile.TemporaryDirectory() as t,patch.object(select,'HttpClient',Client),patch.object(select,'now',return_value=at),redirect_stdout(StringIO()):
            root=Path(t)/'selection';select.select(root,proposals)
            result=load_json((root/'candidates.json').read_bytes())
            self.assertEqual(len(result['pairs']),2)
            for pair in result['pairs']:
                self.assertEqual(pair['classification'],'DISCOVERY')
                self.assertFalse(pair['operator_approved'])
                self.assertEqual(len(pair['sources']),4)
            with self.assertRaises(ValueError):select.select(Path(t)/'overscope',proposals*2)

    def test_unknown_control_schema_and_account_fields_are_redacted(self):
        for frame in [dict(type='ok',id='2'),dict(type='ok',msg=[]),
                      dict(type='ok',msg=dict(market_tickers=[12])),dict(type='ok',extra=True)]:
            self.assertEqual(ws_store.safe_frame(dumps(frame),allow_control=True)[2],'REDACTED')
