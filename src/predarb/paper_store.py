"""Paper intents sourced only from gated M4 evaluations; later quote comparisons."""
from datetime import datetime, timezone
from hashlib import sha256

from . import registry
from .book_store import inspect_pair, load_book
from .fee_store import current_profile
from .paper import policy, simulate
from .research import _latest, replay_books
from .validation import dumps, field, load_json, text_field, utc_time


def digest(value):
    return sha256(dumps(value).encode()).hexdigest()


def _context(con, detail, *, now):
    pair = registry.review(con, detail['pair_id'], now=now)
    if (pair['status'] != 'APPROVED' or pair['approval_blocker'] or pair['evidence_sha256'] != detail['registry']['evidence_sha256']
            or pair['review'] != detail['registry']['review']):
        raise ValueError('PAPER_PAIR_APPROVAL_CHANGED_OR_EXPIRED')
    if pair['hypothetical'] != detail['hypothetical']:
        raise ValueError('paper mode mismatch')
    sides = [pair['review']['legs'][venue] for venue in ('kalshi', 'polymarket_us')]
    models = []
    for old, venue, source, side in zip(detail['fee_profiles'], ('kalshi', 'polymarket_us'),
                                       (pair['kalshi_id'], pair['polymarket_us_id']), sides):
        model, current = current_profile(con, venue, source, side, now=now, hypothetical=pair['hypothetical'])
        if (current['id'], current['sha256']) != (old['id'], old['sha256']):
            raise ValueError('PAPER_FEE_APPLICABILITY_CHANGED')
        models.append(model)
    return pair, sides, models


def _initial(con, detail, *, now, check_current):
    if detail['hypothetical']:
        if con.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0] or con.execute(
                'SELECT COUNT(*) FROM rule_versions WHERE hypothetical=0').fetchone()[0]:
            raise ValueError('paper replay database contains live evidence')
        books, raw_sha = replay_books(con, detail['replay_observation_id'], now=now)
        if raw_sha != detail['replay_sha256']:
            raise ValueError('paper replay provenance mismatch')
        return books
    ids = [row['observation_id'] for row in detail['comparison']['books']]
    if check_current:
        current = inspect_pair(con, detail['pair_id'], *ids, now=now)
        if not current['comparison_ready']:
            raise ValueError('initial paper comparison is no longer usable')
    return [load_book(con, observed, now=now)[0] for observed in ids]


def create_intent(con, evaluation_id, config, *, now=None):
    now = now or datetime.now(timezone.utc)
    policy(config)
    row = con.execute('''SELECT e.status,e.detail_sha256,d.detail_json,s.mode,s.config_json,e.evaluated_at
        FROM research_evaluations e JOIN research_details d ON d.evaluation_id=e.id
        JOIN research_cycles c ON c.id=e.cycle_id JOIN research_sessions s ON s.id=c.session_id
        WHERE e.id=?''', (evaluation_id,)).fetchone()
    if not row or row[0] != 'MODELED_EDGE':
        raise ValueError('positive retained M4 evaluation required; no unreviewed paper intents')
    if sha256(row[2].encode()).hexdigest() != row[1]:
        raise ValueError('M4 detail hash mismatch')
    detail = load_json(row[2])
    if detail['hypothetical'] != (row[3] == 'HYPOTHETICAL_REPLAY'):
        raise ValueError('M4 paper mode mismatch')
    evaluated = utc_time(row[5])
    if not evaluated <= now or (now - evaluated).total_seconds() > 60:
        raise ValueError('paper intent requires a fresh causal M4 evaluation')
    _context(con, detail, now=now)
    initial = _initial(con, detail, now=now, check_current=True)
    if any(book.issues(now=now) for book in initial):
        raise ValueError('initial paper books rejected')
    if any(book.source_ts is None or utc_time(book.source_ts) > now or utc_time(book.received_at) > now for book in initial):
        raise ValueError('causal initial book timestamps required')
    snapshot = {'detail': detail, 'source_detail_sha256': row[1], 'research_policy': load_json(row[4])}
    encoded, config_json = dumps(snapshot), dumps(config)
    previous = con.execute('SELECT id FROM paper_intents WHERE evaluation_id=? AND policy_sha256=?',
                            (evaluation_id, digest(config))).fetchone()
    if previous:
        return previous[0]
    intent_id = con.execute('''INSERT INTO paper_intents(evaluation_id,created_at,mode,policy_json,policy_sha256,input_json,input_sha256)
        VALUES(?,?,?,?,?,?,?)''', (evaluation_id, now.isoformat(), row[3], config_json, digest(config), encoded,
                                  sha256(encoded.encode()).hexdigest())).lastrowid
    con.commit()
    return intent_id


def archive_ticks(con, raw, *, now):
    if con.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0] or con.execute(
            'SELECT COUNT(*) FROM rule_versions WHERE hypothetical=0').fetchone()[0]:
        raise ValueError('hypothetical tick import requires isolated storage')
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 2000000:
        raise ValueError('tick input must contain 1..2000000 bytes')
    observed = con.execute('INSERT INTO paper_tick_inputs(imported_at,raw_bytes,sha256) VALUES(?,?,?)',
                           (now.isoformat(), raw, sha256(raw).hexdigest())).lastrowid
    con.commit()  # Archive first, parse only in comparison.
    return observed


def _ticks(con, observed, *, now):
    from .book_stream import KalshiBookStream
    from .orderbooks import normalize_rest
    row = con.execute('SELECT raw_bytes,sha256 FROM paper_tick_inputs WHERE id=?', (observed,)).fetchone()
    if not row or sha256(row[0]).hexdigest() != row[1]:
        raise ValueError('paper tick hash mismatch or missing input')
    data = load_json(row[0])
    if field(data, 'hypothetical', bool) is not True or text_field(data, 'schema') != 'paper-ticks/m5-v1':
        raise ValueError('explicit hypothetical tick schema required')
    k, p = field(data, 'kalshi_metadata', dict), field(data, 'polymarket_us_metadata', dict)
    if not all(value.startswith('HYPOTHETICAL-') for value in (text_field(k, 'ticker'), text_field(p, 'slug'))):
        raise ValueError('hypothetical tick identities required')
    metadata_at = text_field(data, 'metadata_received_at')
    stream = KalshiBookStream(k['ticker'], k, metadata_received_at=metadata_at)
    books = [stream.apply(field(data, 'kalshi_ws_snapshot', dict), received_at=text_field(data, 'kalshi_received_at'), now=now, generation=stream.generation),
             normalize_rest('polymarket_us', p['slug'], field(data, 'polymarket_us_rest', dict), p,
                            received_at=text_field(data, 'us_received_at'), metadata_received_at=metadata_at, now=now)]
    outages = field(data, 'outages', list)
    return books, outages, row[1]


def compare(con, intent_id, *, now=None, tick_input_id=None):
    now = now or datetime.now(timezone.utc)
    row = con.execute('SELECT created_at,mode,policy_json,input_json,input_sha256 FROM paper_intents WHERE id=?', (intent_id,)).fetchone()
    if row is None:
        raise ValueError('paper intent not found')
    created, mode, config, encoded, expected = row
    if sha256(encoded.encode()).hexdigest() != expected:
        raise ValueError('paper intent hash mismatch')
    if (mode == 'HYPOTHETICAL_REPLAY') != (tick_input_id is not None):
        raise ValueError('live/hypothetical paper tick mode mismatch')
    snapshot = load_json(encoded)
    detail = snapshot['detail']
    inputs = {'tick_input_id': tick_input_id, 'intent_sha256': expected, 'evaluated_at': now.isoformat()}
    try:
        pair, sides, models = _context(con, detail, now=now)
        initial = _initial(con, detail, now=utc_time(created), check_current=False)
        if tick_input_id is not None:
            books, outages, input_sha = _ticks(con, tick_input_id, now=now)
            inputs['tick_sha256'] = input_sha
        else:
            ids = [_latest(con, venue, source, now) for venue, source in
                   zip(('kalshi', 'polymarket_us'), (pair['kalshi_id'], pair['polymarket_us_id']))]
            quality = inspect_pair(con, detail['pair_id'], *ids, now=now)
            inputs['comparison'] = quality
            if not quality['comparison_ready']:
                raise ValueError('LATER_BOOKS_UNUSABLE: ' + ';'.join(quality['rejections']))
            books = [load_book(con, observed, now=now)[0] for observed in ids]
            outages = [False, False]
        inputs['later_books'] = [book.as_dict(now=now) for book in books]
        result = simulate(initial, books, models, sides, detail['economics']['best']['contracts'], pair['review'],
                          load_json(config), created_at=created, now=now,
                          reserve_per_leg=snapshot['research_policy']['reserve_per_leg'], outages=outages)
        for leg, venue in zip(result['legs'], ('kalshi', 'polymarket_us')):
            capital = leg['quote_cost'] + leg['fee_bound_including_settlement']
            from .orderbooks import exact
            capital += leg['filled'] * exact(snapshot['research_policy']['reserve_per_leg'])
            if capital > exact(snapshot['research_policy'][venue + '_budget']):
                result['flags'].append('PAPER_VENUE_BUDGET_EXCEEDED')
                result['severity'] = 'HIGH'
    except (ValueError, KeyError) as exc:
        result = {'status': 'UNOBSERVABLE', 'reason': str(exc), 'severity': 'WARN',
                  'verification': 'UNVERIFIED', 'trading_authorized': False,
                  'fills_unknown': True, 'potential_unhedged_contracts': detail['economics']['best']['contracts'],
                  'planned_capital_at_creation': detail['economics']['best']['total_capital'],
                  'current_loss_bound_known': False, 'real_positions_created': False}
    # Identical samples at different evaluation clocks remain separate diagnostic comparisons.
    input_key = digest(inputs)
    previous = con.execute('SELECT id,result_json FROM paper_comparisons WHERE intent_id=? AND input_key=?', (intent_id, input_key)).fetchone()
    if previous:
        return {'comparison_id': previous[0], **load_json(previous[1])}
    full = {'inputs': inputs, 'result': result}
    comparison_id = con.execute('''INSERT INTO paper_comparisons(intent_id,evaluated_at,input_key,input_json,result_json,sha256)
        VALUES(?,?,?,?,?,?)''', (intent_id, now.isoformat(), input_key, dumps(inputs), dumps(result), digest(full))).lastrowid
    if result['severity'] == 'HIGH':
        con.execute('INSERT INTO ops_events(ts_utc,severity,action,detail_json) VALUES(?,?,?,?)',
                    (now.isoformat(), 'HIGH', 'PAPER_DOWNSIDE_SCENARIO', dumps({'intent_id': intent_id, 'comparison_id': comparison_id})))
    con.commit()
    return {'comparison_id': comparison_id, **result}


def report(con, *, limit=100):
    if type(limit) is not int or not 1 <= limit <= 500: raise ValueError('paper report limit must be 1..500')
    results = []
    for intent_id, mode, created in con.execute('SELECT id,mode,created_at FROM paper_intents ORDER BY id DESC LIMIT ?', (limit,)):
        row = con.execute('SELECT id,evaluated_at,result_json FROM paper_comparisons WHERE intent_id=? ORDER BY id DESC LIMIT 1', (intent_id,)).fetchone()
        results.append({'intent_id': intent_id, 'mode': mode, 'created_at': created,
                        'latest': None if row is None else {'id': row[0], 'at': row[1], 'result': load_json(row[2])}})
    total = con.execute('SELECT COUNT(*) FROM paper_intents').fetchone()[0]
    return {'paper_intents': results, 'total_intents': total, 'truncated': total > len(results),
            'multiweek_acceptance': False, 'continuous_run_verified': False,
            'independent_scenarios_not_realized_pnl': True, 'trading_authorized': False}
