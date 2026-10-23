"""Bounded authenticated read-only orderbook capture. No order/account commands."""
from dataclasses import replace
from datetime import datetime, timezone
import logging
import shutil
import time

from . import kalshi, ws_store
from .book_stream import KalshiBookStream, StreamProtocolError
from .kalshi_auth import WS_URL
from .provider import HttpClient
from .store import save_entry, start_run, update_run, validate_observation
from .validation import dumps, identifier, load_json


def clock():
    return datetime.now(timezone.utc)


def open_socket(headers):
    try:
        from websockets.sync.client import reconnect
    except ImportError:
        raise ValueError('install the kalshi-ws optional dependencies') from None
    # A private disabled logger prevents even application-wide DEBUG from exposing
    # handshake headers, incoming account fields, close reasons or error bodies.
    logger = logging.Logger('predarb.private_ws_transport')
    logger.disabled = True
    class FixedOrigin(reconnect):
        def process_redirect(self, exc):
            return exc  # Never forward Kalshi-specific auth headers to a redirect.
    return FixedOrigin(WS_URL, additional_headers=headers, proxy=None, compression=None,
                       open_timeout=10, close_timeout=2, ping_interval=10, ping_timeout=10,
                       max_size=1_000_000, max_queue=16, logger=logger).connect()


def refresh_metadata(con, source_id, *, client=None):
    client = client or HttpClient(con, 'kalshi', interval=1)
    run = start_run(con, 'kalshi', kalshi.SCHEMA_VERSION,
                    {'filter': 'market:' + source_id, 'selected': [source_id], 'transport': 'WS_METADATA'})
    try:
        def validate(data):
            kalshi.validate_detail(data)
            if data['market']['ticker'] != source_id:
                raise ValueError('market identity mismatch')
        detail = client.get(kalshi.detail_url(source_id), kalshi.SCHEMA_VERSION, validate)
        market = detail.data['market']
        save_entry(con, run, detail, source_id, market, kalshi.rules(market), market[kalshi.TIME_FIELD])
        update_run(con, run, status='COMPLETE', pages=1, records=1, unique=1, next_page=None)
        return run, detail
    except BaseException as exc:
        update_run(con, run, status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                   pages=0, records=0, unique=0, next_page=None, error='WS_METADATA_REFRESH_FAILED')
        raise


def capture(con, source_id, credentials, *, seconds=60, max_messages=10000, max_connections=10,
            min_free_bytes=1024**3, directory='.', connect_socket=open_socket, metadata_loader=refresh_metadata,
            now=clock, monotonic=time.monotonic, sleep=time.sleep, on_book=None):
    identifier(source_id)
    for value, low, high in ((seconds, 1, 3600), (max_messages, 1, 100000), (max_connections, 1, 120)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('invalid stream duration/message/connection budget')
    if type(min_free_bytes) is not int or min_free_bytes < 200 * 1024**2:
        raise ValueError('stream free-space floor must be at least 200 MiB')
    stats = {'connections': 0, 'messages': 0, 'snapshots': 0, 'deltas': 0, 'usable_books': 0,
             'recoveries': 0, 'failures': [], 'connection_ids': [], 'verification': 'UNVERIFIED',
             'trading_authorized': False, 'live_continuity_demonstrated': False}
    deadline = monotonic() + seconds
    attempts, had_failure = 0, False
    # An interrupted earlier invocation has no demonstrable transport continuity.
    con.execute("UPDATE ws_connections SET ended_at=?,end_reason='PREVIOUS_WRITER_STOPPED' WHERE ended_at IS NULL",
                (now().isoformat(),))
    con.commit()
    while monotonic() < deadline and stats['messages'] < max_messages and stats['connections'] < max_connections:
        if shutil.disk_usage(directory).free < min_free_bytes:
            stats['failures'].append('LOW_DISK_SPACE'); break
        connection_id, reason, stream = None, 'CONNECTION_FAILED', None
        stats['connections'] += 1
        wall_start, mono_start = now(), monotonic()
        try:
            run, detail = metadata_loader(con, source_id)
            connection_id = ws_store.begin_connection(con, source_id, run, detail.id, at=now().isoformat())
            stats['connection_ids'].append(connection_id)
            stream = KalshiBookStream(source_id, detail.data['market'], metadata_received_at=detail.received_at)
            stream.generation = connection_id
            headers = credentials.headers()
            secrets = (headers['KALSHI-ACCESS-KEY'], headers['KALSHI-ACCESS-SIGNATURE'])
            with connect_socket(headers) as socket:
                socket.send(dumps({'id': 1, 'cmd': 'subscribe', 'params': {
                    'channels': ['orderbook_delta'], 'market_ticker': source_id,
                    'use_yes_price': False}}))
                sid, frames, last_message = None, 0, monotonic()
                while monotonic() < deadline and stats['messages'] < max_messages:
                    received = now()
                    if abs((received - wall_start).total_seconds() - (monotonic() - mono_start)) > 1:
                        reason = 'WALL_CLOCK_JUMP'; break
                    if monotonic() - mono_start >= 30 or frames >= ws_store.MAX_FRAMES:
                        reason = 'PERIODIC_RESNAPSHOT'; break
                    if monotonic() - last_message >= 5:
                        reason = 'MESSAGE_TIMEOUT'; break
                    if shutil.disk_usage(directory).free < min_free_bytes:
                        reason = 'LOW_DISK_SPACE'; break
                    try:
                        body = socket.recv(timeout=min(.5, max(.001, deadline - monotonic())))
                    except TimeoutError:
                        continue
                    received = now()  # Receipt captured before security screening/normalization.
                    last_message = monotonic()
                    observed, safe, kind = ws_store.archive_frame(con, connection_id, body,
                                                                 at=received.isoformat(), secrets=secrets)
                    stats['messages'] += 1; frames += 1
                    try:
                        if abs((received - wall_start).total_seconds() - (monotonic() - mono_start)) > 1:
                            raise ValueError('wall clock jump')
                        frame = load_json(safe)
                        if kind == 'REDACTED':
                            raise ValueError('unexpected or unsafe message')
                        if frame['type'] == 'subscribed':
                            if sid is not None or frame.get('id') != 1 or frame['msg'].get('channel') != 'orderbook_delta':
                                raise ValueError('unexpected acknowledgment')
                            sid = frame['msg'].get('sid')
                            if type(sid) is not int or sid < 1:
                                raise ValueError('invalid subscription id')
                            validate_observation(con, observed, 'VALID', None)
                            continue
                        if sid is None or frame.get('sid') != sid:
                            raise ValueError('unacknowledged subscription')
                        book = stream.apply(frame, received_at=received.isoformat(), now=received,
                                            generation=connection_id)
                        if any(issue not in {'EMPTY_BOOK', 'PARTIAL_BOOK'} for issue in book.issues(now=received)):
                            raise ValueError('source/metadata freshness rejected')
                        book = replace(book, transport='KALSHI_AUTHENTICATED_WS')
                        ws_store.record_frame(con, observed, book, now=received)
                    except StreamProtocolError as exc:
                        validate_observation(con, observed, 'REJECTED', exc.code)
                        reason = exc.code; break
                    except (ValueError, TypeError, KeyError, OverflowError):
                        validate_observation(con, observed, 'REJECTED', 'INVALID_STREAM_FRAME')
                        reason = 'INVALID_STREAM_FRAME'; break
                    key = 'snapshots' if frame['type'] == 'orderbook_snapshot' else 'deltas'
                    stats[key] += 1
                    if not book.issues(now=received): stats['usable_books'] += 1
                    if had_failure and key == 'snapshots':
                        stats['recoveries'] += 1; had_failure = False
                    if on_book is not None:
                        on_book(con, observed, now())
                    if abs((now() - wall_start).total_seconds() - (monotonic() - mono_start)) > 1:
                        reason = 'WALL_CLOCK_JUMP'; break
                else:
                    reason = 'BUDGET_COMPLETE'
        except KeyboardInterrupt:
            reason = 'SIGNAL_STOP'
            raise
        except Exception:
            # No exception text/response/headers are persisted or printed.
            reason = 'CONNECTION_OR_PROCESSING_FAILED'
        finally:
            if stream is not None: stream.disconnect()
            if connection_id is not None:
                ws_store.end_connection(con, connection_id, at=now().isoformat(), reason=reason)
        if reason in {'WALL_CLOCK_JUMP', 'LOW_DISK_SPACE'}:
            stats['failures'].append(reason); break
        if reason not in {'BUDGET_COMPLETE', 'PERIODIC_RESNAPSHOT'}:
            stats['failures'].append(reason); had_failure = True; attempts += 1
        else:
            attempts = 0
        remaining = deadline - monotonic()
        if remaining > 0 and stats['messages'] < max_messages and stats['connections'] < max_connections:
            sleep(min(remaining, min(30, 2 ** min(attempts, 5))))
    stats['live_continuity_demonstrated'] = stats['snapshots'] > 0 and stats['deltas'] > 0 and stats['usable_books'] > 0
    # This only describes captured protocol continuity, never sustained uptime or readiness.
    stats['status'] = 'CAPTURED' if stats['live_continuity_demonstrated'] and not stats['failures'] else 'INCOMPLETE'
    return stats
