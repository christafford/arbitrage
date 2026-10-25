"""HYPOTHETICAL transport/recovery/signing tests; no exchange authentication."""
import base64
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from predarb import kalshi, ws_store
from predarb.book_store import inspect_book, load_book
from predarb.kalshi_auth import Credentials, WS_PATH, WS_URL, private_file
from predarb.kalshi_ws import capture, open_socket, refresh_metadata
from predarb.provider import Observation
from predarb.research import _latest
from predarb.store import connect, archive_response, validate_observation, start_run, update_run
from predarb.validation import dumps, utc_time
from test_orderbooks import sample

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, padding
    from cryptography.hazmat.primitives import serialization, hashes
    import websockets
    HAS_EXTRAS = True
except ImportError:
    HAS_EXTRAS = False


@unittest.skipUnless(HAS_EXTRAS, 'install .[kalshi-ws] for signing and transport tests')
class CredentialsTests(unittest.TestCase):
    def test_openssh_keys_sign_handshake_without_rewriting_credential_file(self):
        for key in (ed25519.Ed25519PrivateKey.generate(), rsa.generate_private_key(public_exponent=65537, key_size=2048)):
            with self.subTest(key=type(key).__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); private = root / 'private.pem'; config = root / 'credentials.json'
                body = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                         serialization.NoEncryption())
                private.write_bytes(body); private.chmod(0o600)
                config.write_text(json.dumps({'api_key_id': 'a952bcbe-ec3b-4b5b-b8f9-11dae589608c',
                                              'private_key_path': 'private.pem'})); config.chmod(0o600)
                headers = Credentials.load(config).headers(timestamp_ms=123456)
                signature = base64.b64decode(headers['KALSHI-ACCESS-SIGNATURE'])
                message = ('123456GET' + WS_PATH).encode()
                if isinstance(key, ed25519.Ed25519PrivateKey): key.public_key().verify(signature, message)
                else: key.public_key().verify(signature, message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
                self.assertEqual(private.read_bytes(), body)

    def test_encrypted_pem_corrupt_openssh_and_unsupported_keys_fail_without_content_leaks(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ed25519.Ed25519PrivateKey.generate()
        bodies = [key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.BestAvailableEncryption(b'HYPOTHETICAL-PASSWORD')),
                  b'-----BEGIN OPENSSH PRIVATE KEY-----\nHYPOTHETICAL-SECRET\n-----END OPENSSH PRIVATE KEY-----',
                  ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM,
                      serialization.PrivateFormat.OpenSSH, serialization.NoEncryption())]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); private = root / 'private.pem'; config = root / 'credentials.json'
            config.write_text(json.dumps({'api_key_id': 'a952bcbe-ec3b-4b5b-b8f9-11dae589608c',
                                          'private_key_path': 'private.pem'})); config.chmod(0o600)
            for body in bodies:
                private.write_bytes(body); private.chmod(0o600)
                with self.assertRaisesRegex(ValueError, '^invalid credential configuration, permissions or unsupported private key$'):
                    Credentials.load(config)

    def test_both_key_types_sign_only_fixed_handshake_and_never_repr_secrets(self):
        for key in (ed25519.Ed25519PrivateKey.generate(), rsa.generate_private_key(public_exponent=65537, key_size=2048)):
            with self.subTest(key=type(key).__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                private = root / 'private.pem'
                private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption())); private.chmod(0o600)
                config = root / 'credentials.json'
                config.write_text(json.dumps({'api_key_id': 'a952bcbe-ec3b-4b5b-b8f9-11dae589608c',
                                              'private_key_path': 'private.pem'})); config.chmod(0o600)
                credentials = Credentials.load(config)
                headers = credentials.headers(timestamp_ms=123456)
                self.assertNotIn(headers['KALSHI-ACCESS-KEY'], repr(credentials))
                message = ('123456GET' + WS_PATH).encode()
                signature = base64.b64decode(headers['KALSHI-ACCESS-SIGNATURE'])
                if isinstance(key, ed25519.Ed25519PrivateKey): key.public_key().verify(signature, message)
                else: key.public_key().verify(signature, message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
                private.chmod(0o644)
                with self.assertRaisesRegex(ValueError, 'configuration'): Credentials.load(config)

    def test_private_file_rejects_symlinks_checkouts_oversize_and_public_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root / 'key'; target.write_bytes(b'HYPOTHETICAL secret'); target.chmod(0o600)
            link = root / 'link'; link.symlink_to(target)
            with self.assertRaises(ValueError): private_file(link)
            target.write_bytes(b'x' * 65537)
            with self.assertRaises(ValueError): private_file(target)
            target.write_bytes(b'HYPOTHETICAL'); (root / '.git').mkdir()
            with self.assertRaisesRegex(ValueError, 'outside Git'): private_file(target)

    def test_redirects_are_refused_and_debug_logger_is_disabled(self):
        from websockets.sync.client import reconnect
        from websockets.exceptions import InvalidStatus
        from websockets.http11 import Response
        from websockets.datastructures import Headers
        captured = []
        def failure(connector, deadline):
            captured.append(connector)
            raise InvalidStatus(Response(302, 'Found', Headers({'Location': 'wss://example.invalid/'})))
        with patch.object(reconnect, 'open_connection', failure), self.assertRaises(InvalidStatus):
            open_socket({'KALSHI-ACCESS-KEY': 'HYPOTHETICAL_SECRET'})
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].uri, WS_URL)
        self.assertIsNone(captured[0].proxy)
        self.assertTrue(captured[0].logger.disabled)


class FakeCredentials:
    def headers(self):
        return {'KALSHI-ACCESS-KEY': 'HYPOTHETICAL_SECRET_KEY',
                'KALSHI-ACCESS-SIGNATURE': 'HYPOTHETICAL_SECRET_SIGNATURE', 'KALSHI-ACCESS-TIMESTAMP': '1'}


class FakeClock:
    def __init__(self, now): self.at, self.elapsed = now, 0
    def now(self): return self.at + timedelta(seconds=self.elapsed)
    def monotonic(self): return self.elapsed
    def sleep(self, seconds): self.elapsed += seconds


class Socket:
    def __init__(self, frames, clock): self.frames, self.clock, self.sent = list(frames), clock, []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def send(self, message): self.sent.append(loads(message))
    def recv(self, timeout):
        if not self.frames:
            self.clock.sleep(timeout); raise TimeoutError()
        self.clock.sleep(.001)
        item = self.frames.pop(0)
        if isinstance(item, BaseException): raise item
        return dumps(item)


def loads(value): return json.loads(value)


class StreamCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'archive.sqlite3')
        self.db = connect(self.path); self.addCleanup(self.db.close)
        self.case = sample(); self.source = self.case['kalshi_metadata']['ticker']
        self.protocol = loads((Path(__file__).parent / 'fixtures/m5a-ws-hypothetical.json').read_text())
        self.clock = FakeClock(utc_time(self.case['clock']))
        self.sockets = []

    def metadata(self, con, source):
        at = self.clock.now().isoformat()
        market = self.case['kalshi_metadata']
        run = start_run(con, 'kalshi', kalshi.SCHEMA_VERSION, {'filter': 'HYPOTHETICAL'})
        observed = archive_response(con, 'kalshi', kalshi.detail_url(source), dumps({'market': market}).encode(),
                                    200, {}, at, kalshi.SCHEMA_VERSION)
        validate_observation(con, observed, 'VALID', None)
        # Direct seed deliberately avoids presenting synthetic IDs to the live registry.
        con.execute("INSERT INTO catalogue_entries VALUES(?,?,?,?,?,?,?,'UNVERIFIED')",
                    (run, source, observed, at, dumps(market), '{}', hashlib.sha256(b'{}').hexdigest()))
        update_run(con, run, status='COMPLETE', pages=1, records=1, unique=1, next_page=None)
        return run, Observation(observed, kalshi.detail_url(source), at, {'market': market})

    def ack(self, sid=7):
        frame = deepcopy(self.protocol['acknowledgment']); frame['msg']['sid'] = sid
        return frame
    def snapshot(self, seq=10, sid=7):
        frame = deepcopy(self.case['kalshi_ws_snapshot']); frame.update(seq=seq, sid=sid)
        return frame
    def delta(self, seq=11, **changes):
        frame = self.snapshot(seq); frame['type'] = 'orderbook_delta'
        frame['msg'] = {'market_ticker': self.source, 'market_id': frame['msg']['market_id'],
                        'clock': 101, 'side': 'yes', 'price_dollars': '.42', 'delta_fp': '-.50'} | changes
        return frame

    def run_capture(self, *sequences, **kwargs):
        sockets = [Socket(sequence, self.clock) for sequence in sequences]; self.sockets.extend(sockets)
        def connector(headers): return sockets.pop(0)
        options = dict(seconds=15, max_connections=len(sequences), max_messages=100,
                       directory=self.tmp.name, connect_socket=connector, metadata_loader=self.metadata,
                       now=self.clock.now, monotonic=self.clock.monotonic, sleep=self.clock.sleep)
        options.update(kwargs)
        return capture(self.db, self.source, FakeCredentials(), **options)

    def test_snapshot_delta_archive_before_normalization_and_m3_m4_consumption(self):
        seen = []
        def inspect(con, observed, now):
            self.assertEqual(_latest(con, 'kalshi', self.source, now), observed)
            result = inspect_book(con, observed, now=now)
            self.assertTrue(result['data_usable']); self.assertEqual(result['transport'], 'KALSHI_AUTHENTICATED_WS')
            seen.append((observed, now, result))
        stats = self.run_capture([self.ack(), self.snapshot(), self.delta()], max_messages=3, on_book=inspect)
        self.assertEqual(stats['status'], 'CAPTURED'); self.assertEqual(len(seen), 2)
        self.assertEqual(seen[-1][2]['no_asks'][0]['quantity'], '1.00' if isinstance(seen[-1][2]['no_asks'][0]['quantity'], str) else 1)
        observed, at, result = seen[0]
        raw = self.db.execute('SELECT raw_body,source_ts FROM raw_observations WHERE id=?', (observed,)).fetchone()
        self.assertEqual(raw[0], dumps(self.snapshot()).encode())
        self.assertNotEqual(raw[1], at.isoformat())
        self.assertTrue(inspect_book(self.db, observed, now=at)['data_usable'])
        self.assertIn('STREAM_DISCONNECTED', inspect_book(self.db, seen[-1][0], now=self.clock.now())['rejections'])
        self.assertEqual(self.sockets[0].sent, [{'id': 1, 'cmd': 'subscribe', 'params': {
            'channels': ['orderbook_delta'], 'market_ticker': self.source, 'use_yes_price': False}}])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)

    def test_gap_invalidates_old_book_then_new_generation_snapshot_recovers(self):
        stats = self.run_capture([self.ack(), self.snapshot(), self.delta(12)],
                                 [self.ack(), self.snapshot(1), self.delta(2)], max_messages=6)
        self.assertEqual(stats['recoveries'], 1)
        self.assertEqual(stats['failures'], ['INVALID_STREAM_FRAME'])
        self.assertEqual(stats['status'], 'INCOMPLETE')
        rows = self.db.execute("SELECT id,validation_status FROM raw_observations WHERE schema_version=?", (ws_store.SCHEMA_VERSION,)).fetchall()
        self.assertEqual(rows[2][1], 'REJECTED')
        with self.assertRaises(ValueError): load_book(self.db, rows[2][0], now=self.clock.now())
        self.assertIn('STREAM_DISCONNECTED', inspect_book(self.db, rows[1][0], now=self.clock.now())['rejections'])

    def test_coordinator_tick_runs_during_quiet_backoff_and_preserves_capture_stats(self):
        ticks = []
        def stop(db, at):
            ticks.append(self.clock.monotonic())
            return self.clock.monotonic() >= 6
        result = self.run_capture([self.ack(), self.snapshot(), self.delta()],
                                  [self.ack(), self.snapshot(), self.delta()], on_tick=stop)
        self.assertIn('MESSAGE_TIMEOUT', result['failures'])
        self.assertIn('COORDINATOR_STOP', result['failures'])
        self.assertEqual(result['connections'], 1)
        self.assertTrue(result['live_continuity_demonstrated'])
        self.assertGreater(len(ticks), 10)

    def test_transport_disconnect_discards_old_generation_and_requires_snapshot(self):
        stats = self.run_capture([self.ack(), self.snapshot(), OSError('HYPOTHETICAL_SECRET_SIGNATURE')],
                                 [self.ack(), self.delta()], max_messages=4)
        self.assertEqual(stats['deltas'], 0)
        self.assertEqual(stats['failures'], ['CONNECTION_OR_PROCESSING_FAILED', 'INVALID_STREAM_FRAME'])
        self.assertNotIn('HYPOTHETICAL_SECRET', dumps(stats))

    def test_source_time_missing_stale_future_wrong_market_clock_or_bad_book(self):
        cases = []
        missing = self.snapshot(); del missing['sending_ts_ms']; cases.append(missing)
        stale = self.snapshot(); stale['sending_ts_ms'] -= 61000; cases.append(stale)
        future = self.snapshot(); future['sending_ts_ms'] += 6000; cases.append(future)
        wrong = self.snapshot(); wrong['msg']['market_ticker'] = 'HYPOTHETICAL-OTHER'; cases.append(wrong)
        crossed = self.snapshot(); crossed['msg']['yes_dollars_fp'] = [['.99','1']]; cases.append(crossed)
        for frame in cases:
            with self.subTest(frame=frame):
                stats = self.run_capture([self.ack(), frame], max_messages=2)
                self.assertEqual(stats['snapshots'], 0); self.assertFalse(stats['live_continuity_demonstrated'])

    def test_missing_protocol_fields_are_archived_with_precise_safe_failure_codes(self):
        for key,code in (('clock','MISSING_MARKET_CLOCK'),('sending_ts_ms','MISSING_SOURCE_TIMESTAMP')):
            with self.subTest(key=key):
                frame=self.snapshot()
                del (frame['msg'] if key=='clock' else frame)[key]
                stats=self.run_capture([self.ack(),frame],max_messages=2)
                self.assertEqual(stats['failures'],[code])
                self.assertEqual(stats['usable_books'],0)
                self.assertFalse(stats['live_continuity_demonstrated'])
                row=self.db.execute('SELECT raw_body,validation_status,validation_error FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone()
                self.assertEqual(row,(dumps(frame).encode(),'REJECTED',code))

    def test_real_missing_clock_snapshot_replays_through_capture_as_rejected(self):
        fixture=loads((Path(__file__).parent/'fixtures/kalshi-ws-missing-clock-live.json').read_text())
        self.assertIs(fixture['hypothetical'],False)
        self.case['kalshi_metadata']=loads(fixture['metadata']['body'])['market']
        self.source=self.case['kalshi_metadata']['ticker']
        self.clock=FakeClock(utc_time(fixture['frames'][1]['retrieved_at']))
        ack=loads(fixture['frames'][0]['body'])
        snapshot=loads(fixture['frames'][1]['body'])
        stats=self.run_capture([ack,snapshot],max_messages=2)
        self.assertEqual(stats['status'],'INCOMPLETE')
        self.assertEqual(stats['failures'],['MISSING_MARKET_CLOCK'])
        self.assertEqual(stats['snapshots'],0)
        self.assertEqual(stats['usable_books'],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM normalized_books').fetchone()[0],0)

    def test_real_fixture_hashes_sanitization_and_snapshot_delta_clock_rejections(self):
        from predarb.book_stream import KalshiBookStream, StreamProtocolError
        fixture=loads((Path(__file__).parent/'fixtures/kalshi-ws-missing-clock-live.json').read_text())
        metadata=loads(fixture['metadata']['body'])['market']
        for item in [fixture['metadata'],*fixture['frames']]:
            self.assertEqual(hashlib.sha256(item['body'].encode()).hexdigest(),item['sha256'])
        observed_types=set()
        for item in fixture['frames']:
            safe,wire,kind=ws_store.safe_frame(item['body'])
            self.assertEqual(kind,'EXACT_WIRE')
            self.assertEqual(safe,item['body'].encode())
            self.assertEqual(wire,item['wire_sha256'])
            frame=loads(item['body']);observed_types.add(frame['type'])
            if frame['type']=='subscribed':continue
            stream=KalshiBookStream(metadata['ticker'],metadata,
                                    metadata_received_at=fixture['metadata']['retrieved_at'])
            with self.assertRaises(StreamProtocolError) as caught:
                stream.apply(frame,received_at=item['retrieved_at'],now=utc_time(item['retrieved_at']),generation=stream.generation)
            self.assertEqual(caught.exception.code,'MISSING_MARKET_CLOCK')
            self.assertIsNone(stream.current)
        self.assertEqual(observed_types,{'subscribed','orderbook_snapshot','orderbook_delta'})

    def sequence_case(self):
        """Actual pre-rollout fixture; any mutations in fault tests are hypothetical."""
        fixture=loads((Path(__file__).parent/'fixtures/kalshi-ws-missing-clock-live.json').read_text())
        self.case['kalshi_metadata']=loads(fixture['metadata']['body'])['market']
        self.source=self.case['kalshi_metadata']['ticker']
        self.clock=FakeClock(utc_time(fixture['frames'][-1]['retrieved_at']))
        return [loads(item['body']) for item in fixture['frames']]

    def test_explicit_sequence_protocol_accepts_real_frames_and_replays_same_version(self):
        frames=self.sequence_case();seen=[]
        def inspect(con,observed,now):
            book=inspect_book(con,observed,now=now)
            self.assertTrue(book['data_usable'])
            self.assertEqual(book['continuity'],'SINGLE_SUBSCRIPTION_SEQUENCE_V1')
            seen.append((observed,now,book))
        stats=self.run_capture(frames,protocol='sequence-v1',max_messages=4,on_book=inspect)
        self.assertEqual(stats['status'],'CAPTURED')
        self.assertEqual(stats['sequenced_connection_ids'],[1])
        self.assertFalse(stats['reconnected_continuity_demonstrated'])
        self.assertEqual(stats['protocol'],'sequence-v1')
        schemas=self.db.execute('SELECT DISTINCT r.schema_version FROM raw_observations r JOIN ws_frames f ON f.observation_id=r.id').fetchall()
        self.assertEqual(schemas,[(ws_store.PROTOCOL_SCHEMAS['sequence-v1'],)])
        # Fake close shares the final frame's timestamp, so that last instant
        # correctly counts as disconnected. Earlier historical frames replay.
        for observed,at,expected in seen[:-1]:
            self.assertEqual(inspect_book(self.db,observed,now=at),expected)
        self.assertFalse(inspect_book(self.db,seen[-1][0],now=self.clock.now())['data_usable'])

    def test_sequence_protocol_preserves_gap_reconnect_and_no_cross_generation_merge(self):
        frames=self.sequence_case()
        # HYPOTHETICAL omission: drop seq 2, so the seq 3 delta must fail.
        stats=self.run_capture([frames[0],frames[1],frames[3]],frames,
                               protocol='sequence-v1',max_messages=7)
        self.assertEqual(stats['failures'],['INVALID_STREAM_FRAME'])
        self.assertEqual(stats['recoveries'],1)
        self.assertEqual(stats['sequenced_connection_ids'],[2])
        self.assertFalse(stats['reconnected_continuity_demonstrated'])
        self.assertEqual(stats['status'],'INCOMPLETE')
        # A successful resnapshot/reconnect needs a usable delta on both connections.
        with patch('predarb.ws_store.MAX_FRAMES',4):
            stats=self.run_capture(frames,frames,protocol='sequence-v1',max_messages=8)
        self.assertTrue(stats['reconnected_continuity_demonstrated'])
        self.assertEqual(stats['status'],'CAPTURED')

    def test_sequence_mode_never_relaxes_missing_time_identity_prices_or_clock_schema(self):
        frames=self.sequence_case()
        mutations=[('time',None),('clock',0),('clock',None),('market','HYPOTHETICAL-WRONG'),
                   ('price','2'),('quantity','-1'),('stale',None)]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                changed=deepcopy(frames[1])
                if key=='time':del changed['sending_ts_ms']
                elif key=='clock':changed['msg']['clock']=value
                elif key=='market':changed['msg']['market_ticker']=value
                elif key=='price':changed['msg']['yes_dollars_fp'][0][0]=value
                elif key=='quantity':changed['msg']['yes_dollars_fp'][0][1]=value
                else:changed['sending_ts_ms']-=61000
                stats=self.run_capture([frames[0],changed],protocol='sequence-v1',max_messages=2)
                self.assertEqual(stats['usable_books'],0)
                self.assertFalse(stats['live_continuity_demonstrated'])
                if key=='clock':self.assertEqual(stats['failures'],['UNEXPECTED_MARKET_CLOCK' if value is not None else 'INVALID_STREAM_FRAME'])
                if key=='time':self.assertEqual(stats['failures'],['MISSING_SOURCE_TIMESTAMP'])

    def test_sequence_mode_window_is_checked_before_network_during_capture_and_on_read(self):
        from predarb.book_stream import SEQUENCE_PROTOCOL_START,SEQUENCE_PROTOCOL_END
        frames=self.sequence_case();seen=[]
        self.run_capture(frames,protocol='sequence-v1',max_messages=4,
                         on_book=lambda con,observed,at:seen.append((observed,at)))
        with self.assertRaisesRegex(ValueError,'PROTOCOL_REVIEW_REQUIRED'):
            load_book(self.db,seen[-1][0],now=SEQUENCE_PROTOCOL_END)
        for stamp in (SEQUENCE_PROTOCOL_START-timedelta(seconds=1),SEQUENCE_PROTOCOL_END):
            self.clock=FakeClock(stamp)
            with self.assertRaisesRegex(ValueError,'PROTOCOL_REVIEW_REQUIRED'):
                self.run_capture(frames,protocol='sequence-v1')
        self.clock=FakeClock(SEQUENCE_PROTOCOL_END-timedelta(milliseconds=1))
        stats=self.run_capture(frames,protocol='sequence-v1',max_messages=4)
        self.assertEqual(stats['failures'],['PROTOCOL_REVIEW_REQUIRED'])
        self.assertEqual(stats['snapshots'],0)

    def test_stream_replay_rejects_mixed_or_unknown_protocol_schemas(self):
        frames=self.sequence_case();seen=[]
        self.run_capture(frames,protocol='sequence-v1',max_messages=4,
                         on_book=lambda con,observed,at:seen.append((observed,at)))
        for schema in (ws_store.SCHEMA_VERSION,'HYPOTHETICAL-UNKNOWN'):
            self.db.execute('UPDATE raw_observations SET schema_version=? WHERE id=?',(schema,seen[-1][0]));self.db.commit()
            with self.assertRaisesRegex(ValueError,'provenance'):load_book(self.db,seen[-1][0],now=seen[-1][1])
        with self.assertRaisesRegex(ValueError,'unknown'):
            self.run_capture(frames,protocol='HYPOTHETICAL-UNKNOWN')

    def test_partial_sequence_book_requires_liquidity_before_continuity_claim(self):
        frames=self.sequence_case()
        snapshot=deepcopy(frames[1]);snapshot['msg']['yes_dollars_fp']=[]
        delta=deepcopy(frames[3]);delta['seq']=2
        delta['msg'].update(side='yes',price_dollars='.01',delta_fp='1.00')
        stats=self.run_capture([frames[0],snapshot,delta],protocol='sequence-v1',max_messages=3)
        self.assertEqual(stats['usable_books'],1)
        self.assertTrue(stats['live_continuity_demonstrated'])

    def test_actual_multigeneration_sequence_fixture_replays_identically_with_provenance(self):
        from predarb.book_stream import KalshiBookStream
        fixture=loads((Path(__file__).parent/'fixtures/kalshi-ws-sequence-live.json').read_text())
        self.assertIs(fixture['hypothetical'],False)
        outputs=[]
        for attempt in range(2):
            results=[]
            with connect(str(Path(self.tmp.name)/f'live-replay-{attempt}.sqlite3')) as con:
                for generation in fixture['connections']:
                    meta=generation['metadata'];body=meta['body'].encode()
                    self.assertEqual(hashlib.sha256(body).hexdigest(),meta['sha256'])
                    run=start_run(con,'kalshi',kalshi.SCHEMA_VERSION,{'fixture_replay':True})
                    mid=archive_response(con,'kalshi',meta['endpoint'],body,200,{},meta['received_at'],meta['schema_version'])
                    data=loads(body);kalshi.validate_detail(data)
                    validate_observation(con,mid,'VALID',None)
                    source=data['market']['ticker']
                    con.execute("INSERT INTO catalogue_entries VALUES(?,?,?,?,?,?,?,'UNVERIFIED')",
                                (run,source,mid,meta['received_at'],dumps(data['market']),'{}',hashlib.sha256(b'{}').hexdigest()))
                    update_run(con,run,status='COMPLETE',pages=1,records=1,unique=1,next_page=None)
                    cid=ws_store.begin_connection(con,source,run,mid,at=generation['started_at'])
                    stream=KalshiBookStream(source,data['market'],metadata_received_at=meta['received_at'],protocol='sequence-v1')
                    stream.generation=cid
                    for item in generation['frames']:
                        raw=item['body'].encode()
                        self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
                        self.assertEqual(item['sha256'],item['wire_sha256'])
                        observed,safe,kind=ws_store.archive_frame(con,cid,raw,at=item['received_at'],protocol='sequence-v1')
                        self.assertEqual(safe,raw);self.assertEqual(kind,'EXACT_WIRE')
                        frame=loads(safe);at=utc_time(item['received_at'])
                        if frame['type']=='subscribed':
                            validate_observation(con,observed,'VALID',None);continue
                        book=stream.apply(frame,received_at=item['received_at'],now=at,generation=cid)
                        self.assertEqual(book.issues(now=at),())
                        self.assertIsNone(stream.clock);self.assertIsNone(stream.snapshot_clock)
                        ws_store.record_frame(con,observed,book,now=at)
                        results.append(dumps(book.as_dict(now=at)))
                    # Replay the complete generation independently from stored bytes.
                    replayed=inspect_book(con,observed,now=at)
                    self.assertTrue(replayed['data_usable'])
                    self.assertEqual(replayed['yes_asks'],book.as_dict(now=at)['yes_asks'])
                    self.assertEqual(replayed['no_asks'],book.as_dict(now=at)['no_asks'])
                    ws_store.end_connection(con,cid,at=generation['ended_at'],reason=generation['end_reason'])
                    self.assertIn('STREAM_DISCONNECTED',inspect_book(con,observed,now=utc_time(generation['ended_at']))['rejections'])
                self.assertEqual(con.execute('SELECT COUNT(*) FROM pairs').fetchone()[0],0)
            outputs.append(results)
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(len(outputs[0]),222)

    def test_clock_loss_after_valid_snapshot_invalidates_depth_until_new_connection(self):
        missing=self.delta();del missing['msg']['clock']
        stats=self.run_capture([self.ack(),self.snapshot(),missing],
                               [self.ack(),self.snapshot(1),self.delta(2)],max_messages=6)
        self.assertEqual(stats['failures'],['MISSING_MARKET_CLOCK'])
        self.assertEqual(stats['recoveries'],1)
        self.assertEqual(stats['status'],'INCOMPLETE')
        rejected=self.db.execute("SELECT id FROM raw_observations WHERE validation_error='MISSING_MARKET_CLOCK'").fetchone()[0]
        with self.assertRaises(ValueError):load_book(self.db,rejected,now=self.clock.now())

    def test_ack_missing_wrong_or_duplicate_cannot_enable_data(self):
        for sequence in ([self.snapshot()], [self.ack(8), self.snapshot()], [self.ack(), self.ack()]):
            with self.subTest(sequence=sequence):
                stats = self.run_capture(sequence, max_messages=len(sequence))
                self.assertEqual(stats['snapshots'], 0); self.assertIn('INVALID_STREAM_FRAME', stats['failures'])

    def test_partial_depth_preserves_sequence_until_liquidity_returns(self):
        snapshot = self.snapshot(); snapshot['msg']['yes_dollars_fp'] = []
        stats = self.run_capture([self.ack(), snapshot, self.delta(delta_fp='1.00')], max_messages=3)
        self.assertEqual(stats['usable_books'], 1); self.assertEqual(stats['deltas'], 1)

    def test_idle_timeout_and_dead_writer_liveness_fail_closed(self):
        stats = self.run_capture([self.ack(), self.snapshot()])
        self.assertIn('MESSAGE_TIMEOUT', stats['failures'])
        observed = self.db.execute('SELECT MAX(observation_id) FROM book_captures').fetchone()[0]
        self.db.execute('UPDATE ws_connections SET ended_at=NULL,end_reason=NULL'); self.db.commit()
        result = inspect_book(self.db, observed, now=self.clock.now())
        self.assertIn('STREAM_LIVENESS_NOT_DEMONSTRATED', result['rejections'])

    def test_hash_tampering_and_omitted_delta_are_detected_on_replay(self):
        seen = []
        self.run_capture([self.ack(), self.snapshot(), self.delta(), self.delta(12)], max_messages=4,
                         on_book=lambda con, observed, now: seen.append((observed, now)))
        observed, at = seen[-1]
        self.db.execute('DELETE FROM ws_frames WHERE observation_id=?', (seen[-2][0],)); self.db.commit()
        with self.assertRaisesRegex(ValueError, 'sequence gap'): load_book(self.db, observed, now=at)
        self.db.execute("UPDATE raw_observations SET body_sha256='bad' WHERE id=?", (seen[0][0],)); self.db.commit()
        with self.assertRaisesRegex(ValueError, 'provenance'): load_book(self.db, seen[0][0], now=seen[0][1])

    def test_privacy_screening_and_raw_hash_provenance(self):
        frame = self.delta(client_order_id='HYPOTHETICAL_PRIVATE_ACCOUNT_ID')
        raw = dumps(frame).encode(); safe, digest, kind = ws_store.safe_frame(raw)
        self.assertEqual(kind, 'ACCOUNT_FIELD_REMOVED'); self.assertNotIn(b'PRIVATE_ACCOUNT', safe)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        for body in (b'{"type":"error","msg":"HYPOTHETICAL_SECRET"}', b'not JSON HYPOTHETICAL_SECRET',
                     dumps(self.delta(market_id='HYPOTHETICAL_SECRET')).encode(), b'x' * 1000001,
                     dumps(self.delta(market_id='HYPOTHETICAL_SECRET')).replace('HYPOTHETICAL_SECRET',
                         ''.join('\\u%04x' % ord(c) for c in 'HYPOTHETICAL_SECRET')).encode()):
            safe, _, kind = ws_store.safe_frame(body, secrets=('HYPOTHETICAL_SECRET',))
            self.assertEqual(kind, 'REDACTED'); self.assertNotIn(b'HYPOTHETICAL_SECRET', safe)

    def test_interrupt_closes_generation_and_preserves_archived_frames(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_capture([self.ack(), self.snapshot(), KeyboardInterrupt()])
        self.assertEqual(self.db.execute('SELECT end_reason FROM ws_connections').fetchone()[0], 'SIGNAL_STOP')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ws_frames').fetchone()[0], 2)

    def test_low_space_stops_before_network_and_duration_budget_validation(self):
        with patch('predarb.kalshi_ws.shutil.disk_usage') as disk:
            disk.return_value.free = 0
            result = self.run_capture([])
            self.assertEqual(result['connections'], 0); self.assertEqual(result['failures'], ['LOW_DISK_SPACE'])
        for option in ({'seconds': 0}, {'max_messages': 0}, {'max_connections': 121}, {'min_free_bytes': 0}):
            with self.assertRaises(ValueError): self.run_capture([], **option)

    def test_clock_jump_during_receive_archives_but_rejects_frame(self):
        clock = self.clock
        def jumped(): return clock.now() + timedelta(seconds=10 if clock.elapsed else 0)
        stats = self.run_capture([self.ack()], now=jumped, max_messages=1)
        self.assertEqual(stats['failures'], ['INVALID_STREAM_FRAME'])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM raw_observations WHERE validation_status='REJECTED'").fetchone()[0], 1)

    def test_migration_from_six_preserves_all_existing_rows(self):
        self.metadata(self.db, self.source)
        self.db.execute('DROP TABLE ws_frames'); self.db.execute('DROP TABLE ws_connections')
        self.db.execute('PRAGMA user_version=6'); self.db.commit()
        old = self.db.execute('SELECT * FROM raw_observations').fetchall()
        with connect(self.path) as migrated:
            self.assertEqual(migrated.execute('PRAGMA user_version').fetchone()[0], 7)
            self.assertEqual(migrated.execute('SELECT * FROM raw_observations').fetchall(), old)
            self.assertEqual(migrated.execute('SELECT COUNT(*) FROM ws_connections').fetchone()[0], 0)

    def test_periodic_frame_budget_obtains_new_generation_snapshot(self):
        with patch('predarb.ws_store.MAX_FRAMES', 3):
            stats = self.run_capture([self.ack(), self.snapshot(), self.delta()],
                                     [self.ack(), self.snapshot(1), self.delta(2)], max_messages=6)
        self.assertEqual(stats['connections'], 2); self.assertEqual(stats['snapshots'], 2)
        self.assertEqual(stats['failures'], [])
        self.assertEqual(self.db.execute('SELECT end_reason FROM ws_connections ORDER BY id').fetchall(),
                         [('PERIODIC_RESNAPSHOT',), ('BUDGET_COMPLETE',)])

    def test_rejected_frame_persists_barrier_without_secret_echo(self):
        stats = self.run_capture([self.ack(), self.snapshot(), self.delta(market_id='HYPOTHETICAL_SECRET_KEY')],
                                 max_messages=3)
        self.assertEqual(stats['failures'], ['INVALID_STREAM_FRAME'])
        observed = _latest(self.db, 'kalshi', self.source, self.clock.now())
        with self.assertRaises(ValueError): load_book(self.db, observed, now=self.clock.now())
        rows = self.db.execute('SELECT raw_body,validation_error FROM raw_observations').fetchall()
        self.assertNotIn('HYPOTHETICAL_SECRET_KEY', repr(rows))

    def test_wall_clock_jump_after_processing_invalidates_connection(self):
        base = self.clock.at
        def jump(con, observed, at): self.clock.at += timedelta(seconds=10)
        stats = self.run_capture([self.ack(), self.snapshot()], max_messages=2, on_book=jump)
        self.assertEqual(stats['failures'], ['WALL_CLOCK_JUMP'])
        observed = _latest(self.db, 'kalshi', self.source, self.clock.now())
        self.assertFalse(inspect_book(self.db, observed, now=self.clock.now())['data_usable'])
        self.clock.at = base

    def test_metadata_refresh_archives_real_fixture_and_rejects_changed_identity(self):
        from helpers import real_response, Replay, payload
        from predarb.provider import HttpClient
        market = payload('kalshi-market-live')['market']
        client = HttpClient(self.db, 'kalshi', opener=Replay(real_response('kalshi-market-live')),
                            utc_now=lambda: self.clock.now().isoformat())
        run, detail = refresh_metadata(self.db, market['ticker'], client=client)
        self.assertEqual(detail.data['market']['ticker'], market['ticker'])
        self.assertEqual(self.db.execute('SELECT status FROM collection_runs WHERE id=?', (run,)).fetchone()[0], 'COMPLETE')
        client = HttpClient(self.db, 'kalshi', opener=Replay(real_response('kalshi-market-live')))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            refresh_metadata(self.db, 'WRONG-TICKER', client=client)
        self.assertEqual(self.db.execute('SELECT status FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()[0], 'FAILED')

    def test_cli_existing_live_research_session_callback_and_hypothetical_refusal(self):
        from predarb import ws_cli
        from predarb.research import start_session
        from contextlib import redirect_stdout
        from io import StringIO
        config = {'max_contracts': '1', 'kalshi_budget': '0', 'polymarket_us_budget': '0',
                  'reserve_per_leg': '.01', 'min_profit': '.01'}
        session_id = start_session(self.db, config, now=self.clock.now(), interval_seconds=1)
        args = SimpleNamespace(db=self.path, ticker=self.source, credentials_file='HYPOTHETICAL',
                               seconds=1, max_messages=3, max_connections=1, min_free_mb=1024,
                               research_session=session_id, protocol='clocked')
        def fake_capture(con, source, credentials, **options):
            options['on_book'](con, 0, self.clock.now())
            return {'status': 'INCOMPLETE', 'hypothetical_test': True}
        with patch.object(ws_cli.Credentials, 'load', return_value=FakeCredentials()), \
                patch.object(ws_cli, 'capture', side_effect=fake_capture), redirect_stdout(StringIO()):
            self.assertEqual(ws_cli.run(args), 2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_cycles').fetchone()[0], 1)
        with patch.object(ws_cli.Credentials, 'load', return_value=FakeCredentials()), \
                patch('predarb.research.session', return_value={'mode': 'HYPOTHETICAL_REPLAY'}):
            with self.assertRaisesRegex(ValueError, 'hypothetical'): ws_cli.run(args)
