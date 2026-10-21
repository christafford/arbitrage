"""HYPOTHETICAL network failures, retries and rate-limit scenarios; no live requests."""
from email.utils import format_datetime
from datetime import datetime, timezone, timedelta
from io import BytesIO
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

from predarb.provider import HttpClient, NoRedirect, retry_delay
from predarb.store import connect
from predarb import kalshi, polymarket_us as poly
from helpers import Response, Replay, real_response, fixture

URL = kalshi.page_url(2, None, None)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = connect(str(Path(self.temp.name) / 'x.sqlite3'))
        self.addCleanup(self.db.close)
        self.delays = []

    def client(self, *responses):
        replay = Replay(*responses)
        return HttpClient(self.db, 'kalshi', opener=replay, sleep=self.delays.append,
                          monotonic=lambda: 0), replay

    def get(self, client):
        return client.get(URL, kalshi.SCHEMA_VERSION, kalshi.validate_page)

    def test_get_only_with_timeout_and_raw_sha_before_validation(self):
        client, replay = self.client(real_response('kalshi-page'))
        def validate(data):
            self.assertEqual(self.db.execute('SELECT validation_status FROM raw_observations').fetchone()[0], 'PENDING')
            kalshi.validate_page(data)
        observation = client.get(URL, kalshi.SCHEMA_VERSION, validate)
        self.assertEqual(observation.id, 1)
        request, timeout = replay.requests[0]
        self.assertEqual((request.method, timeout), ('GET', 12))
        self.assertNotIn('Authorization', request.headers)
        self.assertEqual(self.db.execute('SELECT body_sha256,validation_status FROM raw_observations').fetchone(),
                         (fixture('kalshi-page')['body_sha256'], 'VALID'))

    def test_retry_429_and_503_archive_each_attempt_and_honor_retry_after(self):
        client, replay = self.client(Response(b'{}', 429, {'Content-Type': 'application/json', 'Retry-After': '3', 'Set-Cookie': 'private'}),
                                     Response(b'{}', 503), real_response('kalshi-page'))
        self.get(client)
        self.assertEqual(self.delays, [3, 0.25, 2, 0.25])
        self.assertEqual(self.db.execute('SELECT http_status,validation_status FROM raw_observations').fetchall(),
                         [(429, 'HTTP_ERROR'), (503, 'HTTP_ERROR'), (200, 'VALID')])
        self.assertNotIn('private', self.db.execute('SELECT headers_json FROM raw_observations LIMIT 1').fetchone()[0])
        self.assertEqual(len(replay.requests), 3)

    def test_urllib_http_error_retried(self):
        error = HTTPError(URL, 429, 'limited', {'Content-Type': 'application/json'}, BytesIO(b'{}'))
        client, _ = self.client(error, real_response('kalshi-page'))
        self.get(client)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], 2)

    def test_retries_exhaust_and_401_never_retry(self):
        for status, expected in ((503, 3), (401, 1), (404, 1), (302, 1)):
            with self.subTest(status=status):
                client, replay = self.client(*(Response(b'{}', status) for _ in range(expected)))
                with self.assertRaisesRegex(OSError, f'HTTP {status}'):
                    self.get(client)
                self.assertEqual(len(replay.requests), expected)

    def test_transport_errors_are_bounded(self):
        client, replay = self.client(URLError('HYPOTHETICAL outage'), TimeoutError(), URLError('still down'))
        with self.assertRaisesRegex(OSError, '3 attempts'):
            self.get(client)
        self.assertEqual(len(replay.requests), 3)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], 0)

    def test_long_retry_after_stops_without_shortening_delay(self):
        client, replay = self.client(Response(b'{}', 429, {'Retry-After': '120'}))
        with self.assertRaisesRegex(OSError, 'retry later'):
            self.get(client)
        self.assertEqual(self.delays, [])
        self.assertEqual(len(replay.requests), 1)

    def test_retry_after_http_dates_and_invalid_values(self):
        self.assertEqual(retry_delay('3'), 3)
        self.assertEqual(retry_delay('junk'), 0)
        self.assertEqual(retry_delay(None), 0)
        future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30))
        self.assertGreater(retry_delay(future), 28)

    def test_response_cap_and_invalid_json_content_type_archived(self):
        with patch('predarb.provider.MAX_BYTES', 4):
            client, _ = self.client(Response(b'123456'))
            with self.assertRaisesRegex(ValueError, '10 MB'):
                self.get(client)
        self.assertEqual(self.db.execute('SELECT raw_body,truncated,validation_status FROM raw_observations').fetchone(),
                         (b'12345', 1, 'REJECTED'))
        for response in (Response(b'not json'), Response(b'{}', headers={'Content-Type': 'text/html'})):
            client, _ = self.client(response)
            with self.assertRaisesRegex(ValueError, 'raw response archived'):
                self.get(client)
            self.assertEqual(self.db.execute('SELECT validation_status FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone()[0], 'REJECTED')

    def test_only_verified_us_hosts_and_no_redirects(self):
        client, replay = self.client()
        for url in ('http://external-api.kalshi.com/markets', 'https://clob.polymarket.com/book',
                    'https://gateway.polymarket.us/v1/markets', 'https://external-api.kalshi.com.evil/markets',
                    'https://user@external-api.kalshi.com/markets', URL + '#fragment'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                client.get(url, 'test', lambda data: None)
        self.assertEqual(len(replay.requests), 0)
        self.assertIsNone(NoRedirect().redirect_request(Request(URL), None, 302, 'redirect', {}, 'https://clob.polymarket.com'))
        with patch.dict('os.environ', {'POLYMARKET_US_DATA_BASE': 'https://polymarket.com'}):
            with self.assertRaises(ValueError):
                poly.base_url()

    def test_invalid_transport_configuration(self):
        for kwargs in ({'timeout': 0}, {'attempts': 0}, {'attempts': 6}, {'interval': 0.1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                HttpClient(self.db, 'kalshi', **kwargs)
        with self.assertRaises(ValueError):
            HttpClient(self.db, 'international')
