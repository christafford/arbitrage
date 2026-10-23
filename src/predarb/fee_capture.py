"""M5A C: public fee evidence, deterministic review packets, no automatic approval."""
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from . import kalshi, polymarket_us
from .fees import VERSION
from .provider import FEE_DOCUMENT_URLS, HttpClient
from .validation import decimal_value, dumps, field, identifier, load_json, text_field, utc_time

SCHEMA = 'live-fee-evidence/m5a-c-v1'
KALSHI_SCHEDULE = 'https://kalshi.com/docs/kalshi-fee-schedule.pdf'
KINDS = {'quadratic', 'quadratic_with_maker_fees', 'quadratic_with_combo_maker_fees'}


def fee_parameters(value, *, override=False):
    suffix = '_override' if override else ''
    kind = text_field(value, 'fee_type' + suffix)
    # Official JSON number, not a string, boolean or float decoded by application code.
    multiplier = value.get('fee_multiplier' + suffix)
    if type(multiplier) not in (int, Decimal):
        raise ValueError('missing or invalid numeric fee_multiplier')
    multiplier = decimal_value(multiplier, string=False)
    if kind not in KINDS or multiplier > 100:
        raise ValueError('unsupported Kalshi fee parameters')
    return {'kind': kind, 'multiplier': str(multiplier)}


def analyze(venue, source_id, get, *, captured_at):
    """Same request/validation plan for live capture and archived offline review."""
    adapter = kalshi if venue == 'kalshi' else polymarket_us
    market = get(adapter.detail_url(source_id), adapter.validate_detail)['market']
    if market[adapter.ID_FIELD] != source_id:
        raise ValueError('fee market identity mismatch')
    future_changes = []
    if venue == 'kalshi':
        if market['market_type'] != 'binary':
            raise ValueError('unsupported scalar/combo market')
        # No waiver assumptions; a separately reviewed model would be needed.
        if market.get('fee_waiver_expiration_time') is not None:
            raise ValueError('market fee waiver requires separate review; unsupported')
        event = get(kalshi.event_url(market), kalshi.validate_event)['event']
        if event['event_ticker'] != market['event_ticker']:
            raise ValueError('fee event identity mismatch')
        series_id = identifier(event['series_ticker'])
        series = get(kalshi.series_url(series_id), kalshi.validate_series)['series']
        if series['ticker'] != series_id:
            raise ValueError('fee series identity mismatch')
        parameters = fee_parameters(series)
        # Official optional paired overrides: absent/null means series inheritance.
        overrides = (event.get('fee_type_override'), event.get('fee_multiplier_override'))
        if overrides != (None, None):
            parameters = fee_parameters(event, override=True)
        changes_url = kalshi.BASE + '/series/fee_changes?series_ticker=' + series_id + '&show_historical=false'
        changes = get(changes_url, lambda d: field(d, 'series_fee_change_arr', list))
        seen = set()
        for change in changes['series_fee_change_arr']:
            change_id = text_field(change, 'id')
            if change_id in seen or text_field(change, 'series_ticker') != series_id:
                raise ValueError('fee change identity mismatch or duplicate')
            seen.add(change_id)
            fee_parameters(change)
            scheduled = utc_time(text_field(change, 'scheduled_ts'))
            if scheduled <= captured_at:
                raise ValueError('past change returned by future-only series fee endpoint; recapture required')
            future_changes.append(scheduled)
        event_url = kalshi.BASE + '/events/fee_changes?event_ticker=' + identifier(event['event_ticker']) + '&limit=1000'
        changes = get(event_url, lambda d: field(d, 'event_fee_changes', list))
        if text_field(changes, 'cursor', empty=True):
            raise ValueError('partial event fee history; pagination exceeds bounded capture')
        seen = set()
        for change in changes['event_fee_changes']:
            change_id = text_field(change, 'id')
            if (change_id in seen or text_field(change, 'series_ticker') != series_id
                    or text_field(change, 'event_ticker') != event['event_ticker']):
                raise ValueError('event fee change identity mismatch or duplicate')
            seen.add(change_id)
            # Unlike optional event metadata, both keys are required in change rows.
            if 'fee_type_override' not in change or 'fee_multiplier_override' not in change:
                raise ValueError('missing event fee change override fields')
            if (change['fee_type_override'], change['fee_multiplier_override']) != (None, None):
                fee_parameters(change, override=True)
            scheduled = utc_time(text_field(change, 'scheduled_ts'))
            if scheduled > captured_at:
                future_changes.append(scheduled)
        scope = {'event_ticker': event['event_ticker'], 'series_ticker': series_id,
                 'event_override': overrides != (None, None)}
    else:
        coefficient = market.get('feeCoefficient')
        if type(coefficient) not in (int, Decimal):
            raise ValueError('missing or invalid numeric feeCoefficient')
        coefficient = decimal_value(coefficient, string=False)
        kinds = {Decimal('.0695'): 'standard', Decimal('.10'): 'table_tennis'}
        if coefficient not in kinds:
            raise ValueError('unsupported US fee coefficient; no zero/combo fallback')
        parameters = {'kind': kinds[coefficient]}
        scope = {'market_id': market['id'], 'fee_coefficient': str(coefficient),
                 'category_review_required': True, 'single_contract_only': True}
    for url in FEE_DOCUMENT_URLS[venue]:
        get(url, None)
    return {'parameters': parameters, 'scope': scope,
            'next_change': min(future_changes).isoformat() if future_changes else None}


def capture(con, venue, source_id, side, *, now, client=None):
    identifier(source_id)
    if venue not in FEE_DOCUMENT_URLS or side not in {'YES', 'NO'} or source_id.startswith('HYPOTHETICAL-'):
        raise ValueError('live fee capture requires a real US venue identity and YES/NO side')
    request = dumps({'schema': SCHEMA, 'venue': venue, 'source_id': source_id, 'side': side,
                     'captured_at': now.isoformat()}).encode()
    capture_id = con.execute('''INSERT INTO fee_imports(imported_at,raw_bytes,sha256,status,venue,source_id,side)
        VALUES(?,?,?,'CAPTURE_PENDING',?,?,?)''',
        (now.isoformat(), request, sha256(request).hexdigest(), venue, source_id, side)).lastrowid
    con.commit()  # Supersede earlier approvals BEFORE any network I/O, including failed refreshes.
    client = client or HttpClient(con, venue)

    def get(url, validator):
        observation = (client.get(url, SCHEMA, validator) if validator else client.get_fee_document(url, SCHEMA))
        body = con.execute('SELECT raw_body FROM raw_observations WHERE id=?', (observation.id,)).fetchone()[0]
        if not 0 < len(body) <= 2000000:
            raise ValueError('fee evidence must contain 1..2000000 bytes')
        con.execute('INSERT INTO fee_documents(import_id,source_url,retrieved_at,raw_bytes,sha256) VALUES(?,?,?,?,?)',
                    (capture_id, url, observation.received_at, body, sha256(body).hexdigest()))
        con.commit()
        return observation.data
    try:
        analyze(venue, source_id, get, captured_at=now)
        con.execute("UPDATE fee_imports SET status='CAPTURED' WHERE id=?", (capture_id,))
        con.commit()
        return capture_id
    except (ValueError, OSError, TypeError) as exc:
        con.execute("UPDATE fee_imports SET status='CAPTURE_FAILED',error=? WHERE id=?", (str(exc), capture_id))
        con.commit()
        raise


def review(con, capture_id, *, now):
    row = con.execute('SELECT raw_bytes,sha256,status,venue,source_id,side FROM fee_imports WHERE id=?', (capture_id,)).fetchone()
    if not row or row[2] != 'CAPTURED' or sha256(row[0]).hexdigest() != row[1]:
        raise ValueError('missing, incomplete or corrupt fee capture')
    request = load_json(row[0])
    if text_field(request, 'schema') != SCHEMA:
        raise ValueError('unsupported live fee capture schema')
    venue, source_id, side = (text_field(request, k) for k in ('venue', 'source_id', 'side'))
    if (venue, source_id, side) != row[3:] or venue not in FEE_DOCUMENT_URLS or side not in {'YES', 'NO'}:
        raise ValueError('fee capture identity mismatch')
    identifier(source_id)
    latest = con.execute("SELECT MAX(id) FROM fee_imports WHERE venue=? AND source_id=? AND side=? AND status LIKE 'CAPTURE%'",
                         (venue, source_id, side)).fetchone()[0]
    if latest != capture_id:
        raise ValueError('fee capture superseded; fresh review required')
    captured = utc_time(text_field(request, 'captured_at'))
    rows = con.execute('SELECT source_url,retrieved_at,raw_bytes,sha256 FROM fee_documents WHERE import_id=? ORDER BY id',
                       (capture_id,)).fetchall()
    if not rows or not captured <= now + timedelta(seconds=5):
        raise ValueError('missing sources or future capture')
    expiry = captured + timedelta(hours=24)
    sources = {}
    for url, retrieved, body, digest in rows:
        received = utc_time(retrieved)
        if (url in sources or not 0 < len(body) <= 2000000 or sha256(body).hexdigest() != digest
                or received < captured or received > now + timedelta(seconds=5)):
            raise ValueError('fee source provenance or receipt time mismatch')
        expiry = min(expiry, received + timedelta(hours=24))
        sources[url] = body
    consumed = set()

    def get(url, validator):
        if url not in sources:
            raise ValueError('missing required captured fee source: ' + url)
        consumed.add(url)
        if validator is None:
            sources[url].decode('utf-8')
            return sources[url]
        data = load_json(sources[url])
        validator(data)
        return data
    analysis = analyze(venue, source_id, get, captured_at=captured)
    if consumed != set(sources):
        raise ValueError('unexpected captured fee sources')
    if analysis['next_change']:
        expiry = min(expiry, utc_time(analysis['next_change']))
    if not now < expiry:
        raise ValueError('STALE_FEE_CAPTURE_OR_SCHEDULED_CHANGE: recapture and review required')
    manifest = [{'url': url, 'retrieved_at': retrieved, 'sha256': digest} for url, retrieved, _, digest in rows]
    digest = sha256(dumps({'request_sha256': row[1], 'sources': manifest}).encode()).hexdigest()
    draft = {'schema': VERSION, 'venue': venue, 'source_id': source_id, 'side': side,
             'version': '', 'capture_id': capture_id, 'capture_sha256': digest,
             'hypothetical': False, 'applicability_reviewed': False, 'operator': '',
             'effective_from': '', 'effective_until': expiry.isoformat(), 'expires_at': expiry.isoformat(),
             'settlement_fee_per_contract': '', 'instrument_scope': '', 'scheduled_changes_checked': '',
             'account_fee_extras_checked': '', 'schedule_reviewed': '', 'category_reviewed': '',
             'documents': [], **analysis['parameters']}
    if venue == 'kalshi':
        draft['balance_precision'] = ''
        draft['documents'] = [{'url': KALSHI_SCHEDULE, 'path': '', 'retrieved_at': ''}]
    return {'schema': SCHEMA, 'status': 'NEEDS_OPERATOR_REVIEW', 'capture_id': capture_id,
            'capture_sha256': digest, 'sources': manifest, 'analysis': analysis,
            'expires_no_later_than': expiry.isoformat(), 'draft': draft,
            'unresolved': ['schedule applicability/effective date and exceptions',
                           'exact category, single contract and instrument scope',
                           'account/FCM extras and balance precision', 'settlement fees'],
            'trading_authorized': False}


def validate_profile_capture(con, data, *, now):
    packet = review(con, field(data, 'capture_id', int), now=now)
    draft = packet['draft']
    for key in ('venue', 'source_id', 'side', 'capture_sha256', 'kind'):
        if text_field(data, key) != draft[key]:
            raise ValueError('fee capture/profile mismatch: ' + key)
    if data['venue'] == 'kalshi' and decimal_value(text_field(data, 'multiplier')) != decimal_value(draft['multiplier']):
        raise ValueError('fee capture/profile multiplier mismatch')
    if not (utc_time(text_field(data, 'effective_from')) <= now < utc_time(text_field(data, 'expires_at'))
            <= utc_time(text_field(data, 'effective_until')) <= utc_time(packet['expires_no_later_than'])):
        raise ValueError('fee profile validity must fit capture and scheduled-change window')
    for key in ('schedule_reviewed', 'category_reviewed'):
        text_field(data, key)
    return packet


def export_review(con, capture_id, directory, *, now):
    packet = review(con, capture_id, now=now)
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    rows = con.execute('SELECT raw_bytes FROM fee_documents WHERE import_id=? ORDER BY id', (capture_id,)).fetchall()
    for index, (source, row) in enumerate(zip(packet['sources'], rows)):
        name = f'source-{index + 1:02d}.txt'
        (root / name).write_bytes(row[0])
        source['local_path'] = name
    (root / 'review.json').write_text(dumps(packet) + '\n')
    (root / 'profile.json').write_text(dumps(packet['draft']) + '\n')
    return {'capture_id': capture_id, 'output': str(root), 'status': packet['status'],
            'expires_no_later_than': packet['expires_no_later_than'], 'trading_authorized': False}
