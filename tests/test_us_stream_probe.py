"""Hypothetical protocol/security tests; no settlement or live-fill assertions."""
import base64
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import websockets
    HAS_EXTRAS=True
except ImportError:
    HAS_EXTRAS=False
from predarb import us_stream_probe as p
from predarb.validation import dumps, utc_time

AT='2026-11-01T16:00:00+00:00'
SLUG='hypothetical-market'
def frame():
    return {'requestId':'m5n-market-data','subscriptionType':'SUBSCRIPTION_TYPE_MARKET_DATA',
            'marketData':{'marketSlug':SLUG,'transactTime':AT,'state':'MARKET_STATE_OPEN',
                          'bids':[{'px':{'value':'0.4','currency':'USD'},'qty':'10'}],
                          'offers':[{'px':{'value':'0.6','currency':'USD'},'qty':'5'}]}}


@unittest.skipUnless(HAS_EXTRAS, 'install .[market-data-ws] for signing/transport tests')
class CredentialsTests(unittest.TestCase):
    def test_protected_formats_and_fixed_signature(self):
        key=Ed25519PrivateKey.generate();seed=key.private_bytes_raw()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'credentials';path.touch(mode=0o600)
            for name in ['POLYMARKET_API_SECRET_KEY','POLYMARKET_API_SECDRET_KEY']:
                for raw in [seed,seed+key.public_key().public_bytes_raw()]:
                    path.write_text('POLYMARKET_API_KEY_ID=00000000-0000-4000-8000-000000000001\n'+name+'='+base64.b64encode(raw).decode()+'\n')
                    c=p.Credentials.load(path);h=c.headers(123)
                    key.public_key().verify(base64.b64decode(h['X-PM-Signature']),b'123GET/v1/ws/markets')
                    self.assertNotIn(base64.b64encode(seed).decode(),repr(c))
            path.chmod(0o644)
            with self.assertRaises(ValueError): p.Credentials.load(path)

    def test_invalid_missing_duplicate_and_mismatched_keys_fail_without_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'credentials';path.touch(mode=0o600)
            prefix='POLYMARKET_API_KEY_ID=00000000-0000-4000-8000-000000000001\n'
            for body in ['HYPOTHETICAL_SECRET',prefix,prefix+prefix,
                         prefix+'POLYMARKET_API_SECRET_KEY=HYPOTHETICAL_SECRET',
                         prefix+'POLYMARKET_API_SECRET_KEY='+base64.b64encode(bytes(64)).decode()]:
                path.write_text(body)
                with self.assertRaises(ValueError) as exc: p.Credentials.load(path)
                self.assertNotIn('HYPOTHETICAL_SECRET',str(exc.exception))

    def test_fixed_origin_proxy_logging_and_redirect_rejection(self):
        seen={}
        class Connector:
            def __init__(self,*args,**kwargs):seen.update(url=args[0],**kwargs)
            def connect(self):return self
        with patch('websockets.sync.client.reconnect',Connector):
            result=p.open_socket({'HYPOTHETICAL':'not-a-real-key'})
        exc=ValueError('hypothetical redirect')
        self.assertIs(result.process_redirect(exc),exc)
        self.assertEqual(seen['url'],p.URL);self.assertIsNone(seen['proxy'])
        self.assertTrue(seen['logger'].disabled)


class FrameTests(unittest.TestCase):
    def test_genuine_sanitized_frames_replay_source_age_and_depth_transitions(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/us-stream-live.json').read_text())
        self.assertEqual(fixture['kind'],'GENUINE_PUBLIC_MARKET_DATA')
        previous={}
        for row in fixture['records']:
            raw=row['raw_body'].encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['wire_sha256'])
            self.assertTrue(p.safe_frame(raw)[2])
            saved=row['original_assessment'];slug=saved['market']
            actual=p.assess(raw,[slug],row['retrieved_at'],previous.get(slug))
            for key in actual:self.assertEqual(actual[key],saved[key])
            previous[slug]=actual
        self.assertEqual(len(previous),2)

    def test_crossed_locked_unsorted_and_nonobject_frames_fail_closed(self):
        for price in ['0.4','0.3']:
            f=frame();f['marketData']['offers'][0]['px']['value']=price
            self.assertIn('CROSSED_OR_LOCKED_BOOK',p.assess(dumps(f),[SLUG],AT)['rejections'])
        f=frame();f['marketData']['bids'].append({'px':{'value':'0.5','currency':'USD'},'qty':'1'})
        self.assertIn('UNSORTED_BOOK',p.assess(dumps(f),[SLUG],AT)['rejections'])
        for raw in ['null','[]','1']:
            with self.assertRaises(ValueError):p.assess(raw,[SLUG],AT)

    def test_quiet_and_missing_markets_do_not_inherit_freshness(self):
        row=p.assess(dumps(frame()),[SLUG],AT)
        row.update(received_at=AT,receive_monotonic=100)
        end=(utc_time(AT)+timedelta(seconds=30)).isoformat()
        result=p.summarize([row],[SLUG,'missing'],end)
        self.assertEqual(result['missing_markets'],['missing'])
        self.assertEqual(result['markets'][SLUG]['last_source_age_at_finish_seconds'],30)
        self.assertEqual(result['markets']['missing']['source_age_seconds'],None)
        self.assertFalse(result['markets'][SLUG]['economic_eligibility'])

    def test_exact_wire_and_documented_stats(self):
        f=frame();f['marketData']['stats']={'openPx':{'value':'0.5','currency':'USD'},
            'notionalTraded':{'value':'45','currency':'USD'},'lastTradeQty':'2',
            'openSetTime':AT,'lastPriceSample':{'longPx':{'value':'0.4','currency':'USD'},
            'shortPx':{'value':'0.6','currency':'USD'},'ts':AT}}
        raw=dumps(f).encode();safe,digest,ok=p.safe_frame(raw)
        self.assertTrue(ok);self.assertEqual(safe,raw);self.assertEqual(digest,hashlib.sha256(raw).hexdigest())
        r=p.assess(raw,[SLUG],AT);self.assertTrue(r['timestamp_depth_diagnostic_pass'])
        self.assertFalse(r['economic_eligibility']);self.assertEqual(r['sequence_continuity'],'UNKNOWN')

    def test_unknown_private_error_malformed_and_secret_echo_redacted(self):
        cases=[b'{',dumps({'error':'HYPOTHETICAL_SECRET'}),dumps({'account':'private'})]
        f=frame();f['marketData']['userId']='private';cases.append(dumps(f))
        f=frame();f['marketData']['stats']={'lastPriceSample':{'account':'private'}};cases.append(dumps(f))
        for raw in cases:
            safe,_,ok=p.safe_frame(raw,('HYPOTHETICAL_SECRET',));self.assertFalse(ok)
            self.assertNotIn(b'private',safe);self.assertNotIn(b'HYPOTHETICAL_SECRET',safe)
        f=frame();f['requestId']='HYPOTHETICAL_SECRET'
        self.assertFalse(p.safe_frame(dumps(f).replace('HYPOTHETICAL','\\u0048YPOTHETICAL'),('HYPOTHETICAL_SECRET',))[2])

    def test_missing_invalid_and_wrong_identity_rejected(self):
        variants=[]
        for key in ['transactTime','bids','offers','state']:
            f=frame();del f['marketData'][key];variants.append(f)
        for price in ['-0.1','1','NaN']:
            f=frame();f['marketData']['offers'][0]['px']['value']=price;variants.append(f)
        f=frame();f['marketData']['bids'][0]['qty']='0';variants.append(f)
        f=frame();f['marketData']['marketSlug']='wrong';variants.append(f)
        f=frame();f['subscriptionType']='SUBSCRIPTION_TYPE_TRADE';variants.append(f)
        for f in variants:
            with self.assertRaises(ValueError):p.assess(dumps(f),[SLUG],AT)

    def test_stale_future_partial_closed_regression_and_repeated_depth(self):
        raw=dumps(frame());first=p.assess(raw,[SLUG],AT)
        r=p.assess(raw,[SLUG],(utc_time(AT)+timedelta(seconds=3)).isoformat(),first)
        self.assertIn('SOURCE_AGE_GT_2S',r['rejections']);self.assertFalse(r['changed_from_previous'])
        self.assertIn('FUTURE_SOURCE',p.assess(raw,[SLUG],(utc_time(AT)-timedelta(seconds=1)).isoformat())['rejections'])
        future=dict(first,source_ts=(utc_time(AT)+timedelta(seconds=1)).isoformat())
        self.assertIn('SOURCE_REGRESSION',p.assess(raw,[SLUG],AT,future)['rejections'])
        f=frame();f['marketData']['bids']=[];f['marketData']['state']='MARKET_STATE_HALTED'
        r=p.assess(dumps(f),[SLUG],AT)
        self.assertEqual(r['rejections'],['MARKET_NOT_OPEN','PARTIAL_OR_EMPTY_BOOK'])
        self.assertEqual(p.assess(b'{"heartbeat":{}}',[SLUG],AT),{'kind':'heartbeat'})

    def test_subscription_only_market_data_and_bounded(self):
        self.assertEqual(p.subscription([SLUG])['subscribe']['subscriptionType'],'SUBSCRIPTION_TYPE_MARKET_DATA')
        for slugs in [[],[SLUG,SLUG],['a','b','c']]:
            with self.assertRaises(ValueError):p.subscription(slugs)


class CaptureTests(unittest.TestCase):
    def run_capture(self,body):
        class Cred:
            def headers(self):return {}
            def sensitive_values(self,h):return ()
        class Socket:
            closed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def send(self,msg):self.sent=load=json.loads(msg)
            def recv(self,timeout):
                if not hasattr(self,'done'):self.done=True;return body
                raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as tmp:
            s=Socket();root=Path(tmp)/'capture'
            r=p.capture(root,Cred(),[SLUG],seconds=1,connect_socket=lambda h:s)
            rows=[json.loads(x) for x in (root/'timing.jsonl').read_text().splitlines()]
            archived=(root/'000001.json').read_bytes()
            self.assertTrue(s.closed)
            self.assertEqual(p.replay(root)['verified_frames'],1)
            with self.assertRaises(FileExistsError):p.capture(root,Cred(),[SLUG],seconds=1,connect_socket=lambda h:s)
            return r,rows,archived

    def test_archive_before_schema_failure(self):
        f=frame();del f['marketData']['transactTime'];raw=dumps(f).encode()
        r,rows,archived=self.run_capture(raw)
        self.assertEqual(archived,raw);self.assertEqual(r['reason'],'INVALID_FRAME')
        self.assertEqual(rows[0]['rejection'],'INVALID_FRAME')

    def test_quality_callback_follows_raw_and_timing_archival(self):
        cred=SimpleNamespace(headers=lambda:{},sensitive_values=lambda h:())
        class Socket:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def send(self,msg):pass
            def recv(self,timeout):return '{"heartbeat":{}}'
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'MAX_FRAMES',1):
            root=Path(tmp)/'capture';seen=[]
            def event(row):
                self.assertTrue((root/row['raw_file']).exists())
                self.assertEqual(len((root/'timing.jsonl').read_text().splitlines()),1)
                seen.append(row['kind'])
            p.capture(root,cred,[SLUG],seconds=1,connect_socket=lambda h:Socket(),on_event=event)
            self.assertEqual(seen,['heartbeat'])

    def test_valid_capture_interrupt_and_privacy_failure(self):
        r,rows,_=self.run_capture(dumps(frame()))
        self.assertEqual(r['books'],1);self.assertEqual(r['reason'],'INTERRUPTED')
        self.assertFalse(rows[0]['economic_eligibility'])
        r,_,raw=self.run_capture('{"account":"HYPOTHETICAL_PRIVATE"}')
        self.assertEqual(r['reason'],'UNSAFE_OR_UNKNOWN_FRAME');self.assertNotIn(b'HYPOTHETICAL_PRIVATE',raw)

    def test_bounds_no_data_resources_and_safe_transport_errors(self):
        cred=SimpleNamespace(headers=lambda:{},sensitive_values=lambda h:())
        class Socket:
            latency=.01
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def send(self,msg):pass
            def recv(self,timeout):return '{"heartbeat":{}}'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for seconds in [0,601,True]:
                with self.assertRaises(ValueError):p.capture(root/'bad',cred,[SLUG],seconds=seconds)
            self.assertFalse((root/'bad').exists())
            with patch.object(p.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                r=p.capture(root/'disk',cred,[SLUG],connect_socket=lambda h:self.fail('must not connect'))
            self.assertEqual(r['reason'],'LOW_DISK');self.assertFalse(r['capture_complete'])
            with patch.object(p,'MAX_FRAMES',2):
                r=p.capture(root/'frames',cred,[SLUG],connect_socket=lambda h:Socket())
            self.assertEqual(r['reason'],'FRAME_LIMIT');self.assertEqual(r['heartbeats'],2)
            self.assertEqual(r['missing_markets'],[SLUG]);self.assertFalse(r['capture_complete'])
            self.assertEqual(r['last_pong_rtt_seconds'],.01)
            with patch.object(p,'MAX_BYTES',999999):
                r=p.capture(root/'bytes',cred,[SLUG],connect_socket=lambda h:Socket())
            self.assertEqual(r['reason'],'BYTE_LIMIT')
            stop=threading.Event();stop.set()
            r=p.capture(root/'stop',cred,[SLUG],stop=stop,connect_socket=lambda h:Socket())
            self.assertEqual(r['reason'],'INTERRUPTED')
            def failure(h):raise RuntimeError('HYPOTHETICAL_SECRET')
            r=p.capture(root/'error',cred,[SLUG],connect_socket=failure)
            self.assertEqual(r['reason'],'CAPTURE_ERROR')
            self.assertNotIn('HYPOTHETICAL_SECRET',(root/'error'/'results.json').read_text())

    def test_deadline_success_timeout_missing_market_and_replay_tampering(self):
        cred=SimpleNamespace(headers=lambda:{},sensitive_values=lambda h:())
        class Socket:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def send(self,msg):pass
            def recv(self,timeout):
                f=frame();f['marketData']['transactTime']=p.datetime.now(p.timezone.utc).isoformat()
                return dumps(f)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            # All clocks are hypothetical; 1s budget, then stop after one frame.
            with patch.object(p.time,'monotonic',side_effect=[0,.1,.1,.1,.1,.1,.2,1.1,1.1]):
                result=p.capture(root/'good',cred,[SLUG],seconds=1,connect_socket=lambda h:Socket())
            self.assertTrue(result['capture_complete']);self.assertEqual(result['frames'],1)
            self.assertEqual(p.replay(root/'good')['replayed_assessments'],1)
            raw=root/'good'/'000001.json';original=raw.read_bytes();raw.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'hash'):p.replay(root/'good')
            raw.write_bytes(original)
            timing=root/'good'/'timing.jsonl';row=json.loads(timing.read_text())
            row['source_age_seconds']=999;timing.write_text(json.dumps(row)+'\n')
            with self.assertRaisesRegex(ValueError,'assessment'):p.replay(root/'good')
            class Quiet(Socket):
                def recv(self,timeout):raise TimeoutError()
            with patch.object(p.time,'monotonic',side_effect=[0,.1,.1,.1,.1,.1,1.1,1.1]):
                result=p.capture(root/'quiet',cred,[SLUG],seconds=1,connect_socket=lambda h:Quiet())
            self.assertEqual(result['reason'],'BUDGET_COMPLETE');self.assertFalse(result['capture_complete'])
            self.assertEqual(p.replay(root/'quiet')['verified_frames'],0)

    def test_clock_jump_and_handshake_deadline(self):
        cred=SimpleNamespace(headers=lambda:{},sensitive_values=lambda h:())
        class Socket:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def send(self,msg):pass
            def recv(self,timeout):raise AssertionError('no receive expected')
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(p.time,'monotonic',side_effect=[0,2,2,2,2]):
                result=p.capture(Path(tmp)/'handshake',cred,[SLUG],seconds=1,connect_socket=lambda h:Socket())
            self.assertEqual(result['reason'],'DEADLINE_DURING_HANDSHAKE')
            with patch.object(p.time,'monotonic',side_effect=[0,.1,.1,2,2,2]):
                result=p.capture(Path(tmp)/'clock',cred,[SLUG],seconds=10,connect_socket=lambda h:Socket())
            self.assertEqual(result['reason'],'WALL_CLOCK_JUMP')

    def test_multiframe_replay_preserves_float_timing_and_rejects_false_completion(self):
        cred=SimpleNamespace(headers=lambda:{},sensitive_values=lambda h:())
        class Socket:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def send(self,msg):pass
            def recv(self,timeout):return dumps(frame())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'capture'
            with patch.object(p,'MAX_FRAMES',2):
                result=p.capture(root,cred,[SLUG],seconds=1,connect_socket=lambda h:Socket())
            self.assertEqual(p.replay(root)['replayed_assessments'],2)
            result['capture_complete']=True
            (root/'results.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'completion'):p.replay(root)


class CommandTests(unittest.TestCase):
    def test_cli_exit_codes_offline_replay_and_signal_handlers_restored(self):
        import importlib.util
        import signal
        spec=importlib.util.spec_from_file_location('m5n_cli',Path(__file__).parents[1]/'scripts/m5n_us_stream.py')
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        handlers={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
        with patch.object(cli.Credentials,'load',return_value=object()),patch('builtins.print'):
            for complete,code in [(True,0),(False,2)]:
                with patch.object(cli,'capture',return_value={'capture_complete':complete}):
                    self.assertEqual(cli.main(['--output','unused','--credentials','unused','--slug',SLUG]),code)
                self.assertEqual({sig:signal.getsignal(sig) for sig in handlers},handlers)
            with patch.object(cli,'replay',return_value={'verified_frames':1}) as replay:
                self.assertEqual(cli.main(['--replay','hypothetical-archive']),0)
                replay.assert_called_once_with('hypothetical-archive')
