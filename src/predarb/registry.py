"""Audited, human-reviewed contract pairs. Registry approval never authorizes trading."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit

from . import mechanics
from .validation import dumps, field, identifier, text_field, utc_time, decimal_value

VENUES = ('kalshi', 'polymarket_us')
MAX_AGE = timedelta(hours=24)
CHECKS = ('proposition', 'event_definition', 'timezone_cutoffs', 'resolution_sources',
          'thresholds_revisions', 'suspension_void_cancellation', 'payout_semantics', 'settlement_timing')
SCENARIOS = ('YES', 'NO', 'VOID', 'CANCELLED', 'SUSPENDED', 'SOURCE_REVISION')
K_FIELDS = ('ticker', 'event_ticker', 'market_type', 'title', 'subtitle', 'yes_sub_title', 'no_sub_title',
            'open_time', 'close_time', 'latest_expiration_time', 'expected_expiration_time',
            'settlement_timer_seconds', 'rules_primary', 'rules_secondary', 'can_close_early',
            'early_close_condition', 'strike_type', 'floor_strike', 'cap_strike', 'functional_strike',
            'custom_strike', 'notional_value_dollars', 'settlement_bounds_type', 'settlement_floor_dollars')
P_FIELDS = ('id', 'slug', 'question', 'title', 'subtitle', 'description', 'startDate', 'endDate',
            'assetPriceTerms', 'rulesDisclaimer')

# Only documented observation/quote/display fields are excluded from contract hashing.
# Any new, uninterpreted metadata is retained in the fingerprint and requires re-review.
K_VOLATILE = {'created_time', 'updated_time', 'status', 'exchange_index', 'result', 'expiration_value',
              'settlement_value_dollars', 'settlement_ts', 'yes_bid_dollars', 'yes_ask_dollars',
              'no_bid_dollars', 'no_ask_dollars', 'yes_bid_size_fp', 'yes_ask_size_fp',
              'last_price_dollars', 'previous_price_dollars', 'previous_yes_bid_dollars',
              'previous_yes_ask_dollars', 'volume_fp', 'volume_24h_fp', 'open_interest_fp'}
P_VOLATILE = {'createdAt', 'updatedAt', 'active', 'closed', 'ep3Status', 'status', 'ep3SyncedAt',
              'bestBidQuote', 'bestAskQuote', 'outcomePrices', 'feeCoefficient', 'orderPriceMinTickSize',
              'minimumTradeQty', 'volume', 'volume24hr', 'volume1wk', 'volume1mo', 'volume1yr',
              'image', 'color', 'darkColor', 'titleShort'}


def now_utc():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def _rows(con, sql, args=()):
    cursor = con.execute(sql, args)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _one(con, sql, args=()):
    rows = _rows(con, sql, args)
    if not rows:
        raise ValueError('registry record not found')
    return rows[0]


def _actor(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('explicit operator/reviewer identity required')
    return value.strip()


def _audit(con, pair_id, actor, action, detail, now):
    con.execute('INSERT INTO pair_audit(pair_id,ts_utc,actor,action,detail_json) VALUES(?,?,?,?,?)',
                (pair_id, now.isoformat(), _actor(actor), action, dumps(detail)))


def _invalidate(con, venue, source_id, reason, now):
    key = 'kalshi_id' if venue == 'kalshi' else 'polymarket_us_id'
    for row in _rows(con, f"SELECT id FROM pairs WHERE {key}=? AND status='APPROVED'", (source_id,)):
        con.execute("UPDATE pairs SET status='INVALIDATED',reason=? WHERE id=?", (reason, row['id']))
        _audit(con, row['id'], 'SYSTEM', 'INVALIDATED', {'reason': reason, 'venue': venue, 'source_id': source_id}, now)


def _record_instrument(con, venue, source_id, contract, *, observed_at, available,
                       hypothetical=False, observation_id=None, run_id=None, now=None):
    now = now or now_utc()
    if venue not in VENUES:
        raise ValueError('unsupported US venue')
    identifier(source_id)
    utc_time(observed_at)
    if hypothetical and not source_id.startswith('HYPOTHETICAL-'):
        raise ValueError('hypothetical IDs must start HYPOTHETICAL-')
    if not hypothetical and source_id.startswith('HYPOTHETICAL-'):
        raise ValueError('hypothetical ID cannot enter the live registry')
    evidence = {'contract_schema': 'm2-contract-v1', 'venue': venue, 'source_id': source_id,
                'hypothetical': hypothetical, 'contract': contract}
    sha = digest(evidence)
    con.execute('''INSERT OR IGNORE INTO rule_versions
        (venue,source_id,contract_sha256,evidence_json,hypothetical,created_at) VALUES(?,?,?,?,?,?)''',
                (venue, source_id, sha, dumps(evidence), int(hypothetical), now.isoformat()))
    version = _one(con, 'SELECT id FROM rule_versions WHERE venue=? AND source_id=? AND contract_sha256=?',
                   (venue, source_id, sha))['id']
    old = _rows(con, 'SELECT version_id FROM registry_instruments WHERE venue=? AND source_id=?', (venue, source_id))
    con.execute('''INSERT INTO registry_instruments VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(venue,source_id) DO UPDATE SET version_id=excluded.version_id,
        observed_at=excluded.observed_at,observation_id=excluded.observation_id,
        run_id=excluded.run_id,available=excluded.available''',
                (venue, source_id, version, observed_at, observation_id, run_id, int(available)))
    if (old and old[0]['version_id'] != version) or not available:
        _invalidate(con, venue, source_id, 'contract evidence changed or instrument unavailable', now)
    con.commit()
    return sha


def observe_catalogue(con, run_id, observation_id, source_id, metadata, rules):
    from . import kalshi, polymarket_us
    raw = _one(con, 'SELECT * FROM raw_observations WHERE id=?', (observation_id,))
    adapter = kalshi if raw['venue'] == 'kalshi' else polymarket_us
    if raw['venue'] not in VENUES or raw['schema_version'] != adapter.SCHEMA_VERSION or raw['validation_status'] != 'VALID':
        raise ValueError('registry requires a validated, versioned US provider observation')
    adapter.validate_market(metadata)
    if metadata[adapter.ID_FIELD] != source_id:
        raise ValueError('registry source identity mismatch')
    keys = K_FIELDS if raw['venue'] == 'kalshi' else P_FIELDS
    contract = {key: metadata[key] for key in keys if key in metadata}
    excluded = K_VOLATILE if raw['venue'] == 'kalshi' else P_VOLATILE | {'marketSides'}
    contract['uninterpreted_metadata'] = {key: value for key, value in metadata.items()
                                           if key not in keys and key not in excluded}
    if raw['venue'] == 'polymarket_us':
        contract['marketSides'] = [{key: value for key, value in side.items()
                                    if key not in {'price', 'quote', 'createdAt', 'updatedAt'}}
                                   for side in metadata['marketSides']]
        available = metadata['active'] and not metadata['closed'] and metadata['status'] == 'MARKET_STATUS_OPEN'
    else:
        available = metadata['status'] == 'active' and metadata['market_type'] == 'binary'
    sha = _record_instrument(con, raw['venue'], source_id, contract, observed_at=raw['ts_utc'],
                             available=available, observation_id=observation_id, run_id=run_id)
    if raw['venue'] == 'kalshi':
        for kind in ('event', 'series'):
            if kind + '_evidence' in rules:
                if kind + '_endpoint' not in rules:
                    raise ValueError('supplemental rule evidence lacks source endpoint; recapture details')
                _observe_supplement(con, source_id, kind, rules[kind + '_evidence'], rules[kind + '_endpoint'])
    return sha


def _observe_supplement(con, source_id, kind, evidence, endpoint):
    from . import kalshi
    raw = _one(con, """SELECT id,ts_utc FROM raw_observations WHERE venue='kalshi'
        AND endpoint=? AND validation_status='VALID' ORDER BY id DESC LIMIT 1""", (endpoint,))
    (kalshi.validate_event if kind == 'event' else kalshi.validate_series)({kind: evidence})
    content = {key: value for key, value in evidence.items() if key not in {'last_updated_ts', 'volume_fp'}}
    sha = digest({'content': content, 'source_url': endpoint})
    con.execute("""INSERT OR IGNORE INTO supplement_versions
        (venue,source_id,kind,content_sha256,evidence_json,source_url) VALUES('kalshi',?,?,?,?,?)""",
                (source_id, kind, sha, dumps(content), endpoint))
    version_id = _one(con, """SELECT id FROM supplement_versions
        WHERE venue='kalshi' AND source_id=? AND kind=? AND content_sha256=?""", (source_id, kind, sha))['id']
    previous = _rows(con, "SELECT version_id FROM registry_supplements WHERE venue='kalshi' AND source_id=? AND kind=?", (source_id, kind))
    con.execute("""INSERT INTO registry_supplements VALUES('kalshi',?,?,?,?,?)
        ON CONFLICT(venue,source_id,kind) DO UPDATE SET version_id=excluded.version_id,
        observation_id=excluded.observation_id,observed_at=excluded.observed_at""",
                (source_id, kind, version_id, raw['id'], raw['ts_utc']))
    if not previous or previous[0]['version_id'] != version_id:
        _invalidate(con, 'kalshi', source_id, f'{kind} rule evidence changed', now_utc())
    con.commit()


def sync_catalogue(con):
    """Backfill existing M1 archives; never convert legacy/unvalidated rows into approvals."""
    for row in _rows(con, 'SELECT * FROM catalogue_entries ORDER BY observation_id,run_id'):
        try:
            observe_catalogue(con, row['run_id'], row['observation_id'], row['source_id'],
                              json.loads(row['metadata_json']), json.loads(row['rules_json']))
        except ValueError as exc:
            _audit(con, None, 'SYSTEM', 'BACKFILL_REJECTED',
                   {'observation_id': row['observation_id'], 'reason': str(exc)}, now_utc())
            con.commit()


def import_document(con, venue, source_id, source_url, raw_bytes, text_bytes, retrieved_at,
                    operator, *, now=None):
    now = now or now_utc()
    operator = _actor(operator)
    head = _instrument(con, venue, source_id)
    url = urlsplit(source_url)
    host = url.hostname or ''
    if url.scheme != 'https' or url.username or url.password or url.fragment or url.port not in (None, 443):
        raise ValueError('source URL must be an official HTTPS URL without credentials/fragment')
    if head['hypothetical']:
        allowed = host == 'example.invalid'
    else:
        roots = ('kalshi.com',) if venue == 'kalshi' else ('polymarket.us', 'polymarketexchange.com')
        allowed = any(host == root or host.endswith('.' + root) for root in roots)
        allowed = allowed or (venue == 'kalshi' and host == 'kalshi-public-docs.s3.amazonaws.com')
    if not allowed:
        raise ValueError('document URL must belong to the corresponding US venue')
    for body in (raw_bytes, text_bytes):
        if not isinstance(body, bytes) or not 0 < len(body) <= 2_000_000:
            raise ValueError('source and extracted text must each contain 1..2000000 bytes')
    if not text_bytes.decode('utf-8').strip():
        raise ValueError('empty resolution text')
    retrieved = utc_time(retrieved_at)
    if retrieved > now + timedelta(seconds=5):
        raise ValueError('document retrieval time is in the future')
    raw_sha, text_sha = (hashlib.sha256(body).hexdigest() for body in (raw_bytes, text_bytes))
    previous = _rows(con, '''SELECT d.raw_sha256,d.text_sha256 FROM document_heads h JOIN rule_documents d
        ON d.id=h.document_id WHERE h.venue=? AND h.source_id=? AND h.source_url=?''', (venue, source_id, source_url))
    cursor = con.execute('''INSERT INTO rule_documents(venue,source_id,source_url,retrieved_at,imported_at,
        operator,raw_bytes,raw_sha256,text_bytes,text_sha256,hypothetical) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (venue, source_id, source_url, retrieved_at, now.isoformat(), operator, raw_bytes, raw_sha,
         text_bytes, text_sha, head['hypothetical']))
    con.execute('''INSERT INTO document_heads VALUES(?,?,?,?) ON CONFLICT(venue,source_id,source_url)
                   DO UPDATE SET document_id=excluded.document_id''', (venue, source_id, source_url, cursor.lastrowid))
    # Adding a source also changes the review bundle; old approvals never cover unreviewed evidence.
    if not previous or (previous[0]['raw_sha256'], previous[0]['text_sha256']) != (raw_sha, text_sha):
        _invalidate(con, venue, source_id, 'official document evidence changed', now)
    _audit(con, None, operator, 'DOCUMENT_IMPORTED', {'document_id': cursor.lastrowid, 'venue': venue,
                                                  'source_id': source_id, 'source_url': source_url,
                                                  'raw_sha256': raw_sha, 'text_sha256': text_sha}, now)
    con.commit()
    return cursor.lastrowid


def _instrument(con, venue, source_id):
    if venue not in VENUES:
        raise ValueError('unsupported US venue')
    return _one(con, '''SELECT h.*,v.contract_sha256,v.evidence_json,v.hypothetical
        FROM registry_instruments h JOIN rule_versions v ON v.id=h.version_id
        WHERE h.venue=? AND h.source_id=?''', (venue, identifier(source_id)))


def _bundle(con, kalshi_id, polymarket_us_id):
    instruments = []
    fingerprint = []
    for venue, source_id in zip(VENUES, (kalshi_id, polymarket_us_id)):
        head = _instrument(con, venue, source_id)
        docs = _rows(con, '''SELECT d.* FROM document_heads h JOIN rule_documents d ON d.id=h.document_id
            WHERE h.venue=? AND h.source_id=? ORDER BY h.source_url''', (venue, source_id))
        if any(hashlib.sha256(doc['raw_bytes']).hexdigest() != doc['raw_sha256'] or
               hashlib.sha256(doc['text_bytes']).hexdigest() != doc['text_sha256'] for doc in docs):
            raise ValueError('registry document provenance mismatch')
        head['supplements'] = _rows(con, '''SELECT s.*,v.content_sha256,v.evidence_json,v.source_url
            FROM registry_supplements s JOIN supplement_versions v ON v.id=s.version_id
            WHERE s.venue=? AND s.source_id=? ORDER BY s.kind''', (venue, source_id))
        for supplement in head['supplements']:
            supplement['evidence'] = json.loads(supplement.pop('evidence_json'))
        head['evidence'] = json.loads(head.pop('evidence_json'))
        head['source_provenance'] = (_one(con, '''SELECT endpoint,ts_utc,body_sha256,schema_version,validation_status
            FROM raw_observations WHERE id=?''', (head['observation_id'],)) if head['observation_id'] is not None
            else {'kind': 'HYPOTHETICAL_LOCAL_FIXTURE'})
        head['documents'] = [{key: value for key, value in doc.items() if key not in {'raw_bytes', 'text_bytes'}}
                             | {'resolution_text': doc['text_bytes'].decode('utf-8'),
                                'provenance': 'OPERATOR_IMPORTED_NOT_INDEPENDENTLY_FETCHED'} for doc in docs]
        fingerprint.append({'venue': venue, 'source_id': source_id, 'contract_sha256': head['contract_sha256'],
                            'supplements': [(item['kind'], item['content_sha256']) for item in head['supplements']],
                            'documents': [(doc['source_url'], doc['raw_sha256'], doc['text_sha256']) for doc in docs]})
        instruments.append(head)
    if instruments[0]['hypothetical'] != instruments[1]['hypothetical']:
        raise ValueError('cannot mix hypothetical and live instruments')
    return {'evidence_sha256': digest(fingerprint), 'instruments': instruments,
            'hypothetical': bool(instruments[0]['hypothetical'])}


def _live_reason(con, bundle, now):
    for head in bundle['instruments']:
        if not head['available']:
            return 'instrument is not available for review'
        if not head['hypothetical']:
            contract = head['evidence']['contract']
            if head['venue'] == 'kalshi':
                if {item['kind'] for item in head['supplements']} != {'event', 'series'}:
                    return 'Kalshi event and series rule evidence required; collect selected market details'
                if any(now - utc_time(item['observed_at']) > MAX_AGE for item in head['supplements']):
                    return 'Kalshi event/series rule evidence is stale'
            rule_key = 'rules_primary' if head['venue'] == 'kalshi' else 'description'
            if not isinstance(contract.get(rule_key), str) or not contract[rule_key].strip():
                return 'market resolution text is missing'
            cutoff_key = 'close_time' if head['venue'] == 'kalshi' else 'endDate'
            if cutoff_key not in contract or utc_time(contract[cutoff_key]) <= now:
                return 'market cutoff is missing or has passed'
        observed = utc_time(head['observed_at'])
        if observed > now + timedelta(seconds=5) or now - observed > MAX_AGE:
            return 'catalogue evidence is stale or future-dated'
        if head['run_id'] is not None:
            run = _one(con, 'SELECT status FROM collection_runs WHERE id=?', (head['run_id'],))
            if run['status'] not in {'COMPLETE', 'PARTIAL'}:
                return 'latest source collection is failed, interrupted or incomplete'
        if not head['documents']:
            return 'official resolution text documents required for both venues'
        for doc in head['documents']:
            if now - utc_time(doc['retrieved_at']) > MAX_AGE:
                return 'official resolution document is stale'
    return None


def propose(con, kalshi_id, polymarket_us_id, operator, *, now=None):
    now = now or now_utc()
    bundle = _bundle(con, kalshi_id, polymarket_us_id)
    operator = _actor(operator)
    cursor = con.execute('''INSERT INTO pairs(kalshi_id,polymarket_us_id,hypothetical,created_at,status,
        evidence_sha256,reason) VALUES(?,?,?,?,'UNVERIFIED',?,'human review required')''',
        (kalshi_id, polymarket_us_id, int(bundle['hypothetical']), now.isoformat(), bundle['evidence_sha256']))
    _audit(con, cursor.lastrowid, operator, 'PROPOSED', bundle, now)
    con.commit()
    return cursor.lastrowid


def review(con, pair_id, *, now=None):
    now = now or now_utc()
    pair = _one(con, 'SELECT * FROM pairs WHERE id=?', (pair_id,))
    bundle = _bundle(con, pair['kalshi_id'], pair['polymarket_us_id'])
    decision = json.loads(pair['review_json']) if pair['review_json'] else None
    assessment = mechanics.assess(decision, bundle, now=now)
    if pair['status'] == 'APPROVED':
        reason = ('review evidence changed' if pair['evidence_sha256'] != bundle['evidence_sha256']
                  else _live_reason(con, bundle, now))
        if not reason and (not bundle['hypothetical'] or 'mechanics' in (decision or {})):
            if assessment['status'] != 'REVIEWED_RESEARCH_ONLY':
                reason = 'mechanics review invalid: ' + ';'.join(assessment['reasons'])
        if utc_time(pair['expires_at']) <= now:
            status, reason = 'EXPIRED', 'human approval expired'
        else:
            status = 'INVALIDATED'
        if reason:
            con.execute('UPDATE pairs SET status=?,reason=? WHERE id=?', (status, reason, pair_id))
            _audit(con, pair_id, 'SYSTEM', status, {'reason': reason}, now)
            con.commit()
            pair['status'], pair['reason'] = status, reason
    pair['decision_evidence_sha256'] = pair['evidence_sha256']
    pair['review'] = json.loads(pair.pop('review_json')) if pair['review_json'] else None
    pair.pop('review_json', None)
    return pair | bundle | {'approval_blocker': _live_reason(con, bundle, now),
                            'mechanics_assessment': assessment, 'trading_authorized': False}


def review_template(con, pair_id, *, now=None):
    data = review(con, pair_id, now=now)
    return {'pair_id': pair_id, 'evidence_sha256': data['evidence_sha256'],
            'hypothetical': data['hypothetical'], 'reviewer': '', 'human_reviewed': False,
            'expires_at': '', 'reason': '',
            'comparisons': {key: {'equivalent': False, 'rationale': ''} for key in CHECKS},
            'outcome_mapping': {'YES': '', 'NO': ''}, 'legs': {'kalshi': '', 'polymarket_us': ''},
            'settlement_scenarios': [], **({'mechanics': mechanics.template()} if not data['hypothetical'] else {})}


def _validate_review(data, pair_id, bundle, now):
    if field(data, 'pair_id', int) != pair_id or text_field(data, 'evidence_sha256') != bundle['evidence_sha256']:
        raise ValueError('review does not cover the current pair evidence hash')
    if field(data, 'hypothetical', bool) != bundle['hypothetical']:
        raise ValueError('review hypothetical flag mismatch')
    if field(data, 'human_reviewed', bool) is not True:
        raise ValueError('explicit human review attestation required')
    reviewer = _actor(text_field(data, 'reviewer'))
    text_field(data, 'reason')
    expires = utc_time(text_field(data, 'expires_at'))
    oldest = min(utc_time(head['observed_at']) for head in bundle['instruments'])
    oldest = min([oldest] + [utc_time(doc['retrieved_at']) for head in bundle['instruments'] for doc in head['documents']]
                 + [utc_time(item['observed_at']) for head in bundle['instruments'] for item in head['supplements']])
    if not now < expires <= min(now + MAX_AGE, oldest + MAX_AGE):
        raise ValueError('expiry must be future and within the 24-hour evidence freshness window')
    comparisons = field(data, 'comparisons', dict)
    for key in CHECKS:
        check = field(comparisons, key, dict)
        if field(check, 'equivalent', bool) is not True:
            raise ValueError(f'human comparison unresolved or different: {key}')
        text_field(check, 'rationale')
    mapping = field(data, 'outcome_mapping', dict)
    if set(mapping) != {'YES', 'NO'} or any(type(v) is not str for v in mapping.values()) or set(mapping.values()) != {'YES', 'NO'}:
        raise ValueError('explicit bijective YES/NO outcome mapping required')
    legs = field(data, 'legs', dict)
    if set(legs) != set(VENUES) or any(type(leg) is not str or leg not in {'YES', 'NO'} for leg in legs.values()):
        raise ValueError('explicit YES/NO leg selection required')
    if mapping[legs['kalshi']] == legs['polymarket_us']:
        raise ValueError('selected legs are not complementary under the reviewed mapping')
    scenarios = field(data, 'settlement_scenarios', list)
    if len(scenarios) < len(SCENARIOS) or len(scenarios) > 30:
        raise ValueError('explicit binary and exceptional settlement scenarios required')
    covered = set()
    for scenario in scenarios:
        code = text_field(scenario, 'case')
        if code not in SCENARIOS:
            raise ValueError('unknown settlement scenario case')
        covered.add(code)
        text_field(scenario, 'condition')
        payouts = []
        for venue in VENUES:
            payout = text_field(scenario, venue + '_payout')
            if not re.fullmatch(r'(?:0(?:\.[0-9]{1,8})?|1(?:\.0{1,8})?)', payout):
                raise ValueError('payout must be an exact USD decimal in [0,1] with at most 8 decimal places')
            payouts.append(decimal_value(payout, price=True))
            when = utc_time(text_field(scenario, venue + '_settlement_at'))
            if when <= now:
                raise ValueError('settlement times must be future UTC-aware timestamps')
        if sum(payouts) != 1:
            raise ValueError('scenario does not establish a fixed $1 combined payout; leave UNVERIFIED or reject')
        if code in {'YES', 'NO'}:
            expected = [int(legs['kalshi'] == code), int(legs['polymarket_us'] == mapping[code])]
            if payouts != expected:
                raise ValueError('scenario payouts contradict outcome mapping and selected legs')
    if covered != set(SCENARIOS):
        raise ValueError('YES/NO, void, cancellation, suspension and source revision scenarios all required')
    if not bundle['hypothetical'] or 'mechanics' in data:
        mechanics.validate_review(data, bundle, now=now)
    return reviewer, expires


def approve(con, pair_id, data, *, human_attested=False, now=None):
    now = now or now_utc()
    # Serialize the final evidence check and decision with collector writes.
    con.execute('BEGIN IMMEDIATE')
    try:
        pair = review(con, pair_id, now=now)
        if pair['status'] != 'UNVERIFIED':
            raise ValueError('only an UNVERIFIED proposal can be approved; terminal decisions require a new proposal')
        if not human_attested:
            raise ValueError('operator must explicitly attest human review')
        if pair['approval_blocker']:
            raise ValueError(pair['approval_blocker'])
        reviewer, expires = _validate_review(data, pair_id, pair, now)
        con.execute('''UPDATE pairs SET status='APPROVED',evidence_sha256=?,review_json=?,reviewer=?,
            approved_at=?,expires_at=?,reason=? WHERE id=?''',
            (pair['evidence_sha256'], dumps(data), reviewer, now.isoformat(), expires.isoformat(), data['reason'], pair_id))
        _audit(con, pair_id, reviewer, 'APPROVED', {'review': data, 'evidence': pair['instruments'],
                                                'trading_authorized': False}, now)
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return review(con, pair_id, now=now)


def decide(con, pair_id, decision, operator, reason, *, now=None):
    now = now or now_utc()
    operator = _actor(operator)
    if decision not in {'REJECTED', 'REVOKED'} or not isinstance(reason, str) or not reason.strip():
        raise ValueError('explicit reject/revoke decision and nonempty reason required')
    pair = review(con, pair_id, now=now)
    if decision == 'REJECTED' and pair['status'] != 'UNVERIFIED':
        raise ValueError('only an UNVERIFIED proposal can be rejected')
    if decision == 'REVOKED' and pair['status'] not in {'UNVERIFIED', 'APPROVED'}:
        raise ValueError('only a current proposal/approval can be revoked')
    con.execute('UPDATE pairs SET status=?,reason=? WHERE id=?', (decision, reason, pair_id))
    _audit(con, pair_id, operator, decision, {'reason': reason}, now)
    con.commit()
    return review(con, pair_id, now=now)


def list_pairs(con, *, now=None):
    return [review(con, row['id'], now=now) for row in _rows(con, 'SELECT id FROM pairs ORDER BY id')]


def audit(con, pair_id=None):
    rows = _rows(con, 'SELECT * FROM pair_audit' + (' WHERE pair_id=?' if pair_id is not None else '') + ' ORDER BY id',
                 (pair_id,) if pair_id is not None else ())
    for row in rows:
        row['detail'] = json.loads(row.pop('detail_json'))
    return rows


def candidates(con, *, limit=20, max_instruments=None):
    from .discovery import discover
    return discover(con, limit=limit, max_instruments=max_instruments)['candidates']


def load_hypothetical(con, data, *, now=None):
    """Seed an isolated empty demo database; no production IDs or approval bypass."""
    now = now or now_utc()
    if field(data, 'hypothetical', bool) is not True:
        raise ValueError('example must be explicitly hypothetical')
    for table in ('registry_instruments', 'pairs', 'raw_observations'):
        if con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:
            raise ValueError('hypothetical examples require an empty isolated database')
    items = field(data, 'instruments', list)
    # Validate the whole fixture before writing any example evidence.
    if not items:
        raise ValueError('example instruments required')
    seen = set()
    for item in items:
        venue = text_field(item, 'venue')
        source_id = identifier(text_field(item, 'source_id'))
        if venue not in VENUES or not source_id.startswith('HYPOTHETICAL-') or (venue, source_id) in seen:
            raise ValueError('invalid/duplicate hypothetical instrument')
        seen.add((venue, source_id))
        contract = field(item, 'contract', dict)
        text_field(contract, 'title')
        text_field(item, 'resolution_text')
    for item in items:
        _record_instrument(con, item['venue'], item['source_id'], item['contract'], observed_at=now.isoformat(),
                           available=True, hypothetical=True, now=now)
        text = item['resolution_text'].encode()
        import_document(con, item['venue'], item['source_id'],
                        'https://example.invalid/' + item['source_id'], text, text,
                        now.isoformat(), 'HYPOTHETICAL fixture importer', now=now)
    return {'hypothetical': True, 'instruments': len(items), 'trading_authorized': False}


def invalidate_failed_collection(con, run_id, status):
    """A failed venue refresh creates uncertainty even if no new valid row was saved."""
    run = _one(con, 'SELECT venue FROM collection_runs WHERE id=?', (run_id,))
    now = now_utc()
    for pair in _rows(con, "SELECT id FROM pairs WHERE status='APPROVED'"):
        reason = f"{run['venue']} collection {run_id} ended {status}; refresh and human re-review required"
        con.execute("UPDATE pairs SET status='INVALIDATED',reason=? WHERE id=?", (reason, pair['id']))
        _audit(con, pair['id'], 'SYSTEM', 'INVALIDATED', {'reason': reason, 'collection_run_id': run_id}, now)
    con.commit()
