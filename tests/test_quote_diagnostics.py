"""Hypothetical diagnostics cases; no market equivalence or live-fill assertions."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from predarb.quote_diagnostics import Changes, Diagnostics, MeasuredClient, ObservedSocket, compare, summarize
from predarb.validation import utc_time
import test_soak


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.at = utc_time('2026-11-01T00:00:00Z')
        self.books = {v:dict(source_ts=self.at.isoformat(),received_at=self.at.isoformat(),
                            data_usable=True,rejections=[]) for v in ('kalshi','polymarket_us')}

    def test_exact_two_second_boundary(self):
        self.books['polymarket_us']['source_ts']=(self.at-timedelta(seconds=2)).isoformat()
        self.assertTrue(compare(self.books,self.at)['strict_observation_valid'])
        self.books['polymarket_us']['source_ts']=(self.at-timedelta(seconds=2,microseconds=1)).isoformat()
        r=compare(self.books,self.at)
        self.assertFalse(r['strict_observation_valid']);self.assertIn('SOURCE_SKEW_GT_2S',r['strict_rejections'])

    def test_old_transaction_recent_response_is_experimental_only(self):
        self.books['polymarket_us'].update(source_ts=(self.at-timedelta(seconds=70)).isoformat(),
                                          data_usable=False,rejections=['STALE_SOURCE'])
        before=deepcopy(self.books);r=compare(self.books,self.at)
        self.assertTrue(r['experimental_response_only_pass']);self.assertFalse(r['strict_observation_valid'])
        self.assertFalse(r['economic_eligibility']);self.assertEqual(r['continuous_us_book_validity'],'UNVERIFIED')
        self.assertEqual(before,self.books)

    def test_missing_invalid_partial_closed_disconnected_and_future_reject(self):
        self.assertFalse(compare({},self.at)['experimental_response_only_pass'])
        for reason in ('INVALID_BOOK: invalid price','PARTIAL_BOOK','STREAM_DISCONNECTED','FUTURE_SOURCE','MARKET_CLOSED_AT_EVALUATION'):
            with self.subTest(reason=reason):
                b=deepcopy(self.books);b['kalshi'].update(data_usable=False,rejections=[reason])
                r=compare(b,self.at);self.assertFalse(r['strict_observation_valid']);self.assertFalse(r['experimental_response_only_pass'])
        b=deepcopy(self.books);b['polymarket_us']['source_ts']=None
        self.assertIn('SOURCE_SKEW_UNKNOWN',compare(b,self.at)['experimental_rejections'])
        b=deepcopy(self.books);b['polymarket_us']['received_at']=(self.at+timedelta(seconds=1)).isoformat()
        self.assertFalse(compare(b,self.at)['experimental_response_only_pass'])

    def test_change_time_left_censoring_repetition_and_reconnect(self):
        c=Changes();b={'yes_asks':[{'price':'0.40','quantity':'10'}],'no_asks':[{'price':'0.65','quantity':'5'}]}
        first=c.observe('kalshi',b,100,1);self.assertIsNone(first['last_observed_change_monotonic'])
        repeat=c.observe('kalshi',b,110,1);self.assertEqual(repeat['observed_unchanged_seconds'],10)
        self.assertFalse(repeat['continuous_unchanged_claim'])
        b['yes_asks'][0]['quantity']='9';changed=c.observe('kalshi',b,120,1)
        self.assertTrue(changed['changed_from_previous_observation']);self.assertEqual(changed['last_observed_change_monotonic'],120)
        reset=c.observe('kalshi',b,130,2);self.assertIsNone(reset['changed_from_previous_observation'])
        self.assertTrue(reset['change_time_left_censored'])

    def test_pong_measurement_is_upper_bound_and_does_not_modify_stream(self):
        import threading
        class Socket:
            def __enter__(self):return self
            def ping(self):e=threading.Event();e.set();return e
            def recv(self,**kw):raise TimeoutError()
            def __exit__(self,*args):pass
        rows=[]
        with ObservedSocket(Socket(),rows.append,lambda:10) as s:
            with self.assertRaises(TimeoutError):s.recv(timeout=.5)
        self.assertEqual([r['kind'] for r in rows],['ws_connected','ws_pong_observed','ws_disconnecting'])

    def test_ping_or_journal_failure_always_closes_socket(self):
        import threading
        class Socket:
            closed=False
            fail_ping=False
            def __enter__(self):return self
            def ping(self):
                if self.fail_ping:raise OSError('HYPOTHETICAL ping failure')
                return threading.Event()
            def __exit__(self,*args):self.closed=True
        s=Socket();s.fail_ping=True
        with self.assertRaises(OSError):
            with ObservedSocket(s,lambda r:None):pass
        self.assertTrue(s.closed)
        def failed_journal(row):
            if row['kind']=='ws_disconnecting':raise OSError('HYPOTHETICAL disk failure')
        s=Socket()
        with self.assertRaises(OSError):
            with ObservedSocket(s,failed_journal):pass
        self.assertTrue(s.closed)


class DiagnosticIntegration(test_soak.SoakTests):
    # Inherit meaningful runner/fault tests; wrappers exercise telemetry on every path.
    def run_soak(self,name='run',**kwargs):
        d=Diagnostics(self.root/(name+'.jsonl'),self.config,monotonic=self.clock.monotonic)
        original_client=self.client
        def factory(con,venue,**kw):
            base=original_client(con,venue,**kw)
            return MeasuredClient(con,venue,emit=d.emit,timeout=base.timeout,attempts=1,interval=base.interval,
                                  opener=base.opener,sleep=self.clock.sleep,monotonic=self.clock.monotonic,
                                  utc_now=lambda:self.clock.now().isoformat())
        original_stream=self.stream
        def stream(con,source,credentials,**opts):
            tick=opts['on_tick']
            def sampled(db,at):
                result=tick(db,at);d.sample(db,self.clock.now());return result
            opts['on_tick']=sampled;opts['on_receive']=d.emit
            opts['on_book']=lambda db,observed,at:d.sample(db,at)
            return original_stream(con,source,credentials,**opts)
        options=dict(client_factory=factory,capture_fn=stream);options.update(kwargs)
        try:result=super().run_soak(name,**options)
        finally:d.close()
        summary=summarize(d.path)
        self.assertFalse(summary['economic_eligibility'])
        for line in d.path.read_text().splitlines():
            row=json.loads(line)
            if row['kind']=='http_request' and row.get('http_status')==200:
                self.assertIsNotNone(row['observation_id']);self.assertIsNotNone(row['body_sha256'])
        return result


class PacketEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        import m5m_review_packets
        cls.packet=m5m_review_packets

    def test_genuine_definitions_hash_schema_identity_and_window_conflict(self):
        import hashlib
        from predarb import kalshi,polymarket_us
        from predarb.validation import load_json
        data=json.loads((Path(__file__).parent/'fixtures/m5m-public-definitions.json').read_text())
        self.assertFalse(data['hypothetical']);self.assertEqual(len(data['responses']),10)
        markets={}
        for row in data['responses']:
            self.assertEqual(hashlib.sha256(row['body'].encode()).hexdigest(),row['sha256'])
            a=kalshi if row['venue']=='kalshi' else polymarket_us
            payload=load_json(row['body']);a.validate_detail(payload)
            self.assertEqual(payload['market'][a.ID_FIELD],row['source_id'])
            markets[row['source_id']]=payload['market']
        self.assertIn('March 23, 2026',markets['KXAAAGASMIN-26DEC31-3.20']['rules_secondary'])
        self.assertIn('September 9, 2026',markets['aaagaspc-usgas-low-2026-12-31-lt3pt20']['description'])

    def test_document_hash_staleness_missing_and_text_tamper(self):
        import hashlib
        from datetime import datetime,timezone
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.pdf';t=p.with_suffix('.txt')
            p.write_bytes(b'HYPOTHETICAL source bytes');t.write_bytes(b'HYPOTHETICAL extraction')
            at=datetime.now(timezone.utc)
            row=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                     text_sha256=hashlib.sha256(t.read_bytes()).hexdigest(),retrieved_at=at.isoformat())
            self.assertEqual(self.packet.verified_document(row,at)[0],p.read_bytes())
            with self.assertRaises(ValueError):self.packet.verified_document(row,at+timedelta(days=2))
            with self.assertRaises(ValueError):self.packet.verified_document(row,at-timedelta(seconds=1))
            t.write_bytes(b'HYPOTHETICAL tamper')
            with self.assertRaises(ValueError):self.packet.verified_document(row,at)
            p.unlink()
            with self.assertRaises(FileNotFoundError):self.packet.verified_document(row,at)

    def test_definition_replay_stale_missing_schema_and_corruption(self):
        from predarb import kalshi
        from predarb.store import connect,archive_response,validate_observation
        row=next(r for r in json.loads((Path(__file__).parent/'fixtures/m5m-public-definitions.json').read_text())['responses'] if r['venue']=='kalshi')
        at=utc_time(row['retrieved_at'])
        with tempfile.TemporaryDirectory() as tmp:
            with connect(str(Path(tmp)/'test.sqlite3')) as con:
                with self.assertRaises(ValueError):self.packet.definition(con,kalshi,row['source_id'],at)
                oid=archive_response(con,'kalshi',row['source_url'],row['body'].encode(),200,{},row['retrieved_at'],row['schema_version'])
                validate_observation(con,oid,'VALID',None)
                self.assertEqual(self.packet.definition(con,kalshi,row['source_id'],at)['sha256'],row['sha256'])
                with self.assertRaises(ValueError):self.packet.definition(con,kalshi,row['source_id'],at+timedelta(days=2))
                con.execute("UPDATE raw_observations SET body_sha256='HYPOTHETICAL_CORRUPTION' WHERE id=?",(oid,));con.commit()
                with self.assertRaises(ValueError):self.packet.definition(con,kalshi,row['source_id'],at)

    def test_incomplete_preparation_cannot_create_forms(self):
        from predarb.validation import dumps
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'forms'
            (root/'manifest.json').write_text(dumps({'schema':'m5m-review-preparation/v1','candidates':[]}))
            with self.assertRaises(ValueError):self.packet.build(root,[],out)
            self.assertFalse(out.exists())

    def test_running_capture_is_not_hour_acceptance(self):
        import m5m_analyze
        from predarb.validation import dumps
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'capture').mkdir()
            (root/'capture/status.json').write_text(dumps({'status':'RUNNING','stop_reason':None}))
            with self.assertRaises(ValueError):m5m_analyze.analyze(root)

    def test_preparation_exports_five_blank_forms_and_cannot_approve(self):
        """HYPOTHETICAL document/fee inputs over genuine definition replay."""
        import hashlib
        from datetime import datetime
        from predarb import kalshi,polymarket_us as us
        from predarb.store import connect,archive_response,validate_observation,save_entry,start_run,update_run
        from predarb.provider import Observation
        from predarb.validation import load_json,dumps
        from m5m_packets import CANDIDATES
        fixture=json.loads((Path(__file__).parent/'fixtures/m5m-public-definitions.json').read_text())
        at=max(utc_time(r['retrieved_at']) for r in fixture['responses'])+timedelta(seconds=1)
        class Frozen(datetime):
            @classmethod
            def now(cls,tz=None):return at
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();docs=[];manifest=[]
            with connect(str(source/'research.sqlite3')) as con:
                for r in fixture['responses']:
                    a=kalshi if r['venue']=='kalshi' else us;data=load_json(r['body']);m=data['market']
                    run=start_run(con,a.VENUE,a.SCHEMA_VERSION,{'hypothetical_replay':True})
                    oid=archive_response(con,a.VENUE,r['source_url'],r['body'].encode(),200,{},r['retrieved_at'],a.SCHEMA_VERSION)
                    validate_observation(con,oid,'VALID',None)
                    save_entry(con,run,Observation(oid,r['source_url'],r['retrieved_at'],data),r['source_id'],m,a.rules(m),m.get(a.TIME_FIELD))
                    update_run(con,run,status='COMPLETE',pages=1,records=1,unique=1,next_page=None)
            for name in ('kalshi-cpi','us-cpi','kalshi-gas','us-gas','us-rulebook'):
                p=root/(name+'.pdf');p.write_bytes(b'HYPOTHETICAL document, no legal effect');p.with_suffix('.txt').write_bytes(b'HYPOTHETICAL extraction, no legal effect')
                host='assets.kalshi.com' if name.startswith('kalshi') else 'www.polymarketexchange.com'
                docs.append(dict(path=str(p),url='https://'+host+'/HYPOTHETICAL.pdf',status=200,
                                 sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                 text_sha256=hashlib.sha256(p.with_suffix('.txt').read_bytes()).hexdigest(),retrieved_at=at.isoformat()))
            captures={}
            for i,(name,k,u,event) in enumerate(CANDIDATES):
                manifest.append(dict(name=name,kalshi_collection={'status':'COMPLETE'},polymarket_us_collection={'status':'COMPLETE'},kalshi_fee_capture_id=2*i+1,polymarket_us_fee_capture_id=2*i+2))
                captures[2*i+1]={'draft':{'source_id':k,'side':'NO'},'hypothetical_test':True}
                captures[2*i+2]={'draft':{'source_id':u,'side':'YES'},'hypothetical_test':True}
            (source/'manifest.json').write_text(dumps({'schema':'m5m-review-preparation/v1','candidates':manifest}))
            with patch.object(self.packet,'datetime',Frozen),patch.object(self.packet.fee_capture,'review',side_effect=lambda con,i,now:captures[i]),patch.object(self.packet.registry,'approve',side_effect=AssertionError('approval forbidden')):
                packets=self.packet.build(source,docs,root/'out')
            self.assertEqual(len(packets),5)
            for p in packets:
                self.assertFalse(p['strict_arbitrage_eligible']);self.assertIsNone(p['human_decision'])
                self.assertTrue(all(x['net_edge_usd'] is None for x in p['capital_cases']))
            for path in (root/'out').glob('*-human-review.json'):
                f=json.loads(path.read_text());self.assertFalse(f['human_reviewed']);self.assertEqual(f['reviewer'],'')
            with connect(str(source/'research.sqlite3')) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM pairs WHERE status='UNVERIFIED'").fetchone()[0],5)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM fee_profiles').fetchone()[0],0)

    def test_genuine_clocked_frames_and_cached_old_us_quotes(self):
        import hashlib
        from predarb import kalshi,polymarket_us as us
        from predarb.book_stream import KalshiBookStream
        from predarb.collector import book_freshness
        from predarb.validation import load_json
        fixture=json.loads((Path(__file__).parent/'fixtures/m5m-timing-live.json').read_text())
        self.assertFalse(fixture['hypothetical'])
        rows=fixture['responses'];meta=next(r for r in rows if r['venue']=='kalshi' and not r.get('ws'))
        market=load_json(meta['body']);kalshi.validate_detail(market)
        stream=KalshiBookStream(market['market']['ticker'],market['market'],metadata_received_at=meta['ts_utc'])
        frames=[r for r in rows if r.get('ws')];stream.generation=frames[0]['ws']['connection_id'];deltas=0
        for r in rows:
            self.assertEqual(hashlib.sha256(r['body'].encode()).hexdigest(),r['body_sha256'])
            self.assertEqual(r['timing']['observation_id'],r['id'])
        for r in frames:
            frame=load_json(r['body'])
            if frame['type']=='subscribed':continue
            book=stream.apply(frame,received_at=r['ts_utc'],now=utc_time(r['ts_utc']),generation=stream.generation)
            self.assertFalse(book.issues(now=utc_time(r['ts_utc'])))
            deltas+=frame['type']=='orderbook_delta'
        self.assertGreater(deltas,0)
        for r in rows:
            if r['venue']!='polymarket_us':continue
            body=load_json(r['body']);us.validate_book(body)
            self.assertEqual(book_freshness(body['marketData']['transactTime'],r['ts_utc'],now=utc_time(r['ts_utc'])),'STALE_SOURCE')
            self.assertEqual(r['timing']['cache_control'],'public, max-age=30')
