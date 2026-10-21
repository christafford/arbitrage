"""Archival normalization and current-time inspection, without economic evaluation."""
from datetime import datetime, timedelta, timezone
import hashlib

from . import kalshi, polymarket_us
from .orderbooks import NORMALIZER_VERSION, normalize_rest, walk_depth
from .validation import dumps, load_json, utc_time

M3_SCHEMA = """
CREATE TABLE normalized_books (
 id INTEGER PRIMARY KEY, observation_id INTEGER NOT NULL REFERENCES raw_observations(id),
 metadata_observation_id INTEGER NOT NULL REFERENCES raw_observations(id), normalizer_version TEXT NOT NULL,
 evaluated_at TEXT NOT NULL, max_age_seconds INTEGER NOT NULL, data_usable INTEGER NOT NULL CHECK(data_usable IN (0,1)),
 result_json TEXT NOT NULL, verification TEXT NOT NULL CHECK(verification='UNVERIFIED')
);
CREATE INDEX normalized_books_observation ON normalized_books(observation_id,id);
"""


def _raw(con, observation_id):
    cursor = con.execute('SELECT * FROM raw_observations WHERE id=?', (observation_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError('raw observation not found')
    result = dict(zip((item[0] for item in cursor.description), row))
    if result['validation_status'] != 'VALID' or result['http_status'] != 200 or result['truncated']:
        raise ValueError('raw observation is not a complete validated HTTP snapshot')
    if result['raw_body'] is None or hashlib.sha256(result['raw_body']).hexdigest() != result['body_sha256']:
        raise ValueError('raw observation body hash mismatch or missing bytes')
    return result


def load_book(con, observation_id, *, now, metadata_observation_id=None):
    row = con.execute('SELECT run_id,source_id FROM book_captures WHERE observation_id=?', (observation_id,)).fetchone()
    if row is None:
        raise ValueError('observation is not an archived book capture')
    run_id, source_id = row
    if metadata_observation_id is None:
        saved = con.execute('SELECT metadata_observation_id FROM normalized_books WHERE observation_id=? ORDER BY id DESC LIMIT 1',
                            (observation_id,)).fetchone()
        if saved:
            metadata_observation_id = saved[0]
        else:
            # M1/M2 archive replay: only use preceding detail provenance from the same capture run.
            selected = con.execute('SELECT observation_id FROM catalogue_entries WHERE run_id=? AND source_id=?',
                                   (run_id, source_id)).fetchone()
            if not selected or selected[0] > observation_id:
                raise ValueError('matching preceding market detail observation required')
            metadata_observation_id = selected[0]
    if con.execute('SELECT 1 FROM catalogue_entries WHERE run_id=? AND source_id=? AND observation_id=?',
                   (run_id, source_id, metadata_observation_id)).fetchone() is None:
        raise ValueError('metadata must be bound to the same catalogue run and source')
    raw, meta = _raw(con, observation_id), _raw(con, metadata_observation_id)
    venue = raw['venue']
    adapter = {'kalshi': kalshi, 'polymarket_us': polymarket_us}.get(venue)
    if adapter is None or raw['schema_version'] != adapter.SCHEMA_VERSION or meta['schema_version'] != adapter.SCHEMA_VERSION:
        raise ValueError('unsupported provider schema version')
    if meta['venue'] != venue or raw['endpoint'] != adapter.book_url(source_id) or meta['endpoint'] != adapter.detail_url(source_id):
        raise ValueError('book/detail endpoint or venue mismatch; full snapshots are required')
    if utc_time(meta['ts_utc']) > utc_time(raw['ts_utc']):
        raise ValueError('metadata was retrieved after this book')
    payload, detail = load_json(raw['raw_body']), load_json(meta['raw_body'])
    adapter.validate_detail(detail)
    book = normalize_rest(venue, source_id, payload, detail['market'], received_at=raw['ts_utc'],
                          metadata_received_at=meta['ts_utc'], now=now)
    return book, metadata_observation_id, run_id


def record_normalization(con, observation_id, metadata_observation_id, *, now=None, max_age=60):
    now = now or datetime.now(timezone.utc)
    try:
        book, _, _ = load_book(con, observation_id, now=now, metadata_observation_id=metadata_observation_id)
        result = book.as_dict(now=now, max_age=max_age)
    except ValueError as exc:
        result = {'data_usable': False, 'rejections': ['INVALID_PROVENANCE_OR_SCHEMA: ' + str(exc)],
                  'normalizer_version': NORMALIZER_VERSION, 'verification': 'UNVERIFIED', 'trading_authorized': False}
    con.execute('''INSERT INTO normalized_books(observation_id,metadata_observation_id,normalizer_version,
                   evaluated_at,max_age_seconds,data_usable,result_json,verification) VALUES(?,?,?,?,?,?,?,'UNVERIFIED')''',
                (observation_id, metadata_observation_id, NORMALIZER_VERSION, now.isoformat(), max_age,
                 int(result['data_usable']), dumps(result)))
    con.commit()
    return result


def inspect_book(con, observation_id, *, now=None, max_age=60, side=None, quantity=None):
    now = now or datetime.now(timezone.utc)
    book, metadata_id, run_id = load_book(con, observation_id, now=now)
    result = book.as_dict(now=now, max_age=max_age)
    status = con.execute('SELECT status FROM collection_runs WHERE id=?', (run_id,)).fetchone()[0]
    reasons = list(result['rejections'])
    if status not in {'COMPLETE', 'PARTIAL'}:
        reasons.append('SOURCE_RUN_NOT_COMPLETE')
    # A newly captured book supersedes older depth; --at historical replay excludes future observations.
    for candidate_id, retrieved in con.execute('''SELECT b.observation_id,r.ts_utc FROM book_captures b
            JOIN raw_observations r ON r.id=b.observation_id WHERE r.venue=? AND b.source_id=?
            AND b.observation_id>?''', (book.venue, book.source_id, observation_id)):
        if utc_time(retrieved) <= now:
            reasons.append('SUPERSEDED_BOOK')
            break
    # Do not silently apply an older tick/lot/state mapping after newer metadata was collected.
    current = con.execute('''SELECT c.observation_id,r.ts_utc FROM catalogue_entries c
        JOIN raw_observations r ON r.id=c.observation_id WHERE r.venue=? AND c.source_id=?
        AND c.observation_id>?''', (book.venue, book.source_id, metadata_id)).fetchall()
    if any(utc_time(retrieved) <= now for _, retrieved in current):
        reasons.append('NEWER_METADATA_REQUIRES_FRESH_BOOK')
    result.update(observation_id=observation_id, metadata_observation_id=metadata_id,
                  rejections=tuple(dict.fromkeys(reasons)), data_usable=not reasons, evaluated_at=now.isoformat())
    if side is not None or quantity is not None:
        if side is None or quantity is None:
            raise ValueError('both side and quantity are required for depth coverage')
        if reasons:
            raise ValueError('book rejected: ' + '; '.join(reasons))
        from dataclasses import asdict
        result['hypothetical_depth'] = asdict(walk_depth(book, side, quantity, now=now, max_age=max_age))
    return result


def inspect_pair(con, pair_id, kalshi_observation_id, us_observation_id, *, now=None, max_age=60, max_skew_ms=2000):
    from .registry import review
    now = now or datetime.now(timezone.utc)
    if type(max_skew_ms) is not int or not 0 <= max_skew_ms <= 60000:
        raise ValueError('max_skew_ms must be an integer in 0..60000')
    pair = review(con, pair_id, now=now)
    books = [inspect_book(con, item, now=now, max_age=max_age) for item in (kalshi_observation_id, us_observation_id)]
    reasons = []
    if pair['status'] != 'APPROVED': reasons.append('PAIR_NOT_APPROVED')
    # Current HTTP collectors archive real provider data; synthetic registry examples cannot qualify it.
    if pair['hypothetical']: reasons.append('HYPOTHETICAL_PAIR_WITH_LIVE_CAPTURE')
    for data, venue, source_id in zip(books, ('kalshi', 'polymarket_us'), (pair['kalshi_id'], pair['polymarket_us_id'])):
        if data['venue'] != venue or data['source_id'] != source_id: reasons.append('PAIR_BOOK_IDENTITY_MISMATCH')
        if not data['data_usable']: reasons.append(venue.upper() + '_BOOK_REJECTED')
    for key in ('received_at', 'source_ts'):
        if any(data[key] is None for data in books): reasons.append('MISSING_COMPARABLE_SOURCE_TIME')
        elif abs(utc_time(books[0][key]) - utc_time(books[1][key])) > timedelta(milliseconds=max_skew_ms):
            reasons.append('EXCESSIVE_' + key.upper() + '_SKEW')
    return {'pair_id': pair_id, 'comparison_ready': not reasons, 'rejections': tuple(dict.fromkeys(reasons)),
            'books': books, 'trading_authorized': False, 'fees_or_profit_evaluated': False}
