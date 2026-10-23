"""Resumable read-only research cycles, audit, aggregates and bounded detail retention."""
import csv
from shutil import disk_usage
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
from decimal import Decimal, localcontext

from . import registry, mechanics
from .book_store import inspect_pair, load_book
from .economics import evaluate, policy, seconds
from .fee_store import current_profile
from .validation import dumps, load_json, utc_time


def clock():
    return datetime.now(timezone.utc)


def audit(con, action, detail, now):
    con.execute('INSERT INTO research_audit(ts_utc,action,detail_json) VALUES(?,?,?)',
                (now.isoformat(), action, dumps(detail)))


def session(con, session_id):
    row = con.execute('SELECT started_at,target_end,mode,config_json,interval_seconds FROM research_sessions WHERE id=?',
                      (session_id,)).fetchone()
    if row is None:
        raise ValueError('research session not found')
    return dict(zip(('started_at', 'target_end', 'mode', 'config', 'interval_seconds'), row)) | {'config': load_json(row[3])}


def start_session(con, config, *, interval_seconds=60, now=None, hypothetical=False):
    now = now or clock()
    policy(config)
    if type(interval_seconds) is not int or not 1 <= interval_seconds <= 3600:
        raise ValueError('interval must be 1..3600 seconds')
    if hypothetical:
        if con.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0] or con.execute(
                'SELECT COUNT(*) FROM rule_versions WHERE hypothetical=0').fetchone()[0]:
            raise ValueError('hypothetical replay requires an isolated database')
    elif con.execute('SELECT COUNT(*) FROM research_sessions WHERE mode=?', ('HYPOTHETICAL_REPLAY',)).fetchone()[0]:
        raise ValueError('cannot mix live research with hypothetical replay')
    cursor = con.execute('''INSERT INTO research_sessions(started_at,target_end,mode,config_json,interval_seconds)
        VALUES(?,?,?,?,?)''', (now.isoformat(), (now + timedelta(days=30)).isoformat(),
                              'HYPOTHETICAL_REPLAY' if hypothetical else 'LIVE_READ_ONLY', dumps(config), interval_seconds))
    audit(con, 'SESSION_STARTED', {'session_id': cursor.lastrowid, 'hypothetical': hypothetical}, now)
    con.commit()
    return cursor.lastrowid


def archive_replay(con, raw, *, now):
    """Archive original hypothetical bytes before any decoding. Isolated replay only."""
    if con.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0] or con.execute(
            'SELECT COUNT(*) FROM rule_versions WHERE hypothetical=0').fetchone()[0]:
        raise ValueError('replay requires an isolated database')
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 2000000:
        raise ValueError('replay must contain 1..2000000 bytes')
    observed = con.execute('INSERT INTO research_replays(imported_at,raw_bytes,sha256) VALUES(?,?,?)',
                           (now.isoformat(), raw, sha256(raw).hexdigest())).lastrowid
    con.commit()
    return observed


def replay_books(con, replay_id, *, now):
    from .book_stream import KalshiBookStream
    from .orderbooks import normalize_rest
    row = con.execute('SELECT raw_bytes,sha256 FROM research_replays WHERE id=?', (replay_id,)).fetchone()
    if not row or sha256(row[0]).hexdigest() != row[1]:
        raise ValueError('invalid replay provenance')
    data = load_json(row[0])
    if data['hypothetical'] is not True:
        raise ValueError('explicit hypothetical replay required')
    k, p, received = data['kalshi_metadata'], data['polymarket_us_metadata'], data['clock']
    if not all(value.startswith('HYPOTHETICAL-') for value in (k['ticker'], p['slug'])):
        raise ValueError('hypothetical replay identities required')
    stream = KalshiBookStream(k['ticker'], k, metadata_received_at=received)
    kalshi_book = stream.apply(data['kalshi_ws_snapshot'], received_at=received, now=now, generation=stream.generation)
    us_book = normalize_rest('polymarket_us', p['slug'], data['polymarket_us_rest'], p,
                             received_at=received, metadata_received_at=received, now=now)
    return [kalshi_book, us_book], row[1]


def _latest(con, venue, source_id, now):
    rows = con.execute('''SELECT b.observation_id,r.ts_utc FROM book_captures b
        JOIN raw_observations r ON r.id=b.observation_id WHERE r.venue=? AND b.source_id=?
        ORDER BY b.observation_id DESC''', (venue, source_id))
    for observed, stamp in rows:
        if utc_time(stamp) <= now:
            return observed
    raise ValueError('MISSING_BOOK: ' + venue)


def _refresh(con, pair):
    from .collector import collect
    from . import kalshi, polymarket_us
    contract = pair['instruments'][0]['evidence']['contract']
    collect(con, kalshi, scope=contract['event_ticker'], page_size=100, max_pages=10,
            selected=(pair['kalshi_id'],), books=1)
    collect(con, polymarket_us, scope=pair['polymarket_us_id'], page_size=20, max_pages=2,
            selected=(pair['polymarket_us_id'],), books=1)


def _result(con, pair_id, config, *, now, refresh=False, replay=None):
    detail = {'pair_id': pair_id, 'evaluated_at': now.isoformat(), 'verification': 'UNVERIFIED',
              'trading_authorized': False}
    try:
        pair = registry.review(con, pair_id, now=now)
        detail['registry'] = pair
        if pair['status'] != 'APPROVED' or pair['approval_blocker']:
            raise ValueError('PAIR_NOT_CURRENTLY_APPROVED')
        if pair['hypothetical'] != (replay is not None):
            raise ValueError('HYPOTHETICAL_LIVE_SEPARATION')
        if refresh:
            _refresh(con, pair)
            now = clock()
            pair = registry.review(con, pair_id, now=now)
            detail.update(evaluated_at=now.isoformat(), registry=pair)
            if pair['status'] != 'APPROVED' or pair['approval_blocker']:
                raise ValueError('PAIR_INVALIDATED_DURING_REFRESH')
        if replay is None:
            ids = [_latest(con, venue, source, now) for venue, source in
                   zip(('kalshi', 'polymarket_us'), (pair['kalshi_id'], pair['polymarket_us_id']))]
            quality = inspect_pair(con, pair_id, *ids, now=now)
            detail['comparison'] = quality
            if not quality['comparison_ready']:
                raise ValueError('INCOMPARABLE_BOOKS: ' + ';'.join(quality['rejections']))
            books = [load_book(con, observed, now=now)[0] for observed in ids]
        else:
            books = replay[pair_id]
            if any(not book.source_id.startswith('HYPOTHETICAL-') for book in books):
                raise ValueError('hypothetical book identity required')
            expected = (pair['kalshi_id'], pair['polymarket_us_id'])
            if tuple(book.source_id for book in books) != expected:
                raise ValueError('PAIR_BOOK_IDENTITY_MISMATCH')
            for key in ('received_at', 'source_ts'):
                stamps = [getattr(book, key) for book in books]
                if any(stamp is None for stamp in stamps) or abs(utc_time(stamps[0]) - utc_time(stamps[1])) > timedelta(seconds=2):
                    raise ValueError('INCOMPARABLE_REPLAY_CLOCKS')
            detail['hypothetical_books'] = [book.as_dict(now=now) for book in books]
        sides = [pair['review']['legs'][venue] for venue in ('kalshi', 'polymarket_us')]
        models, provenance = [], []
        for book, side in zip(books, sides):
            model, evidence = current_profile(con, book.venue, book.source_id, side, now=now, hypothetical=pair['hypothetical'])
            models.append(model)
            provenance.append(evidence)
        detail['fee_profiles'] = provenance
        scenarios = pair['review']['settlement_scenarios']
        settlement = [max((row[venue + '_settlement_at'] for row in scenarios), key=utc_time)
                      for venue in ('kalshi', 'polymarket_us')]
        # Never rely solely on cached human status when computing a fixed combined payout.
        for row in scenarios:
            if Decimal(row['kalshi_payout']) + Decimal(row['polymarket_us_payout']) != 1:
                raise ValueError('UNSUPPORTED_REVIEWED_PAYOUT')
        explicit_mechanics = not pair['hypothetical'] or 'mechanics' in pair['review']
        if explicit_mechanics:
            mechanics.validate_review(pair['review'], pair, now=now)
        detail['mechanics'] = pair['mechanics_assessment']
        result = evaluate(books, sides, models, settlement, config, now=now,
                          payout_scenarios=scenarios if explicit_mechanics else None)
        quote = [{'venue': book.venue, 'source_id': book.source_id, 'side': side,
                  'levels': [(str(level.price), str(level.quantity)) for level in
                             (book.yes_asks if side == 'YES' else book.no_asks)]} for book, side in zip(books, sides)]
        result['quote_sha256'] = sha256(dumps(quote).encode()).hexdigest()
        return result, detail
    except (ValueError, KeyError, OSError) as exc:
        return {'status': 'REJECTED', 'rejections': [str(exc)], 'best': None,
                'verification': 'UNVERIFIED', 'trading_authorized': False}, detail


def scan_once(con, session_id, *, now=None, refresh=False, replay_id=None):
    current = session(con, session_id)
    now = now or clock()
    hypothetical = current['mode'] == 'HYPOTHETICAL_REPLAY'
    if hypothetical != (replay_id is not None) or (hypothetical and refresh):
        raise ValueError('session mode mismatch; no hypothetical refresh')
    if hypothetical and (con.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0] or
                         con.execute('SELECT COUNT(*) FROM rule_versions WHERE hypothetical=0').fetchone()[0]):
        raise ValueError('hypothetical replay database contaminated by live evidence')
    database_file = con.execute('PRAGMA database_list').fetchone()[2]
    if database_file and disk_usage(database_file).free < 200 * 1024 * 1024:
        raise ValueError('insufficient free disk space; require 200 MiB before research cycle')
    previous = con.execute('SELECT evaluated_at FROM research_cycles WHERE session_id=? ORDER BY id DESC LIMIT 1',
                           (session_id,)).fetchone()
    if now < utc_time(current['started_at']) or (previous and now <= utc_time(previous[0])):
        raise ValueError('research cycle clock must advance')
    audit(con, 'CYCLE_STARTED', {'session_id': session_id, 'refresh': refresh, 'hypothetical': hypothetical}, now)
    con.commit()
    replay = None
    replay_sha = None
    if hypothetical:
        books, replay_sha = replay_books(con, replay_id, now=now)
        replay = {row[0]: books for row in con.execute('SELECT id FROM pairs')}
    rows = []
    pair_ids = [row[0] for row in con.execute('SELECT id FROM pairs ORDER BY id')]
    # Limit resource use explicitly; never silently omit the tail of a registry.
    if len(pair_ids) > 50:
        raise ValueError('registry exceeds bounded 50-pair research scope')
    for pair_id in pair_ids:
        result, detail = _result(con, pair_id, current['config'], now=now, refresh=refresh, replay=replay)
        full = detail | {'economics': result, 'hypothetical': hypothetical,
                         'replay_observation_id': replay_id, 'replay_sha256': replay_sha}
        encoded = dumps(full)
        rows.append((pair_id, result, detail['evaluated_at'], encoded))
    cycle_summary = {'pairs_observed': len(rows), 'modeled_edges': sum(row[1]['status'] == 'MODELED_EDGE' for row in rows),
                     'rejected': sum(row[1]['status'] == 'REJECTED' for row in rows), 'hypothetical': hypothetical,
                     'no_pairs': not rows, 'trading_authorized': False}
    # Full details and durable summaries commit atomically. Source archives commit earlier.
    con.execute('BEGIN IMMEDIATE')
    try:
        cycle_id = con.execute('''INSERT INTO research_cycles(session_id,evaluated_at,recorded_at,status,summary_json)
            VALUES(?,?,?,?,?)''', (session_id, now.isoformat(), clock().isoformat(), 'COMPLETE', dumps(cycle_summary))).lastrowid
        for pair_id, result, evaluated_at, encoded in rows:
            evaluation_id = con.execute('''INSERT INTO research_evaluations(cycle_id,pair_id,evaluated_at,status,
                reasons_json,summary_json,detail_sha256) VALUES(?,?,?,?,?,?,?)''',
                (cycle_id, pair_id, evaluated_at, result['status'], dumps(result['rejections']), dumps(result),
                 sha256(encoded.encode()).hexdigest())).lastrowid
            con.execute('INSERT INTO research_details VALUES(?,?)', (evaluation_id, encoded))
        audit(con, 'CYCLE_FINISHED', {'session_id': session_id, 'cycle_id': cycle_id, **cycle_summary}, now)
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return cycle_summary | {'cycle_id': cycle_id}


def summary(con, session_id):
    current = session(con, session_id)
    cycles = con.execute('SELECT evaluated_at FROM research_cycles WHERE session_id=? ORDER BY id', (session_id,))
    evaluations = con.execute('''SELECT e.pair_id,e.evaluated_at,e.status,e.reasons_json,e.summary_json
        FROM research_evaluations e JOIN research_cycles c ON c.id=e.cycle_id WHERE c.session_id=? ORDER BY e.id''', (session_id,))
    reasons, latest, previous = {}, {}, {}
    persistence = {}
    for pair_id, stamp, status, rejection_json, encoded in evaluations:
        data = load_json(encoded)
        for reason in load_json(rejection_json):
            reasons[reason] = reasons.get(reason, 0) + 1
        older = previous.get(pair_id)
        quote = data.get('quote_sha256')
        if older and quote and quote == older[1]:
            delta = seconds(utc_time(stamp) - utc_time(older[0]))
            if 0 < delta <= 2 * current['interval_seconds']:
                sample = persistence.setdefault(pair_id, {'pair_id': pair_id, 'seconds_between_equal_samples': Decimal('0'),
                                                         'equal_sample_pairs': 0, 'continuous_lifespan_verified': False})
                sample['seconds_between_equal_samples'] = max(sample['seconds_between_equal_samples'], delta)
                sample['equal_sample_pairs'] += 1
        previous[pair_id] = (stamp, quote)
        latest[pair_id] = data | {'pair_id': pair_id, 'evaluated_at': stamp}
    first = last = None
    count = 0
    max_gap = Decimal('0')
    for (stamp,) in cycles:
        when = utc_time(stamp)
        if last is not None: max_gap = max(max_gap, seconds(when - last))
        first = first or when
        last = when
        count += 1
    span = seconds(last - first) if first is not None else Decimal('0')
    expected = int(span // current['interval_seconds']) + 1
    coverage = min(Decimal('1'), Decimal(count) / expected) if count else Decimal('0')
    ranking = sorted((data for data in latest.values() if data.get('best')),
                     key=lambda data: Decimal(data['best']['profit_per_capital_day']), reverse=True)
    attempts = con.execute("SELECT COUNT(*) FROM research_audit WHERE action='CYCLE_STARTED' AND json_extract(detail_json,'$.session_id')=?",
                           (session_id,)).fetchone()[0]
    qualifies = (current['mode'] == 'LIVE_READ_ONLY' and span >= 30 * 86400 and coverage >= Decimal('.95')
                 and max_gap <= 2 * current['interval_seconds'] and bool(persistence) and attempts == count)
    return {'session_id': session_id, 'mode': current['mode'], 'cycles': count, 'observed_span_seconds': span,
            'cadence_coverage': coverage, 'largest_gap_seconds': max_gap,
            'rejection_counts': reasons, 'latest_ranked_independent_alternatives': ranking,
            'equal_quote_samples': list(persistence.values()), 'continuous_quote_lifespan_verified': False,
            'unfinished_cycle_attempts': attempts - count, 'observed_window_qualifies_for_audit': qualifies,
            'thirty_day_acceptance': False,  # Requires an actual reviewed observation audit, not elapsed time alone.
            'acceptance_blockers': ['30_DAY_OBSERVATION_AND_EVIDENCE_AUDIT_PENDING'] +
                                   (['HYPOTHETICAL_REPLAY_IS_NOT_LIVE_EVIDENCE'] if current['mode'] == 'HYPOTHETICAL_REPLAY' else []),
            'verification': 'UNVERIFIED', 'trading_authorized': False}


def export_csv(con, session_id):
    session(con, session_id)
    rows = con.execute('''SELECT e.id,e.pair_id,e.evaluated_at,e.status,e.reasons_json,e.summary_json,e.detail_sha256,s.mode
        FROM research_evaluations e JOIN research_cycles c ON c.id=e.cycle_id JOIN research_sessions s ON s.id=c.session_id
        WHERE s.id=? ORDER BY e.id''', (session_id,)).fetchall()
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(('evaluation_id', 'pair_id', 'evaluated_at', 'status', 'rejections', 'contracts', 'net_profit_bound',
                     'total_capital', 'locked_capital_days', 'detail_sha256', 'mode', 'trading_authorized'))
    for eid, pair_id, stamp, status, reasons, encoded, digest, mode in rows:
        best = load_json(encoded).get('best') or {}
        values = [eid, pair_id, stamp, status, reasons, best.get('contracts', ''), best.get('net_profit_bound', ''),
                  best.get('total_capital', ''), best.get('locked_capital_days', ''), digest, mode, False]
        writer.writerow(["'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')) else value for value in values])
    return output.getvalue()


def prune_details(con, *, now=None, keep_days=31, apply=False):
    now = now or clock()
    if type(keep_days) is not int or keep_days < 31:
        raise ValueError('retain at least 31 days of derived details')
    cutoff = now - timedelta(days=keep_days)
    rows = con.execute('''SELECT d.evaluation_id,e.evaluated_at FROM research_details d
        JOIN research_evaluations e ON e.id=d.evaluation_id''').fetchall()
    ids = [eid for eid, stamp in rows if utc_time(stamp) < cutoff]
    if apply:
        con.execute('BEGIN IMMEDIATE')
        try:
            con.executemany('DELETE FROM research_details WHERE evaluation_id=?', [(eid,) for eid in ids])
            audit(con, 'DERIVED_DETAILS_PRUNED', {'evaluation_ids': ids, 'cutoff': cutoff.isoformat(), 'keep_days': keep_days}, now)
            con.commit()
        except BaseException:
            con.rollback()
            raise
    return {'candidate_details': len(ids), 'applied': apply, 'summaries_and_source_evidence_retained': True}
