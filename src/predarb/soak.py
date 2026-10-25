"""Bounded collection-only coordinator. One writer; no pair/economics execution."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import shutil
import threading
import time

from . import polymarket_us as us
from .backups import backup
from .book_store import inspect_book, record_normalization
from .book_stream import SEQUENCE_PROTOCOL_END, validate_protocol
from .collector import book_freshness
from .kalshi_ws import capture, refresh_metadata
from .operations import clock_sync, event
from .provider import HttpClient, retry_delay
from .runtime import writer_lock
from .store import connect, save_entry, save_book, start_run, update_run
from .validation import dumps, identifier, load_json, utc_time

MIB = 1024**2
HEADROOM = 32 * MIB  # One bounded HTTP/frame write plus derived rows may overshoot.


def clock():
    return datetime.now(timezone.utc)


class SoakClient(HttpClient):
    """Persist server cooldown across separate attempts and WS reconnects."""
    retry_not_before = 0

    def get(self, url, schema_version, validator):
        if self.monotonic() < self.retry_not_before:
            raise OSError('venue HTTP cooldown is still active')
        before = self.con.execute('SELECT COALESCE(MAX(id),0) FROM raw_observations').fetchone()[0]
        try:
            return super().get(url, schema_version, validator)
        finally:
            row = self.con.execute('''SELECT headers_json FROM raw_observations
                WHERE id>? AND venue=? AND http_status IN (429,503) ORDER BY id DESC LIMIT 1''',
                                   (before, self.venue)).fetchone()
            if row:
                self.retry_not_before = self.monotonic() + max(1, retry_delay(load_json(row[0]).get('retry-after')))


def validate_config(config, now):
    required = {'kalshi_ticker', 'us_slug', 'seconds', 'poll_seconds', 'segment_seconds',
                'backup_seconds', 'min_free_mb', 'max_storage_mb', 'protocol'}
    if set(config) != required:
        raise ValueError('unknown or missing soak configuration field')
    identifier(config['kalshi_ticker']); identifier(config['us_slug'])
    for key, low, high in [('seconds', 10, 86400), ('poll_seconds', 5, 60),
                           ('segment_seconds', 10, 300), ('backup_seconds', 300, 21600),
                           ('min_free_mb', 200, 1048576), ('max_storage_mb', 64, 102400)]:
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f'{key} must be an integer in {low}..{high}')
    validate_protocol(config['protocol'], now)
    if config['protocol'] == 'sequence-v1' and now + timedelta(seconds=config['seconds'] + 60) >= SEQUENCE_PROTOCOL_END:
        raise ValueError('requested soak plus shutdown allowance crosses sequence-v1 cutoff')


def poll_us(con, slug, client, *, now=clock):
    """Exact selected detail/book only; archive before validation, no catalogue claim."""
    run = start_run(con, us.VENUE, us.SCHEMA_VERSION,
                    {'filter': slug, 'transport': 'SOAK_SELECTED_DETAIL', 'selected': [slug]})
    records = 0
    try:
        def detail_check(data):
            us.validate_detail(data)
            if data['market']['slug'] != slug:
                raise ValueError('detail identity mismatch')
        detail = client.get(us.detail_url(slug), us.SCHEMA_VERSION, detail_check)
        market = detail.data['market']
        save_entry(con, run, detail, slug, market, us.rules(market), market.get(us.TIME_FIELD))
        records = 1
        def book_check(data):
            us.validate_book(data)
            if data['marketData']['marketSlug'] != slug:
                raise ValueError('book identity mismatch')
        book = client.get(us.book_url(slug), us.SCHEMA_VERSION, book_check)
        source_ts, sizes = us.book_info(book.data)
        at = now()
        save_book(con, run, book, slug, source_ts,
                  book_freshness(source_ts, book.received_at, now=at),
                  'EMPTY' if not any(sizes) else 'PARTIAL' if not all(sizes) else 'TWO_SIDED')
        result = record_normalization(con, book.id, detail.id, now=at)
        update_run(con, run, status='COMPLETE', pages=0, records=1, unique=1, next_page=None)
        return result
    except BaseException as exc:
        update_run(con, run, status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                   pages=0, records=records, unique=records, next_page=None, error='SOAK_US_POLL_FAILED')
        raise


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as handle:
        handle.write(dumps(data) + '\n'); handle.flush(); os.fsync(handle.fileno())
    temporary.replace(path)


def storage_bytes(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())


def sample_books(con, config, now):
    """Current-time diagnostics only, including disconnect and pending-frame barriers."""
    results = {}
    for venue, source in [('kalshi', config['kalshi_ticker']), ('polymarket_us', config['us_slug'])]:
        row = con.execute('''SELECT b.observation_id FROM book_captures b
            JOIN raw_observations r ON r.id=b.observation_id
            WHERE r.venue=? AND b.source_id=? ORDER BY b.observation_id DESC LIMIT 1''',
                          (venue, source)).fetchone()
        try:
            if row is None:
                raise ValueError('missing book')
            book = inspect_book(con, row[0], now=now)
            latest = con.execute('''SELECT status FROM collection_runs WHERE venue=?
                ORDER BY id DESC LIMIT 1''', (venue,)).fetchone()
            if latest and latest[0] in {'FAILED', 'INTERRUPTED'}:
                book['rejections'] = list(book['rejections']) + ['LATEST_COLLECTION_FAILED']
                book['data_usable'] = False
            results[venue] = {key: book[key] for key in
                              ('observation_id', 'data_usable', 'rejections', 'source_ts', 'received_at')}
        except (ValueError, KeyError):
            results[venue] = {'observation_id': row[0] if row else None, 'data_usable': False,
                              'rejections': ['MISSING_OR_INVALID_BOOK'], 'source_ts': None, 'received_at': None}
    both = all(b['data_usable'] for b in results.values())
    aligned = both and all(abs(utc_time(results['kalshi'][key]) - utc_time(results['polymarket_us'][key]))
                          <= timedelta(seconds=2) for key in ('source_ts', 'received_at'))
    return {'books': results, 'both_fresh': both, 'timestamps_within_2s': bool(aligned),
            'equivalence_verified': False, 'fees_or_profit_evaluated': False}


def read_report(directory, *, now=None):
    path = Path(directory) / 'status.json'
    with path.open('rb') as handle:
        body = handle.read(1000001)
    if len(body) > 1000000:
        raise ValueError('soak report exceeds size limit')
    result = load_json(body)
    if result.get('schema') != 'collection-soak/v1':
        raise ValueError('unsupported soak report')
    age = ((now or clock()) - utc_time(result['heartbeat_at'])).total_seconds()
    result['heartbeat_age_seconds'] = int(age)
    if result['status'] == 'RUNNING' and (age > 120 or age < -5):
        result['status'] = 'INTERRUPTED_OR_UNRESPONSIVE'
    return result


def run(directory, config, credentials, *, stop=None, now=clock, monotonic=time.monotonic,
        sleep=time.sleep, capture_fn=capture, client_factory=SoakClient, backup_fn=backup,
        sync_probe=clock_sync):
    """A new isolated archive per invocation. Never revive a disconnected generation."""
    validate_config(config, now())
    root = Path(directory).absolute()
    root.mkdir(parents=True, exist_ok=False)
    database = root / 'capture.sqlite3'
    atomic_json(root / 'config.json', config)
    stop = stop or threading.Event()
    started, start_mono = now(), monotonic()
    deadline = start_mono + config['seconds']
    counts = Counter()
    failures = Counter()
    sample_reasons = Counter()
    report = {'schema': 'collection-soak/v1', 'status': 'RUNNING', 'pid': os.getpid(),
              'started_at': started.isoformat(), 'planned_end_at': (started + timedelta(seconds=config['seconds'])).isoformat(),
              'config': config, 'verification': 'UNVERIFIED', 'trading_authorized': False,
              'fees_or_profit_evaluated': False, 'equivalence_verified': False,
              'counts': counts, 'failures': failures, 'sample_rejections': sample_reasons,
              'latest_sample': None, 'backups': [], 'stop_reason': None,
              'clock': sync_probe(), 'max_sample_gap_ms': 0, 'max_poll_duration_ms': 0}
    next_poll = next_sample = next_resource = start_mono
    next_backup = start_mono + config['backup_seconds']
    last_sample, consecutive_errors, storage = None, 0, 0

    with writer_lock(database), connect(str(database)) as con:
        # Requests are serialized and paced. A failed US request is retried by the
        # coordinator, respecting Retry-After; it never blocks in a long retry sleep.
        us_client = client_factory(con, us.VENUE, timeout=3, attempts=1, interval=1)
        k_client = client_factory(con, 'kalshi', timeout=3, attempts=1, interval=1)

        def emit(action='SOAK_HEARTBEAT'):
            report.update(heartbeat_at=now().isoformat(), elapsed_seconds=int(monotonic() - start_mono),
                          storage_bytes=storage)
            event(con, 'INFO', action, report, now())
            atomic_json(root / 'status.json', report)

        def resource_guard(extra=0):
            nonlocal storage
            storage = storage_bytes(root)
            if shutil.disk_usage(root).free < config['min_free_mb'] * MIB + HEADROOM + extra:
                return 'LOW_DISK_SPACE'
            if storage + HEADROOM + extra > config['max_storage_mb'] * MIB:
                return 'STORAGE_LIMIT'
            return None

        def guard():
            nonlocal next_resource
            if stop.is_set(): return 'SIGNAL_STOP'
            if abs((now() - started).total_seconds() - (monotonic() - start_mono)) > 1:
                return 'WALL_CLOCK_JUMP'
            try:
                validate_protocol(config['protocol'], now())
            except ValueError:
                return 'PROTOCOL_REVIEW_REQUIRED'
            if monotonic() >= next_resource:
                next_resource = monotonic() + 1
                return resource_guard()
            return None

        def tick(db, at):
            nonlocal next_poll, next_sample, last_sample, consecutive_errors
            if report['stop_reason']:
                return True
            report['stop_reason'] = guard()
            if report['stop_reason'] or monotonic() >= deadline:
                return True
            if monotonic() >= next_poll:
                poll_started = monotonic()
                before = con.execute('SELECT COALESCE(MAX(id),0) FROM raw_observations').fetchone()[0]
                counts['us_poll_attempts'] += 1
                delay = config['poll_seconds']
                try:
                    result = poll_us(con, config['us_slug'], us_client, now=now)
                    counts['us_polls_complete'] += 1
                    counts['us_books_usable_at_capture'] += int(result['data_usable'])
                    consecutive_errors = 0
                except (ValueError, OSError):
                    counts['us_poll_failures'] += 1
                    failures['US_POLL_FAILED'] += 1
                    consecutive_errors += 1
                    delay = max(delay, min(300, 2 ** min(consecutive_errors, 9)))
                    row = con.execute('''SELECT headers_json FROM raw_observations
                        WHERE id>? AND venue='polymarket_us' AND http_status IN (429,503)
                        ORDER BY id DESC LIMIT 1''', (before,)).fetchone()
                    if row:
                        delay = max(delay, retry_delay(load_json(row[0]).get('retry-after')))
                next_poll = monotonic() + delay  # No catch-up bursts after a slow request.
                report['max_poll_duration_ms'] = max(report['max_poll_duration_ms'], int((monotonic() - poll_started) * 1000))
                report['stop_reason'] = guard()
                if report['stop_reason']: return True
            if monotonic() >= next_sample:
                sampled = monotonic()
                if last_sample is not None:
                    report['max_sample_gap_ms'] = max(report['max_sample_gap_ms'], int((sampled - last_sample) * 1000))
                last_sample, next_sample = sampled, sampled + 10
                report['latest_sample'] = sample_books(con, config, now())
                counts['samples'] += 1
                for key in ('both_fresh', 'timestamps_within_2s'):
                    counts[key + '_samples'] += int(report['latest_sample'][key])
                for venue, book in report['latest_sample']['books'].items():
                    counts[venue + '_fresh_samples'] += int(book['data_usable'])
                    for reason in book['rejections']:
                        sample_reasons[venue + ':' + reason.split(':', 1)[0]] += 1
                emit()
            return False

        def take_backup():
            # A closed stream and explicit pause prevent treating backup time as
            # demonstrated live continuity. Reserve both temporary/final file space.
            estimate = con.execute('PRAGMA page_count').fetchone()[0] * con.execute('PRAGMA page_size').fetchone()[0]
            reason = resource_guard(2 * estimate)
            if reason:
                report['stop_reason'] = reason
                return
            emit('SOAK_BACKUP_STARTED')
            snapshot = root / 'backups' / f"snapshot-{len(report['backups']) + 1:03d}.sqlite3"
            result = backup_fn(database, snapshot)
            report['backups'].append({key: result[key] for key in
                                      ('destination', 'file_sha256', 'logical_sha256', 'created_at')})
            counts['backups_complete'] += 1
            emit('SOAK_BACKUP_COMPLETE')

        try:
            emit('SOAK_STARTED')
            if report['clock']['synchronized'] is not True:
                report['stop_reason'] = 'CLOCK_SYNC_UNCONFIRMED'
            if not report['stop_reason']:
                take_backup()
            while monotonic() < deadline and not report['stop_reason']:
                if tick(con, now()): break
                remaining = int(deadline - monotonic())
                if remaining < 1:
                    sleep(max(0, deadline - monotonic()))
                    break
                result = capture_fn(con, config['kalshi_ticker'], credentials,
                                    seconds=min(config['segment_seconds'], remaining),
                                    max_messages=100000, max_connections=120,
                                    min_free_bytes=config['min_free_mb'] * MIB,
                                    directory=str(root), protocol=config['protocol'], on_tick=tick,
                                    metadata_loader=lambda db, source: refresh_metadata(db, source, client=k_client),
                                    now=now, monotonic=monotonic, sleep=sleep)
                counts['segments'] += 1
                for key in ('connections', 'messages', 'snapshots', 'deltas', 'usable_books', 'recoveries'):
                    counts['kalshi_' + key] += result.get(key, 0)
                for reason in result['failures']:
                    if reason != 'COORDINATOR_STOP': failures[reason] += 1
                    if reason in {'WALL_CLOCK_JUMP', 'LOW_DISK_SPACE', 'PROTOCOL_REVIEW_REQUIRED', 'UNEXPECTED_MARKET_CLOCK'}:
                        report['stop_reason'] = reason
                event(con, 'INFO', 'SOAK_SEGMENT', result, now())
                con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                if report['stop_reason']: break
                if monotonic() >= next_backup:
                    take_backup()
                    next_backup = monotonic() + config['backup_seconds']
                emit()
            if not report['stop_reason']:
                report['stop_reason'] = 'DURATION_COMPLETE'
            if report['stop_reason'] in {'DURATION_COMPLETE', 'SIGNAL_STOP'}:
                take_backup()
        except KeyboardInterrupt:
            report['stop_reason'] = 'SIGNAL_STOP'
        except Exception:
            report['stop_reason'] = 'COLLECTION_OR_BACKUP_FAILED'
            failures['COLLECTION_OR_BACKUP_FAILED'] += 1
        finally:
            # Hard process death is instead detected by the report's stale heartbeat.
            con.execute("UPDATE ws_connections SET ended_at=?,end_reason='SOAK_STOPPED' WHERE ended_at IS NULL",
                        (now().isoformat(),))
            con.commit()
            report['status'] = ('COMPLETED' if report['stop_reason'] == 'DURATION_COMPLETE'
                                else 'STOPPED' if report['stop_reason'] == 'SIGNAL_STOP' else 'FAILED')
            report['coverage_assessment'] = ('OBSERVATIONS_RECORDED' if counts['kalshi_usable_books'] and
                                             counts['us_books_usable_at_capture'] else 'INSUFFICIENT_USABLE_DATA')
            report['latest_sample'] = sample_books(con, config, now())
            storage = storage_bytes(root)
            emit('SOAK_FINISHED')
            con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    return report
