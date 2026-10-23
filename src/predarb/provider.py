"""Bounded, paced, GET-only transport. Archive bytes before JSON/schema handling."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .store import archive_response, validate_observation, timestamp
from .validation import load_json

LOG = logging.getLogger(__name__)
MAX_BYTES = 10_000_000
ORIGINS = {
    'kalshi': 'https://external-api.kalshi.com',
    'polymarket_us': 'https://gateway.polymarket.us',
}
# Exact public documentation URLs used by fee review. No arbitrary URL fetcher.
FEE_DOCUMENT_URLS = {
    'kalshi': ('https://docs.kalshi.com/api-reference/market/get-series.md',
               'https://docs.kalshi.com/getting_started/fee_rounding.md'),
    'polymarket_us': ('https://docs.polymarket.us/fees.md',),
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class Observation:
    id: int
    endpoint: str
    received_at: str
    data: dict | bytes


class HttpClient:
    def __init__(self, con, venue, *, timeout=12, attempts=3, interval=0.25,
                 opener=None, sleep=time.sleep, monotonic=time.monotonic, utc_now=timestamp):
        if venue not in ORIGINS:
            raise ValueError('unsupported US venue')
        if timeout <= 0 or not 1 <= attempts <= 5 or interval < 0.25:
            raise ValueError('invalid transport limits (at most 4 requests/s)')
        self.con, self.venue = con, venue
        self.timeout, self.attempts, self.interval = timeout, attempts, interval
        self.opener = opener or build_opener(NoRedirect())
        self.utc_now = utc_now
        self.sleep, self.monotonic, self.last_request = sleep, monotonic, None

    def get(self, url, schema_version, validator):
        parsed = urlsplit(url)
        if f'{parsed.scheme}://{parsed.netloc}' != ORIGINS[self.venue] or parsed.fragment:
            raise ValueError('only the verified production US venue origin is permitted')
        return self._get(url, schema_version, validator)

    def get_fee_document(self, url, schema_version):
        if url not in FEE_DOCUMENT_URLS[self.venue]:
            raise ValueError('only fixed official fee documentation URLs are permitted')
        return self._get(url, schema_version, None, document=True)

    def _get(self, url, schema_version, validator, *, document=False):
        for attempt in range(self.attempts):
            if self.last_request is not None:
                self.sleep(max(0, self.interval - (self.monotonic() - self.last_request)))
            self.last_request = self.monotonic()
            req = Request(url, headers={'User-Agent': 'prediction-arb-research/0.1 (read-only)',
                                       'Accept': 'text/markdown,text/plain' if document else 'application/json'}, method='GET')
            try:
                try:
                    response = self.opener.open(req, timeout=self.timeout)
                except HTTPError as exc:
                    response = exc
                with response:
                    body = response.read(MAX_BYTES + 1)
                    status, headers = response.code, response.headers
                received = self.utc_now()
                oversized = len(body) > MAX_BYTES
                observation_id = archive_response(self.con, self.venue, url, body,
                                                   status, headers, received, schema_version,
                                                   truncated=oversized)
                if oversized:
                    validate_observation(self.con, observation_id, 'REJECTED', 'response exceeds byte cap; truncated')
                    raise ValueError('response exceeds 10 MB cap; archived prefix only')
                if status in (429, 500, 502, 503, 504) and attempt + 1 < self.attempts:
                    validate_observation(self.con, observation_id, 'HTTP_ERROR', f'HTTP {status}')
                    delay = max(2 ** attempt, retry_delay(headers.get('Retry-After')))
                    if delay > 60:
                        raise OSError(f'HTTP {status}: Retry-After exceeds 60s retry budget; retry later')
                    self._retry(url, attempt, delay, f'HTTP {status}')
                    continue
                if status != 200:
                    validate_observation(self.con, observation_id, 'HTTP_ERROR', f'HTTP {status}')
                    raise OSError(f'HTTP {status} for {url}; raw response archived')
                try:
                    if document:
                        content_type = headers.get('Content-Type', '').split(';')[0].lower()
                        if content_type not in {'text/markdown', 'text/plain', 'text/x-markdown'}:
                            raise ValueError('unexpected fee document Content-Type')
                        if not 0 < len(body) <= 2000000:
                            raise ValueError('fee document must contain 1..2000000 bytes')
                        body.decode('utf-8')
                        data = body  # Prose is evidence for human review, never a parsed rate.
                    else:
                        if 'json' not in headers.get('Content-Type', '').lower():
                            raise ValueError('unexpected Content-Type; expected JSON')
                        data = load_json(body)
                        validator(data)
                except (ValueError, TypeError) as exc:
                    validate_observation(self.con, observation_id, 'REJECTED', str(exc))
                    raise ValueError(f'{url}: {exc}; raw response archived') from exc
                validate_observation(self.con, observation_id, 'VALID', None)
                return Observation(observation_id, url, received, data)
            except (URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
                if attempt + 1 == self.attempts:
                    raise OSError(f'transport failed after {self.attempts} attempts: {url}: {exc}') from exc
                self._retry(url, attempt, 2 ** attempt, type(exc).__name__)
        raise AssertionError('unreachable')

    def _retry(self, url, attempt, delay, reason):
        LOG.warning('retry ts_utc=%s venue=%s attempt=%s delay_s=%s reason=%s endpoint=%s',
                    timestamp(), self.venue, attempt + 1, delay, reason, url)
        self.sleep(delay)


def retry_delay(value):
    if value is None:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0
