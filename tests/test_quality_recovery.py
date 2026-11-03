"""M5P hypothetical clock/lifecycle faults and genuine historical replay evidence."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
import tempfile
import hashlib
import unittest
from unittest.mock import patch

from test_continuous_research import hypothetical
from predarb import quality_capture as capture
from predarb.quality_recovery import tally, primary_reason, verify_raw
from predarb.models import AskLevel
from predarb.validation import dumps,load_json
from predarb.store import connect,archive_response


class ForensicTests(unittest.TestCase):
    def test_primary_and_simultaneous_reasons_reconcile(self):
        rows=[{'quality':{'timestamp_depth_overlap':False,'rejections':[
            'kalshi:DISCONNECTED','polymarket_us:SOURCE_NOT_WITHIN_2S','SOURCE_SKEW_GT_2S']}},
            {'quality':{'timestamp_depth_overlap':True,'rejections':[]}},
            {'status':'POLL_OR_BOOK_ERROR','rejections':['ValueError:missing']}]
        r=tally(rows)
        self.assertEqual(sum(r['primary'].values()),3)
        self.assertEqual(r['unassessed_after_processing_error'],1)
        self.assertEqual(r['additional']['polymarket_us:SOURCE_NOT_WITHIN_2S'],1)
        self.assertEqual(r['venue_failed_samples']['polymarket_us'],1)
        self.assertEqual(r['valid_samples'],1)
        self.assertEqual(primary_reason(rows[0]),'kalshi:DISCONNECTED')
        with self.assertRaises(ValueError):tally([{'quality':{'timestamp_depth_overlap':True,'rejections':['INVALID']}}])

    def test_raw_integrity_is_readonly_and_tampering_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'hypothetical.sqlite3'
            with connect(str(p)) as c:
                oid=archive_response(c,'kalshi','https://external-api.kalshi.com/hypothetical',b'{"hypothetical":true}',200,{},'2026-11-03T00:00:00Z','HYPOTHETICAL')
            before=p.read_bytes();self.assertEqual(verify_raw(p),1);self.assertEqual(before,p.read_bytes())
            with connect(str(p)) as c:c.execute('UPDATE raw_observations SET raw_body=? WHERE id=?',(b'{}',oid));c.commit()
            with self.assertRaisesRegex(ValueError,'hash'):verify_raw(p)


class IntervalTests(unittest.TestCase):
    def setUp(self):
        self.data,self.at,self.books,self.pair=hypothetical()
        self.engine=capture.Engine(self.pair,self.at.isoformat(),(self.at+timedelta(seconds=10)).isoformat())

    def event(self,channel,second,kind='book',book=None,**extra):
        event=dict(kind=kind,channel=channel,at=(self.at+timedelta(seconds=second)).isoformat(),
                   snapshot=True,generation=1,**extra)
        self.engine.event(event,book if book is not None else self.books[0 if channel=='kalshi' else 1] if kind=='book' else None)

    def test_wall_time_expires_at_two_seconds_not_poll_interval(self):
        self.event('kalshi',0);self.event('us_ws',0)
        self.assertTrue(self.engine.assess('us_ws',self.at+timedelta(seconds=2))['quality']['timestamp_depth_overlap'])
        r=self.engine.finish()
        self.assertEqual(r['valid_local_market_state_seconds']['us_ws'],D(2))
        self.assertEqual(r['valid_local_market_state_percent']['us_ws'],D(20))
        self.assertIn('UNKNOWN',r['continuous_exchange_validity'])

    def test_sampling_frequency_cannot_change_coverage(self):
        self.event('kalshi',0);self.event('us_ws',0)
        for i in range(100):self.engine.assess('us_ws',self.at+timedelta(seconds=i/10))
        self.assertEqual(self.engine.finish()['valid_local_market_state_seconds']['us_ws'],D(2))

    def test_pending_and_disconnect_gaps_and_new_generation(self):
        self.event('kalshi',0);self.event('us_ws',0)
        self.event('kalshi',.5,'pending')
        self.event('kalshi',.75)
        self.event('us_ws',1,'disconnect',reason='SOCKET_CLOSED')
        self.assertEqual(self.engine.finish()['valid_local_market_state_seconds']['us_ws'],D('.75'))

    def test_heartbeat_never_refreshes_stale_or_disconnected_book(self):
        self.event('kalshi',0);self.event('us_ws',0)
        self.event('us_ws',1,'disconnect',reason='SOCKET_CLOSED')
        self.event('us_ws',1.5,'heartbeat',received_at=(self.at+timedelta(seconds=1.5)).isoformat())
        self.assertFalse(self.engine.assess('us_ws',self.at+timedelta(seconds=1.5))['quality']['timestamp_depth_overlap'])
        self.assertEqual(self.engine.finish()['valid_local_market_state_seconds']['us_ws'],D(1))
        self.assertEqual(self.engine.states['us_ws'].local_receipt_at,self.books[1].received_at)

    def test_partial_missing_stale_invalid_prices_and_clock_fail_closed(self):
        for bad in [replace(self.books[1],rejections=('PARTIAL_BOOK',)),
                    replace(self.books[1],source_ts=None),
                    replace(self.books[1],source_ts=(self.at-timedelta(seconds=3)).isoformat()),
                    replace(self.books[1],rejections=('INVALID_BOOK:off-grid',)),
                    replace(self.books[1],metadata_received_at=(self.at-timedelta(seconds=61)).isoformat())]:
            self.setUp();self.event('kalshi',0);self.event('us_ws',0,book=bad)
            self.assertEqual(self.engine.finish()['valid_local_market_state_seconds']['us_ws'],0)
        self.setUp();self.event('kalshi',0);self.event('us_ws',0)
        self.engine.event(dict(kind='clock',at=self.at.isoformat(),synchronized=False))
        self.assertEqual(self.engine.finish()['valid_local_market_state_seconds']['us_ws'],0)

    def test_future_time_never_gains_coverage_silently(self):
        self.event('kalshi',0)
        self.event('us_ws',0,book=replace(self.books[1],source_ts=(self.at+timedelta(seconds=5)).isoformat()))
        self.assertEqual(self.engine.finish()['valid_local_market_state_seconds']['us_ws'],0)

    def test_availability_startup_gap_and_market_close_are_in_denominator(self):
        self.event('kalshi',1,book=replace(self.books[0],market_close_at=(self.at+timedelta(seconds=1.5)).isoformat()))
        self.event('us_ws',1)
        r=self.engine.finish()
        self.assertEqual(r['planned_wall_seconds'],10)
        self.assertEqual(r['valid_local_market_state_seconds']['us_ws'],D('.5'))

    def test_future_source_lower_boundary_is_split_exactly(self):
        stamp=(self.at+timedelta(seconds=1)).isoformat()
        self.event('kalshi',0,book=replace(self.books[0],source_ts=stamp))
        self.event('us_ws',0,book=replace(self.books[1],source_ts=stamp))
        # Existing comparison rejects negative source age until t=1, then
        # receipt-age expires at t=2. Never credit the whole t=0..2 interval.
        self.assertEqual(self.engine.finish()['valid_local_market_state_seconds']['us_ws'],D(1))

    def test_source_versions_only_downgrade_conditional_economics(self):
        self.event('kalshi',0);self.event('us_ws',0,source_changed=True)
        r=self.engine.assess('us_ws',self.at,economics=True)
        self.assertEqual(r['classification'],'DISCOVERY');self.assertEqual(r['capital_cases'],[])
        self.assertFalse(r['strict_arbitrage_eligible'])

    def test_observed_mutation_snapshot_activity_and_loss_are_distinct(self):
        self.event('kalshi',0)
        s=self.engine.states['kalshi'];self.assertIsNone(s.last_mutation_observed_at)
        b=replace(self.books[0],no_asks=(AskLevel(D('.41'),D(10)),),received_at=(self.at+timedelta(seconds=1)).isoformat())
        self.event('kalshi',1,book=b)
        self.assertEqual(s.last_mutation_observed_at,b.received_at)
        self.event('kalshi',1.5,'disconnect',reason='TEST')
        self.assertIsNotNone(s.last_continuity_loss_at)
        self.assertNotEqual(s.last_continuity_loss_at,s.last_verified_snapshot_at)

    def test_invalid_grid_does_not_advance_verified_snapshot_or_activity_clock(self):
        self.event('us_ws',0);state=self.engine.states['us_ws']
        before=state.last_verified_snapshot_at;activity=state.last_authenticated_validated_activity_at
        b=replace(self.books[1],rejections=('INVALID_BOOK: off-grid price',),
                  received_at=(self.at+timedelta(seconds=1)).isoformat())
        self.event('us_ws',1,book=b)
        self.assertEqual(state.last_verified_snapshot_at,before)
        self.assertEqual(state.last_authenticated_validated_activity_at,activity)
        self.assertNotEqual(state.local_receipt_at,activity)
        self.assertIsNotNone(state.last_continuity_loss_at)

    def test_regression_and_unknown_schema_rejected(self):
        self.event('kalshi',1)
        with self.assertRaisesRegex(ValueError,'regressed'):self.event('us_ws',0)
        with self.assertRaisesRegex(ValueError,'unknown'):self.event('us_ws',2,'unexpected')

    def test_fixed_scope_and_no_full_day_or_duplicate_instruments(self):
        pairs=[self.pair,dict(self.pair,id='other',kalshi_id='K2',polymarket_us_id='U2')]
        capture.validate_window(900,pairs)
        for duration in [True,0,901,86400]:
            with self.assertRaises(ValueError):capture.validate_window(duration,pairs)
        with self.assertRaises(ValueError):capture.validate_window(900,[self.pair])
        with self.assertRaises(ValueError):capture.validate_window(900,[self.pair,self.pair])
        config=dict(schema=capture.VERSION,seconds=900,pairs=pairs,started_at=self.at.isoformat(),
                    deadline_at=(self.at+timedelta(seconds=900)).isoformat())
        capture.validate_config(config)
        with self.assertRaisesRegex(ValueError,'schema'):capture.validate_config(dict(config,schema='unknown'))
        with self.assertRaisesRegex(ValueError,'deadline'):
            capture.validate_config(dict(config,deadline_at=(self.at+timedelta(hours=24)).isoformat()))

    def test_journal_records_event_frontiers_and_sample_clocks(self):
        with tempfile.TemporaryDirectory() as t,patch.object(capture,'now',return_value=self.at):
            config=dict(started_at=self.at.isoformat(),deadline_at=(self.at+timedelta(seconds=10)).isoformat())
            j=capture.Journal(Path(t),self.pair,config)
            j.event(dict(kind='book',channel='kalshi',snapshot=True),self.books[0])
            j.event(dict(kind='book',channel='us_ws',snapshot=True),self.books[1]);j.sample()
            rows=list(capture.json_lines(Path(t)/'samples.jsonl'))
            self.assertEqual(rows[0]['event_number'],2)
            self.assertTrue(rows[0]['quality']['timestamp_depth_overlap'])
            self.assertFalse(rows[0]['trading_authorized'])
            for e in capture.json_lines(Path(t)/'events.jsonl'):
                digest=e.pop('sha256')
                self.assertEqual(hashlib.sha256(dumps(e).encode()).hexdigest(),digest)

    def test_rest_book_failure_does_not_discard_valid_stream_metadata(self):
        with tempfile.TemporaryDirectory() as t,patch.object(capture,'now',return_value=self.at):
            config=dict(started_at=self.at.isoformat(),deadline_at=(self.at+timedelta(seconds=10)).isoformat())
            j=capture.Journal(Path(t),self.pair,config);metadata=object();j.latest_metadata=metadata
            j.event(dict(kind='book',channel='kalshi',snapshot=True),self.books[0])
            j.event(dict(kind='book',channel='us_ws',snapshot=True),self.books[1])
            capture.rest_failure(j,metadata_confirmed=True)
            self.assertIs(j.latest_metadata,metadata)
            self.assertTrue(j.engine.assess('us_ws',self.at)['quality']['timestamp_depth_overlap'])
            self.assertFalse(j.engine.assess('us_rest',self.at)['quality']['timestamp_depth_overlap'])
            capture.rest_failure(j,metadata_confirmed=False)
            self.assertIsNone(j.latest_metadata)
            self.assertFalse(j.engine.assess('us_ws',self.at)['quality']['timestamp_depth_overlap'])


class GenuineFixtures(unittest.TestCase):
    def read(self,name):return load_json((Path(__file__).parent/'fixtures'/name).read_bytes())

    def payload(self,r):
        self.assertEqual(hashlib.sha256(r['raw_body'].encode()).hexdigest(),r['body_sha256'])
        return load_json(r['raw_body'])

    def test_brooklyn_positive_and_neighbors_reconstructed_from_original_frames(self):
        from predarb.book_stream import KalshiBookStream
        from predarb.orderbooks import normalize_rest
        from predarb.conditional_research import quote_cases
        from predarb.validation import utc_time
        f=self.read('m5p-brooklyn-live.json');self.assertIs(f['hypothetical'],False)
        for c in f['cases']:
            meta=c['kalshi_metadata'];stream=KalshiBookStream(f['pair']['kalshi_id'],self.payload(meta)['market'],metadata_received_at=meta['ts_utc'])
            for r in c['frames']:
                frame=self.payload(r)
                if frame['type']=='subscribed':continue
                b=stream.apply(frame,received_at=r['ts_utc'],now=utc_time(r['ts_utc']),generation=stream.generation)
            u=normalize_rest('polymarket_us',f['pair']['polymarket_us_id'],self.payload(c['us_book']),self.payload(c['us_metadata'])['market'],
                received_at=c['us_book']['ts_utc'],metadata_received_at=c['us_metadata']['ts_utc'],now=utc_time(c['at']))
            result=quote_cases([b,u],f['pair'],now=utc_time(c['at']),inspected=[b.as_dict(now=utc_time(c['at'])),u.as_dict(now=utc_time(c['at']))])
            self.assertEqual(load_json(dumps(load_json(dumps(result['quality'])))),c['expected']['quality'])
            self.assertEqual(load_json(dumps(result['capital_cases'])),c['expected']['capital_cases'])
        self.assertEqual(f['cases'][1]['expected']['quality']['rejections'],[])
        self.assertTrue(f['cases'][0]['expected']['quality']['rejections'])
        self.assertTrue(f['cases'][2]['expected']['quality']['rejections'])

    def test_toronto_fifth_stop_counterfactual_does_not_upgrade_original_rejection(self):
        from predarb.book_stream import KalshiBookStream
        from predarb.validation import utc_time
        f=self.read('m5p-toronto-live.json');self.assertIs(f['hypothetical'],False)
        m=self.payload(f['metadata']);frame=self.payload(f['frame']);at=utc_time(f['frame']['ts_utc'])
        s=KalshiBookStream(m['market']['ticker'],m['market'],metadata_received_at=f['metadata']['ts_utc'])
        b=s.apply(frame,received_at=f['frame']['ts_utc'],now=at,generation=s.generation)
        self.assertIn('PARTIAL_BOOK',b.issues(now=at))
        self.assertEqual(f['frame']['validation_status'],'REJECTED')

    def test_selected_open_definitions_grids_and_depth_keep_exact_hashes(self):
        from predarb import kalshi,polymarket_us
        f=self.read('m5p-selection-live.json');self.assertIs(f['hypothetical'],False)
        self.assertEqual(len(f['responses']),8)
        for r in f['responses']:
            self.assertEqual(hashlib.sha256(r['body'].encode()).hexdigest(),r['sha256'])
            adapter=kalshi if r['venue']=='kalshi' else polymarket_us
            data=load_json(r['body'])
            (adapter.validate_book if r['endpoint'].endswith(('/book','/orderbook')) else adapter.validate_detail)(data)


class GenuineEventReplay(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.fixture=load_json((Path(__file__).parent/'fixtures'/getattr(self,'fixture_name','m5p-event-replay-live.json')).read_bytes())
        self.assertIs(self.fixture['hypothetical'],False)
        for name,item in self.fixture['files'].items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
            raw=item['body'].encode();self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256']);p.write_bytes(raw)
        for name,tables in self.fixture['databases'].items():
            with connect(str(self.root/name)) as c:
                for table in ('collection_runs','raw_observations','catalogue_entries','book_captures','ws_connections','ws_frames','normalized_books'):
                    for r in tables[table]:
                        if 'raw_body' in r:r['raw_body']=r['raw_body'].encode()
                        cols=list(r)
                        c.execute('INSERT INTO '+table+' ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',list(r.values()))
                c.commit()

    def replay(self):return capture.replay(self.root,self.fixture['pair'],self.fixture['config'])

    def test_all_raw_frames_event_clocks_samples_and_intervals_replay(self):
        r=self.replay()
        expected=load_json(self.fixture['files']['audit.json']['body'])
        for key in ('events','samples','raw_hashes_verified','us_frames_verified'):
            self.assertEqual(r[key],expected[key])
        self.assertTrue(r['interval_coverage_recomputed'])

    def test_missing_event_cannot_inflate_coverage(self):
        p=self.root/'events.jsonl';lines=p.read_text().splitlines();p.write_text('\n'.join(lines[:5]+lines[6:])+'\n')
        with self.assertRaisesRegex(ValueError,'integrity'):self.replay()

    def test_modified_raw_frame_never_passes_hash_audit(self):
        with connect(str(self.root/'kalshi.sqlite3')) as c:
            c.execute("UPDATE raw_observations SET raw_body=? WHERE id=(SELECT min(observation_id) FROM ws_frames)",(b'{}',));c.commit()
        with self.assertRaisesRegex(ValueError,'provenance'):self.replay()

    def test_false_coverage_and_unfinished_stream_rejected(self):
        p=self.root/'result.json';r=load_json(p.read_bytes())
        r['valid_local_market_state_seconds']['us_ws']='900';p.write_text(dumps(r))
        with self.assertRaisesRegex(ValueError,'coverage'):self.replay()
        p.write_text(self.fixture['files']['result.json']['body'])
        with connect(str(self.root/'kalshi.sqlite3')) as c:c.execute('UPDATE ws_connections SET ended_at=NULL');c.commit()
        with self.assertRaisesRegex(ValueError,'unfinished'):self.replay()

    def test_sample_cannot_look_ahead_or_survive_missing_raw_us_frame(self):
        p=self.root/'samples.jsonl';rows=list(capture.json_lines(p));rows[0]['at']=self.fixture['config']['deadline_at']
        p.write_text(''.join(dumps(r)+'\n' for r in rows))
        with self.assertRaisesRegex(ValueError,'visibility'):self.replay()
        p.write_text(self.fixture['files']['samples.jsonl']['body'])
        next(self.root.glob('us-stream-*/*.json')).unlink()
        with self.assertRaises((FileNotFoundError,ValueError)):self.replay()


if __name__=='__main__':unittest.main()
