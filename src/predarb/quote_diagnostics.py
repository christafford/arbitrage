"""Isolated research telemetry. Never supplies eligibility to the economics engine."""
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import io
import json
from pathlib import Path
import statistics
import time
from urllib.error import HTTPError

from . import soak, kalshi_ws
from .provider import MAX_BYTES
from .validation import dumps, load_json, utc_time

VERSION = 'quote-synchronization/m5m-v1'


def wall():
    return datetime.now(timezone.utc).isoformat()


def compare(books, at):
    """Two timestamp gates remain exact; experimental response metric is separate."""
    reasons = []
    for venue in ('kalshi', 'polymarket_us'):
        book = books.get(venue)
        if book is None:
            reasons.append(venue + ':MISSING_BOOK')
        else:
            reasons.extend(venue + ':' + r for r in book['rejections'])
            if not book['data_usable'] and not book['rejections']:
                reasons.append(venue + ':UNUSABLE_BOOK')
    source_skew = receipt_skew = None
    if len(books) == 2:
        k, u = books['kalshi'], books['polymarket_us']
        if k['source_ts'] and u['source_ts']:
            source_skew = abs((utc_time(k['source_ts']) - utc_time(u['source_ts'])).total_seconds())
        if k['received_at'] and u['received_at']:
            receipt_skew = abs((utc_time(k['received_at']) - utc_time(u['received_at'])).total_seconds())
    if source_skew is None: reasons.append('SOURCE_SKEW_UNKNOWN')
    elif source_skew > 2: reasons.append('SOURCE_SKEW_GT_2S')
    if receipt_skew is None: reasons.append('RECEIPT_SKEW_UNKNOWN')
    elif receipt_skew > 2: reasons.append('RECEIPT_SKEW_GT_2S')
    # Sensitivity analysis ONLY: removes US transaction age/source skew, never a
    # substitute for source freshness. A response has no demonstrated US continuity.
    experimental = [r for r in reasons if r not in {'SOURCE_SKEW_GT_2S', 'polymarket_us:STALE_SOURCE'}]
    for venue, book in books.items():
        receipt = book.get('received_at')
        age = (at - utc_time(receipt)).total_seconds() if receipt else None
        if age is None or not 0 <= age <= 2:
            experimental.append(venue + ':RESPONSE_NOT_WITHIN_2S')
    return {'source_skew_seconds': source_skew, 'receipt_skew_seconds': receipt_skew,
            'strict_observation_valid': not reasons, 'strict_rejections': sorted(set(reasons)),
            'experimental_policy': 'recent-response-sensitivity/m5m-v1',
            'experimental_response_only_pass': not experimental,
            'experimental_rejections': sorted(set(experimental)),
            'continuous_us_book_validity': 'UNVERIFIED',
            'economic_eligibility': False, 'trading_authorized': False}


class Changes:
    """Observe depth changes, never invent a change time before the first snapshot.

    Repeated HTTP snapshots do not establish no intervening changes. Generation
    changes reset the Kalshi observation window; initial time is left-censored.
    """
    def __init__(self): self.states = {}

    def observe(self, venue, book, mono, generation=None):
        payload = [[(str(x['price']), str(x['quantity'])) for x in book[key]]
                   for key in ('yes_asks', 'no_asks')]
        digest = hashlib.sha256(dumps(payload).encode()).hexdigest()
        prev = self.states.get(venue)
        reset = prev is None or prev['generation'] != generation
        changed = None if reset else digest != prev['depth_sha256']
        since = mono if reset or changed else prev['unchanged_since_monotonic']
        result = {'depth_sha256': digest, 'generation': generation, 'changed_from_previous_observation': changed,
                  'unchanged_since_monotonic': since, 'observed_unchanged_seconds': mono - since,
                  'last_observed_change_monotonic': (mono if changed else None if reset else prev['last_observed_change_monotonic']),
                  'change_time_left_censored': True if reset else prev['change_time_left_censored'] and not changed,
                  'continuous_unchanged_claim': False}
        self.states[venue] = result
        return dict(result)


class Body(io.BytesIO):
    def __init__(self, body, code, headers):
        super().__init__(body); self.code = code; self.headers = headers


class MeasuredClient(soak.SoakClient):
    """One-attempt telemetry includes request/body timing, excluding SQLite work."""
    def __init__(self, con, venue, *, emit, **kwargs):
        super().__init__(con, venue, **kwargs)
        if self.attempts != 1: raise ValueError('diagnostic requires one attempt per poll')
        self.emit = emit
        original = self.opener
        owner = self
        class Opener:
            def open(self, request, timeout):
                info = owner.current
                info.update(request_started_at=owner.utc_now(), request_monotonic=owner.monotonic())
                try:
                    try: response = original.open(request, timeout=timeout)
                    except HTTPError as exc: response = exc
                    info['headers_monotonic'] = owner.monotonic()
                    with response:
                        body = response.read(MAX_BYTES + 1)
                        info.update(received_at=owner.utc_now(), receive_monotonic=owner.monotonic(),
                                    http_status=response.code, response_bytes=len(body),
                                    http_date=response.headers.get('Date'), http_age=response.headers.get('Age'),
                                    cache_control=response.headers.get('Cache-Control'))
                    return Body(body, response.code, response.headers)
                finally:
                    info['request_finished_monotonic'] = owner.monotonic()
        self.opener = Opener()

    def get(self, url, schema_version, validator):
        self.current = {'kind': 'http_request', 'venue': self.venue, 'url': url,
                        'call_started_at': self.utc_now(), 'call_monotonic': self.monotonic()}
        before = self.con.execute('SELECT COALESCE(MAX(id),0) FROM raw_observations').fetchone()[0]
        try:
            result = super().get(url, schema_version, validator)
            self.current['success'] = True
            return result
        except (ValueError, OSError):
            self.current['success'] = False
            raise
        finally:
            row = self.con.execute('SELECT id,body_sha256,validation_status FROM raw_observations WHERE id>? AND endpoint=? ORDER BY id DESC LIMIT 1', (before, url)).fetchone()
            self.current.update(observation_id=row[0] if row else None,
                                body_sha256=row[1] if row else None,
                                validation_status=row[2] if row else None,
                                call_finished_monotonic=self.monotonic())
            self.emit(self.current)


class Diagnostics:
    def __init__(self, path, config, *, monotonic=time.monotonic):
        self.path, self.config, self.monotonic = Path(path), config, monotonic
        self.handle = self.path.open('x')
        self.last_sample = -1
        self.last_normalization = 0
        self.timing = {}
        self.changes = Changes()

    def close(self): self.handle.close()

    def emit(self, record):
        if record.get('observation_id') is not None:
            self.timing[record['observation_id']] = dict(record)
            # Only recent transport associations are needed in memory; all remain on disk.
            if len(self.timing) > 2048:
                self.timing.pop(next(iter(self.timing)))
        self.handle.write(dumps(dict(schema=VERSION, **record)) + '\n')
        self.handle.flush()

    def sample(self, con, at, *, force=False):
        mono = self.monotonic()
        # All normalized depth changes are observed, regardless of sample cadence.
        for row in con.execute('SELECT id,observation_id,result_json FROM normalized_books WHERE id>? ORDER BY id', (self.last_normalization,)):
            self.last_normalization = row[0]
            book = load_json(row[2])
            transport = self.timing.get(row[1], {})
            received_mono = transport.get('receive_monotonic')
            if received_mono is None: continue
            changes = self.changes.observe(book['venue'], book, received_mono, transport.get('connection_id'))
            raw = con.execute('SELECT raw_body FROM raw_observations WHERE id=?', (row[1],)).fetchone()
            payload = load_json(raw[0])
            message = payload.get('msg', {}) if book['venue'] == 'kalshi' else {}
            self.emit({'kind': 'book_observation', 'observation_id': row[1], 'venue': book['venue'],
                       'received_at': book['received_at'], 'receive_monotonic': received_mono,
                       'source_ts': book['source_ts'], 'timestamp_kind': book['timestamp_kind'],
                       'sequence': book['sequence'], 'market_clock': message.get('clock'),
                       'exchange_event_ts_ms': message.get('ts_ms'), 'exchange_event_ts': message.get('ts'),
                       'data_usable_at_normalization': book['data_usable'], 'rejections': book['rejections'],
                       'changes': changes})
        if not force and mono - self.last_sample < 1: return
        self.last_sample = mono
        start = self.monotonic()
        sample = soak.sample_books(con, self.config, at)
        comparison = compare(sample['books'], at)
        self.emit({'kind': 'comparison', 'at': at.isoformat(), 'sample_monotonic': mono,
                   'assessment_seconds': self.monotonic() - start, 'books': sample['books'], **comparison})

    def capture(self, con, source, credentials, **kwargs):
        tick = kwargs['on_tick']
        def observed_tick(db, at):
            stop = tick(db, at)
            # The coordinator may have blocked for HTTP. Sample at the current clock.
            self.sample(db, kwargs['now']())
            return stop
        kwargs['on_tick'] = observed_tick
        kwargs['on_receive'] = self.emit
        kwargs['on_book'] = lambda db, observed, at: self.sample(db, at)
        kwargs['connect_socket'] = lambda headers: ObservedSocket(kalshi_ws.open_socket(headers), self.emit, self.monotonic)
        return kalshi_ws.capture(con, source, credentials, **kwargs)


class ObservedSocket:
    """One explicit read-only ping per connection, with nonblocking pong observation.

    The observed duration is an upper bound (application scheduling included), not
    network RTT. The library handles protocol ping/pong independently of recv().
    """
    def __init__(self, socket, emit, monotonic=time.monotonic):
        self.socket, self.emit, self.monotonic = socket, emit, monotonic
        self.waiter = None

    def __enter__(self):
        self.socket.__enter__()
        try:
            self.started = self.monotonic()
            self.emit({'kind': 'ws_connected', 'at': wall(), 'monotonic': self.started})
            self.waiter = self.socket.ping()
        except BaseException as exc:
            self.socket.__exit__(type(exc), exc, exc.__traceback__)
            raise
        return self

    def check(self):
        if self.waiter is not None and self.waiter.is_set():
            self.emit({'kind': 'ws_pong_observed', 'at': wall(), 'monotonic': self.monotonic(),
                       'connection_started_monotonic': self.started,
                       'ping_observation_upper_bound_seconds': self.monotonic() - self.started})
            self.waiter = None

    def send(self, value): return self.socket.send(value)

    def recv(self, **kwargs):
        try: return self.socket.recv(**kwargs)
        finally: self.check()

    def __exit__(self, *args):
        try:
            self.check()
            self.emit({'kind': 'ws_disconnecting', 'at': wall(), 'monotonic': self.monotonic(),
                       'connection_started_monotonic': self.started, 'pong_unobserved': self.waiter is not None})
        finally:
            self.socket.__exit__(*args)


def distribution(values):
    values = sorted(v for v in values if v is not None)
    if not values: return {'count': 0, 'min': None, 'median': None, 'p95': None, 'max': None}
    return {'count': len(values), 'min': values[0], 'median': statistics.median(values),
            'p95': values[min(len(values)-1, (95*len(values)+99)//100-1)], 'max': values[-1]}


def summarize(path):
    counts, rejects, experimental_rejects = Counter(), Counter(), Counter()
    metrics, prior_requests = {}, {}
    first = last = None
    def add(key, value): metrics.setdefault(key, []).append(value)
    for line in Path(path).open():
        r = load_json(line)
        if r.get('schema') != VERSION: raise ValueError('unknown diagnostic schema')
        kind = r['kind']; counts[kind] += 1
        if kind == 'ws_pong_observed':
            add('ws_ping_observation_upper_bound_seconds', r['ping_observation_upper_bound_seconds'])
        elif kind == 'comparison':
            first = first or r['at']; last = r['at']
            counts['strict_valid'] += int(r['strict_observation_valid'])
            counts['experimental_response_only_pass'] += int(r['experimental_response_only_pass'])
            rejects.update(r['strict_rejections']); experimental_rejects.update(r['experimental_rejections'])
            for key in ('source_skew_seconds', 'receipt_skew_seconds', 'assessment_seconds'): add(key, r[key])
        elif kind == 'http_request':
            venue = r['venue']; start = r.get('request_monotonic'); end = r.get('receive_monotonic')
            counts[venue + ':http_success'] += int(r.get('success', False))
            counts[venue + ':http_failure'] += int(not r.get('success', False))
            if start is not None and end is not None:
                add(venue + ':request_response_seconds', end - start)
                add(venue + ':headers_seconds', r['headers_monotonic'] - start)
                add(venue + ':call_seconds', r['call_finished_monotonic'] - r['call_monotonic'])
                add(venue + ':pacing_seconds', start - r['call_monotonic'])
                add(venue + ':body_transfer_seconds', end - r['headers_monotonic'])
                add(venue + ':archive_validation_seconds', r['call_finished_monotonic'] - end)
                if r['url'] in prior_requests: add(venue + ':' + ('book' if r['url'].endswith('/book') else 'metadata') + ':poll_interval_seconds', start-prior_requests[r['url']])
                prior_requests[r['url']] = start
                if r.get('http_date'):
                    try:
                        remote = parsedate_to_datetime(r['http_date'])
                        # Coarse HTTP responder wall time only. NOT matching-engine clock offset.
                        add(venue + ':http_date_minus_receipt_seconds', (remote-utc_time(r['received_at'])).total_seconds())
                    except (ValueError, TypeError, OverflowError): counts['invalid_http_date'] += 1
        elif kind == 'book_observation':
            v = r['venue']; counts[v + ':book_observations'] += 1
            changed = r['changes']['changed_from_previous_observation']
            counts[v + ':initial_or_reset' if changed is None else v + ':depth_changed' if changed else v + ':depth_repeated'] += 1
            add(v + ':observed_unchanged_seconds', r['changes']['observed_unchanged_seconds'])
            if r['source_ts']: add(v + ':source_to_application_receipt_seconds', (utc_time(r['received_at'])-utc_time(r['source_ts'])).total_seconds())
    return {'schema': VERSION, 'first_comparison_at': first, 'last_comparison_at': last,
            'counts': dict(counts), 'strict_rejections': dict(rejects),
            'experimental_rejections': dict(experimental_rejects),
            'metrics': {k: distribution(v) for k,v in metrics.items()},
            'continuous_us_validity': 'UNVERIFIED', 'remote_clock_offset': 'UNKNOWN',
            'economic_eligibility': False, 'trading_authorized': False}
