"""HYPOTHETICAL coordinated runner, fault and replay tests. No live calls."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from predarb import soak
from predarb.backups import verify
from predarb.kalshi_ws import capture
from predarb.store import connect
from predarb.validation import dumps, utc_time
from helpers import Response, Replay, fixture
from test_orderbooks import sample
from test_kalshi_ws import FakeClock, FakeCredentials, Socket


class SoakTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case = sample()
        self.clock = FakeClock(utc_time(self.case['clock']))
        self.config = fixture('soak-hypothetical')['config']
        self.config.update(kalshi_ticker=self.case['kalshi_metadata']['ticker'],
                           us_slug=self.case['polymarket_us_metadata']['slug'])
        self.calls = []
        self.us_faults = []
        # Synthetic IDs must never enter the real-instrument registry. Keep its
        # rejection intact; these tests exercise capture/storage, not approval.
        registry = patch('predarb.registry.observe_catalogue')
        registry.start(); self.addCleanup(registry.stop)

    def client(self, con, venue, **kwargs):
        owner = self
        class Opener:
            def open(self, request, timeout):
                owner.calls.append((venue, request.full_url, owner.clock.monotonic()))
                if request.full_url.endswith('/book'):
                    if owner.us_faults:
                        response = owner.us_faults.pop(0)
                        if isinstance(response, BaseException): raise response
                        return response
                    data = deepcopy(owner.case['polymarket_us_rest'])
                    data['marketData']['transactTime'] = owner.clock.now().isoformat()
                else:
                    data = {'market': deepcopy(owner.case[venue + '_metadata'])}
                return Response(dumps(data).encode())
        return soak.SoakClient(con, venue, **kwargs, opener=Opener(), sleep=self.clock.sleep,
                               monotonic=self.clock.monotonic, utc_now=lambda: self.clock.now().isoformat())

    def stream(self, con, ticker, credentials, **kwargs):
        def connector(headers):
            snap = deepcopy(self.case['kalshi_ws_snapshot'])
            snap['sending_ts_ms'] = int(self.clock.now().timestamp() * 1000)
            ack = {'id': 1, 'type': 'subscribed', 'msg': {'channel': 'orderbook_delta', 'sid': snap['sid']}}
            delta = deepcopy(snap); delta.update(type='orderbook_delta', seq=snap['seq'] + 1)
            delta['msg'] = {'market_ticker': ticker, 'market_id': snap['msg']['market_id'],
                            'clock': snap['msg']['clock'] + 1, 'side': 'yes',
                            'price_dollars': '.42', 'delta_fp': '.50'}
            return Socket([ack, snap, delta], self.clock)
        return capture(con, ticker, credentials, connect_socket=connector, **kwargs)

    def run_soak(self, name='run', **kwargs):
        options = dict(now=self.clock.now, monotonic=self.clock.monotonic, sleep=self.clock.sleep,
                       capture_fn=self.stream, client_factory=self.client,
                       sync_probe=lambda: {'synchronized': True, 'hypothetical': True})
        options.update(kwargs)
        return soak.run(self.root / name, self.config, FakeCredentials(), **options)

    def test_coordinated_capture_reconnect_backups_and_raw_replay(self):
        result = self.run_soak()
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertGreaterEqual(result['elapsed_seconds'], 20)
        self.assertEqual(result['coverage_assessment'], 'OBSERVATIONS_RECORDED')
        self.assertGreater(result['counts']['us_polls_complete'], 1)
        self.assertGreater(result['counts']['kalshi_connections'], 1)
        self.assertGreater(result['counts']['kalshi_deltas'], 0)
        self.assertGreater(result['failures']['MESSAGE_TIMEOUT'], 0)
        self.assertEqual(len(result['backups']), 2)
        for saved in result['backups']: self.assertTrue(verify(saved['destination'])['verified'])
        self.assertFalse(result['latest_sample']['books']['kalshi']['data_usable'])
        with connect(str(self.root / 'run/capture.sqlite3')) as con:
            for body, sha in con.execute('SELECT raw_body,body_sha256 FROM raw_observations'):
                self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM research_sessions').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM fee_profiles').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM ws_connections WHERE ended_at IS NULL').fetchone()[0], 0)
            row = con.execute("SELECT observation_id FROM book_captures WHERE freshness='FRESH' AND source_id=? LIMIT 1",
                              (self.config['us_slug'],)).fetchone()
            at = con.execute('SELECT ts_utc FROM raw_observations WHERE id=?', row).fetchone()[0]
            replay = soak.inspect_book(con, row[0], now=utc_time(at))
            self.assertTrue(replay['data_usable'])
        self.assertNotIn('HYPOTHETICAL_SECRET', (self.root / 'run/status.json').read_text())

    def test_http_failure_recovers_without_losing_raw_error(self):
        self.us_faults = [Response(b'{"hypothetical":"unavailable"}', 503, {'Content-Type': 'application/json'})]
        result = self.run_soak()
        self.assertEqual(result['counts']['us_poll_failures'], 1)
        self.assertGreater(result['counts']['us_polls_complete'], 0)
        with connect(str(self.root / 'run/capture.sqlite3')) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM raw_observations WHERE validation_status='HTTP_ERROR'").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM collection_runs WHERE status='FAILED'").fetchone()[0], 1)

    def test_retry_after_prevents_new_us_requests_until_cooldown(self):
        self.us_faults = [Response(b'{}', 429, {'Content-Type': 'application/json', 'Retry-After': '100'})]
        result = self.run_soak()
        self.assertEqual(result['counts']['us_poll_attempts'], 1)
        self.assertEqual(sum(v == 'polymarket_us' for v, _, _ in self.calls), 2)
        self.assertEqual(result['coverage_assessment'], 'INSUFFICIENT_USABLE_DATA')

    def test_kalshi_client_cooldown_survives_separate_reconnect_attempts(self):
        with connect(str(self.root / 'cooldown.sqlite3')) as con:
            replay = Replay(Response(b'{}', 429, {'Content-Type': 'application/json', 'Retry-After': '90'}), Response(b'{}'))
            client = soak.SoakClient(con, 'kalshi', attempts=1, opener=replay,
                                     sleep=self.clock.sleep, monotonic=self.clock.monotonic)
            url = 'https://external-api.kalshi.com/trade-api/v2/markets/HYPOTHETICAL'
            with self.assertRaises(OSError): client.get(url, 'test', lambda data: None)
            with self.assertRaisesRegex(OSError, 'cooldown'): client.get(url, 'test', lambda data: None)
            self.assertEqual(len(replay.requests), 1)
            self.clock.sleep(90)
            client.get(url, 'test', lambda data: None)
            self.assertEqual(len(replay.requests), 2)

    def test_missing_invalid_prices_identity_and_partial_liquidity(self):
        original = self.case['polymarket_us_rest']
        cases = []
        missing = deepcopy(original); del missing['marketData']['transactTime']; cases.append((missing, True))
        price = deepcopy(original); price['marketData']['bids'][0]['px']['value'] = '1.5'; cases.append((price, True))
        wrong = deepcopy(original); wrong['marketData']['marketSlug'] = 'hypothetical-wrong'; cases.append((wrong, True))
        partial = deepcopy(original); partial['marketData']['offers'] = []; cases.append((partial, False))
        for index, (data, invalid) in enumerate(cases):
            with self.subTest(index=index), connect(str(self.root / f'poll-{index}.sqlite3')) as con:
                self.us_faults = [Response(dumps(data).encode())]
                if invalid:
                    with self.assertRaises(ValueError):
                        soak.poll_us(con, self.config['us_slug'], self.client(con, 'polymarket_us'), now=self.clock.now)
                    self.assertEqual(con.execute('SELECT validation_status FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone()[0], 'REJECTED')
                else:
                    result = soak.poll_us(con, self.config['us_slug'], self.client(con, 'polymarket_us'), now=self.clock.now)
                    self.assertFalse(result['data_usable']); self.assertIn('PARTIAL_BOOK', result['rejections'])

    def test_stale_book_is_archived_without_inventing_freshness(self):
        data = deepcopy(self.case['polymarket_us_rest'])
        data['marketData']['transactTime'] = (self.clock.now() - timedelta(seconds=120)).isoformat()
        with connect(str(self.root / 'stale.sqlite3')) as con:
            self.us_faults = [Response(dumps(data).encode())]
            result = soak.poll_us(con, self.config['us_slug'], self.client(con, 'polymarket_us'), now=self.clock.now)
            self.assertIn('STALE_SOURCE', result['rejections'])
            self.assertEqual(con.execute('SELECT freshness FROM book_captures').fetchone()[0], 'STALE_SOURCE')

    def test_actual_us_stale_source_capture_replays_with_original_bytes(self):
        evidence = fixture('soak-us-stale-live')
        self.assertFalse(evidence['hypothetical'])
        responses = []
        for key in ('metadata', 'book'):
            row = evidence[key]
            self.assertEqual(hashlib.sha256(row['body'].encode()).hexdigest(), row['body_sha256'])
            responses.append(Response(row['body'].encode(), row['status'], row['headers']))
        with connect(str(self.root / 'live-replay.sqlite3')) as con:
            from predarb.validation import load_json
            from predarb.provider import HttpClient
            stamps = iter([evidence['metadata']['retrieved_at'], evidence['book']['retrieved_at']])
            client = HttpClient(con, 'polymarket_us', opener=Replay(*responses),
                                sleep=lambda seconds: None, utc_now=lambda: next(stamps))
            at = utc_time(evidence['book']['retrieved_at'])
            slug = load_json(evidence['metadata']['body'])['market']['slug']
            result = soak.poll_us(con, slug, client, now=lambda: at)
            self.assertIn(evidence['expected_rejection'], result['rejections'])
            self.assertFalse(result['data_usable'])
            bodies = con.execute('SELECT raw_body FROM raw_observations ORDER BY id').fetchall()
            self.assertEqual([row[0] for row in bodies], [evidence[key]['body'].encode() for key in ('metadata', 'book')])

    def test_failed_detail_refresh_blocks_previous_fresh_sample(self):
        with connect(str(self.root / 'barrier.sqlite3')) as con:
            client = self.client(con, 'polymarket_us')
            soak.poll_us(con, self.config['us_slug'], client, now=self.clock.now)
            self.assertTrue(soak.sample_books(con, self.config, self.clock.now())['books']['polymarket_us']['data_usable'])
            del self.case['polymarket_us_metadata']['marketSides']
            with self.assertRaises(ValueError): soak.poll_us(con, self.config['us_slug'], client, now=self.clock.now)
            state = soak.sample_books(con, self.config, self.clock.now())['books']['polymarket_us']
            self.assertFalse(state['data_usable'])
            self.assertIn('LATEST_COLLECTION_FAILED', state['rejections'])

    def test_cutoff_and_invalid_limits_fail_before_files_or_network(self):
        now = utc_time('2026-10-28T23:59:00Z')
        with self.assertRaisesRegex(ValueError, 'cutoff'):
            soak.run(self.root / 'invalid', self.config | {'protocol': 'sequence-v1'}, FakeCredentials(), now=lambda: now)
        self.assertFalse((self.root / 'invalid').exists())
        for values in ({'seconds': True}, {'poll_seconds': 0}, {'max_storage_mb': 10}, {'extra': 1}):
            with self.assertRaises(ValueError): soak.validate_config(self.config | values, self.clock.now())

    def test_clock_sync_resource_and_backup_failures_stop_before_stream(self):
        cases = [({'sync_probe': lambda: {'synchronized': None}}, 'CLOCK_SYNC_UNCONFIRMED'),
                 ({'backup_fn': lambda *a: (_ for _ in ()).throw(OSError('HYPOTHETICAL_SECRET'))}, 'COLLECTION_OR_BACKUP_FAILED')]
        for index, (options, code) in enumerate(cases):
            with self.subTest(code=code):
                result = self.run_soak(str(index), **options)
                self.assertEqual(result['status'], 'FAILED'); self.assertEqual(result['stop_reason'], code)
                self.assertEqual(result['counts']['kalshi_connections'], 0)
        with patch('predarb.soak.shutil.disk_usage', return_value=type('Usage', (), {'free': 0})()):
            result = self.run_soak('disk')
            self.assertEqual(result['stop_reason'], 'LOW_DISK_SPACE')
        with patch('predarb.soak.storage_bytes', return_value=1024**4):
            result = self.run_soak('cap')
            self.assertEqual(result['stop_reason'], 'STORAGE_LIMIT')

    def test_signal_stop_closes_connection_and_existing_directory_is_refused(self):
        stopped = threading.Event()
        def stop_during_capture(con, source, credentials, **options):
            original = options['on_tick']
            def tick(db, at):
                if self.clock.monotonic() >= 4: stopped.set()
                return original(db, at)
            options['on_tick'] = tick
            return self.stream(con, source, credentials, **options)
        result = self.run_soak(stop=stopped, capture_fn=stop_during_capture)
        self.assertEqual(result['status'], 'STOPPED'); self.assertEqual(result['stop_reason'], 'SIGNAL_STOP')
        self.assertLess(result['elapsed_seconds'], self.config['seconds'])
        with self.assertRaises(FileExistsError): self.run_soak()
        with connect(str(self.root / 'run/capture.sqlite3')) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM ws_connections WHERE ended_at IS NULL').fetchone()[0], 0)

    def test_report_detects_dead_writer_without_creating_or_mutating_database(self):
        result = self.run_soak()
        path = self.root / 'run/status.json'
        result['status'] = 'RUNNING'; soak.atomic_json(path, result)
        before = path.read_bytes()
        self.clock.sleep(121)
        self.assertEqual(soak.read_report(self.root / 'run', now=self.clock.now())['status'], 'INTERRUPTED_OR_UNRESPONSIVE')
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(FileNotFoundError): soak.read_report(self.root / 'absent')
        self.assertFalse((self.root / 'absent').exists())

    def test_periodic_backup_and_wall_clock_jump(self):
        self.config['seconds'] = 315
        result = self.run_soak()
        self.assertEqual(len(result['backups']), 3)
        self.config['seconds'] = 20
        def jump(con, source, credentials, **options):
            self.clock.at += timedelta(seconds=2)
            self.assertTrue(options['on_tick'](con, self.clock.now()))
            return {'failures': ['COORDINATOR_STOP']}
        result = self.run_soak('jump', capture_fn=jump)
        self.assertEqual(result['stop_reason'], 'WALL_CLOCK_JUMP')

    def test_storage_growth_stops_active_capture_and_closes_generation(self):
        real_size = soak.storage_bytes
        def size(root):
            return 1024**4 if self.clock.monotonic() >= 4 else real_size(root)
        with patch('predarb.soak.storage_bytes', side_effect=size):
            result = self.run_soak()
        self.assertEqual(result['stop_reason'], 'STORAGE_LIMIT')
        self.assertLess(result['elapsed_seconds'], 20)
        with connect(str(self.root / 'run/capture.sqlite3')) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM ws_connections WHERE ended_at IS NULL').fetchone()[0], 0)

    def test_cli_exit_codes_and_signal_handlers_restored(self):
        import signal
        from predarb import soak_cli
        args = SimpleNamespace(soak_cmd='run', output=str(self.root/'cli'), credentials_file='HYPOTHETICAL', **self.config)
        before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        for status, coverage, expected in [('COMPLETED', 'OBSERVATIONS_RECORDED', 0),
                                           ('COMPLETED', 'INSUFFICIENT_USABLE_DATA', 2),
                                           ('STOPPED', 'OBSERVATIONS_RECORDED', 2)]:
            with patch.object(soak_cli.Credentials, 'load', return_value=FakeCredentials()), \
                    patch.object(soak_cli.soak, 'run', return_value={'status': status, 'coverage_assessment': coverage}), \
                    redirect_stdout(StringIO()):
                self.assertEqual(soak_cli.run(args), expected)
        self.assertEqual({sig: signal.getsignal(sig) for sig in before}, before)
        with patch.object(soak_cli.Credentials, 'load', return_value=FakeCredentials()), \
                patch.object(soak_cli.soak, 'run', side_effect=OSError('HYPOTHETICAL')):
            with self.assertRaises(OSError): soak_cli.run(args)
        self.assertEqual({sig: signal.getsignal(sig) for sig in before}, before)


if __name__ == '__main__': unittest.main()
