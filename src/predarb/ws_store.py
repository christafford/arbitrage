"""Archived Kalshi frames, connection boundaries and bounded deterministic replay."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import re

from . import kalshi
from .book_stream import KalshiBookStream, validate_protocol
from .kalshi_auth import WS_URL
from .store import archive_response, validate_observation
from .validation import dumps, load_json, utc_time

SCHEMA_VERSION = 'kalshi-ws/m5a-v1'
PROTOCOL_SCHEMAS = {'clocked': SCHEMA_VERSION, 'sequence-v1': 'kalshi-ws/m5a-sequence-v1'}
MAX_FRAMES = 1000
SCHEMA = """
CREATE TABLE ws_connections (
 id INTEGER PRIMARY KEY, source_id TEXT NOT NULL,
 run_id INTEGER NOT NULL REFERENCES collection_runs(id),
 metadata_observation_id INTEGER NOT NULL REFERENCES raw_observations(id),
 started_at TEXT NOT NULL, ended_at TEXT, end_reason TEXT
);
CREATE TABLE ws_frames (
 observation_id INTEGER PRIMARY KEY REFERENCES raw_observations(id),
 connection_id INTEGER NOT NULL REFERENCES ws_connections(id),
 wire_sha256 TEXT NOT NULL, archive_kind TEXT NOT NULL
);
CREATE INDEX ws_frames_connection ON ws_frames(connection_id,observation_id);
"""


def safe_frame(body, secrets=()):
    """Security screening precedes archival; normalization always follows archival.

    Public-shaped frames retain exact wire bytes. Account enrichment is removed;
    unknown/error/malformed bodies retain only their hash and a local marker.
    """
    raw = body.encode() if isinstance(body, str) else body
    digest = hashlib.sha256(raw).hexdigest()
    marker = dumps({'type': 'REDACTED_UNSAFE_FRAME'}).encode()
    if len(raw) > 1_000_000 or any(secret.encode() in raw for secret in secrets if secret):
        return marker, digest, 'REDACTED'
    try:
        frame = load_json(raw)
        if any(secret in dumps(frame) for secret in secrets if secret):
            return marker, digest, 'REDACTED'
        kind = frame.get('type')
        if kind not in {'subscribed', 'orderbook_snapshot', 'orderbook_delta'}:
            return marker, digest, 'REDACTED'
        allowed = {'type', 'id', 'sid', 'seq', 'sending_ts_ms', 'msg'}
        if not set(frame) <= allowed or type(frame.get('msg')) is not dict:
            return marker, digest, 'REDACTED'
        for key, value in frame.items():
            if key not in {'type', 'msg'} and type(value) is not int:
                return marker, digest, 'REDACTED'
        message = dict(frame['msg'])
        redacted = 'client_order_id' in message
        message.pop('client_order_id', None)
        strings = {'market_ticker', 'market_id', 'side', 'channel', 'price_dollars', 'delta_fp', 'ts'}
        integers = {'clock', 'ts_ms', 'sid'}
        ladders = {'yes_dollars_fp', 'no_dollars_fp'}
        if not set(message) <= strings | integers | ladders:
            return marker, digest, 'REDACTED'
        for key, value in message.items():
            if key in strings:
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:+\-]{1,250}', value):
                    return marker, digest, 'REDACTED'
            elif key in integers:
                if type(value) is not int:
                    return marker, digest, 'REDACTED'
            elif type(value) is not list or any(type(level) is not list or len(level) != 2 or
                    any(not isinstance(item, str) or not re.fullmatch(r'-?[0-9.]{1,40}', item)
                        for item in level) for level in value):
                return marker, digest, 'REDACTED'
        if redacted:
            frame['msg'] = message
            return dumps(frame).encode(), digest, 'ACCOUNT_FIELD_REMOVED'
        return raw, digest, 'EXACT_WIRE'
    except (ValueError, TypeError, AttributeError, RecursionError):
        return marker, digest, 'REDACTED'


def begin_connection(con, source_id, run_id, metadata_id, *, at):
    cursor = con.execute('''INSERT INTO ws_connections(source_id,run_id,metadata_observation_id,started_at)
                            VALUES(?,?,?,?)''', (source_id, run_id, metadata_id, at))
    con.commit()
    return cursor.lastrowid


def connection(con, connection_id):
    row = con.execute('''SELECT source_id,run_id,metadata_observation_id,started_at,ended_at,end_reason
                        FROM ws_connections WHERE id=?''', (connection_id,)).fetchone()
    if row is None:
        raise ValueError('missing stream connection')
    return row


def archive_frame(con, connection_id, body, *, at, secrets=(), protocol='clocked'):
    if protocol not in PROTOCOL_SCHEMAS:
        raise ValueError('unknown Kalshi stream protocol')
    safe, wire_hash, kind = safe_frame(body, secrets)
    observed = archive_response(con, 'kalshi', WS_URL, safe, 101, {}, at, PROTOCOL_SCHEMAS[protocol])
    con.execute('INSERT INTO ws_frames VALUES(?,?,?,?)', (observed, connection_id, wire_hash, kind))
    # Every frame is a pending barrier until validated, including a crash between writes.
    source, run, *_ = connection(con, connection_id)
    con.execute("INSERT INTO book_captures VALUES(?,?,?,?,?,?,'UNVERIFIED')",
                (observed, run, source, None, 'UNVERIFIED_STREAM', 'UNKNOWN'))
    con.commit()
    return observed, safe, kind


def end_connection(con, connection_id, *, at, reason):
    # Only local fixed reason codes are stored, never transport exception messages.
    con.execute('UPDATE ws_connections SET ended_at=?,end_reason=? WHERE id=? AND ended_at IS NULL',
                (at, reason, connection_id))
    con.commit()


def record_frame(con, observed, book, *, now):
    validate_observation(con, observed, 'VALID', None, book.source_ts)
    result = book.as_dict(now=now)
    con.execute('UPDATE book_captures SET source_ts=?,freshness=?,liquidity=? WHERE observation_id=?',
                (book.source_ts, 'FRESH' if result['data_usable'] else 'REJECTED',
                 'TWO_SIDED' if book.yes_asks and book.no_asks else 'PARTIAL_OR_EMPTY', observed))
    metadata_id = con.execute('''SELECT c.metadata_observation_id FROM ws_frames f JOIN ws_connections c
                               ON c.id=f.connection_id WHERE f.observation_id=?''', (observed,)).fetchone()[0]
    con.execute('''INSERT INTO normalized_books(observation_id,metadata_observation_id,normalizer_version,
                   evaluated_at,max_age_seconds,data_usable,result_json,verification) VALUES(?,?,?,?,?,?,?,'UNVERIFIED')''',
                (observed, metadata_id, result['normalizer_version'], now.isoformat(), 60,
                 int(result['data_usable']), dumps(result)))
    con.commit()


def load_stream_book(con, observation_id, *, now):
    from .book_store import _raw
    row = con.execute('SELECT connection_id FROM ws_frames WHERE observation_id=?', (observation_id,)).fetchone()
    if row is None:
        raise ValueError('missing stream frame provenance')
    connection_id = row[0]
    source, run, metadata_id, started, ended, reason = connection(con, connection_id)
    meta = _raw(con, metadata_id)
    if meta['venue'] != 'kalshi' or meta['schema_version'] != kalshi.SCHEMA_VERSION or meta['endpoint'] != kalshi.detail_url(source):
        raise ValueError('stream metadata provenance mismatch')
    if not utc_time(meta['ts_utc']) <= utc_time(started) <= now:
        raise ValueError('stream metadata/connection clock mismatch')
    if con.execute('SELECT 1 FROM catalogue_entries WHERE run_id=? AND source_id=? AND observation_id=?',
                   (run, source, metadata_id)).fetchone() is None:
        raise ValueError('stream metadata run mismatch')
    detail = load_json(meta['raw_body']); kalshi.validate_detail(detail)
    rows = con.execute('''SELECT r.id,r.ts_utc,r.raw_body,r.body_sha256,r.validation_status,r.schema_version,
                         r.endpoint,r.http_status,r.truncated,f.archive_kind,f.wire_sha256
                         FROM ws_frames f JOIN raw_observations r ON r.id=f.observation_id
                         WHERE f.connection_id=? AND r.id<=? ORDER BY r.id LIMIT ?''',
                       (connection_id, observation_id, MAX_FRAMES + 2)).fetchall()
    if not rows or len(rows) > MAX_FRAMES + 1 or rows[-1][0] != observation_id:
        raise ValueError('stream replay exceeds bound or is incomplete')
    schema_version = rows[0][5]
    protocol = next((name for name, version in PROTOCOL_SCHEMAS.items() if version == schema_version), None)
    validate_protocol(protocol, now)
    stream = KalshiBookStream(source, detail['market'], metadata_received_at=meta['ts_utc'], protocol=protocol)
    stream.generation = connection_id
    book, previous_receipt, sid = None, utc_time(started), None
    for observed, receipt, body, sha, status, schema, endpoint, http, truncated, kind, wire_sha in rows:
        if (status != 'VALID' or schema != schema_version or endpoint != WS_URL or http != 101 or
                truncated or body is None or hashlib.sha256(body).hexdigest() != sha or
                kind not in {'EXACT_WIRE', 'ACCOUNT_FIELD_REMOVED'} or
                (kind == 'EXACT_WIRE' and sha != wire_sha)):
            raise ValueError('invalid stream frame provenance or continuity')
        received = utc_time(receipt)
        if not previous_receipt <= received <= now:
            raise ValueError('stream receipt clock regressed or is in the future')
        previous_receipt = received
        frame = load_json(body)
        if frame['type'] == 'subscribed':
            if sid is not None or book is not None or frame.get('id') != 1 or frame['msg'].get('channel') != 'orderbook_delta':
                raise ValueError('invalid subscription acknowledgment')
            sid = frame['msg'].get('sid')
            if type(sid) is not int or sid < 1:
                raise ValueError('invalid subscription id')
            continue
        if sid is None or frame.get('sid') != sid:
            raise ValueError('unacknowledged stream subscription')
        book = stream.apply(frame, received_at=receipt, now=received, generation=connection_id)
        # A stale historical frame cannot be repaired by a later delta.
        if any(issue not in {'EMPTY_BOOK', 'PARTIAL_BOOK'} for issue in book.issues(now=received)):
            raise ValueError('stream source/metadata freshness failed during replay')
    if book is None:
        raise ValueError('stream has no snapshot')
    extra = ()
    if ended is not None and utc_time(ended) <= now:
        extra += ('STREAM_DISCONNECTED',)
    # A stopped/crashed writer cannot leave a reusable book for the full M3 age window.
    if now - utc_time(book.received_at) >= timedelta(seconds=5):
        extra += ('STREAM_LIVENESS_NOT_DEMONSTRATED',)
    return replace(book, transport='KALSHI_AUTHENTICATED_WS', rejections=book.rejections + extra), metadata_id, run
