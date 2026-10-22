"""Explainable retrieval heuristics and a derived queue; never settlement decisions."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import sys
import unicodedata

from . import kalshi, polymarket_us, registry
from .collector import book_freshness
from .validation import dumps, load_json, utc_time, text_field

SCHEMA = """
CREATE TABLE discovery_queue (
 kalshi_id TEXT NOT NULL, polymarket_us_id TEXT NOT NULL,
 ranked_at TEXT NOT NULL, candidate_json TEXT NOT NULL,
 PRIMARY KEY(kalshi_id,polymarket_us_id)
);
CREATE TABLE discovery_state (
 id INTEGER PRIMARY KEY CHECK(id=1), refreshed_at TEXT NOT NULL, report_json TEXT NOT NULL
);
CREATE INDEX discovery_books_source ON book_captures(source_id,observation_id DESC);
"""
VERSION = 'discovery-v1'
STOP = set('win winner wins beat beats price game match will would should could reaches reach a an the will be is are was were of on in at by to for and or with this that market contract resolves resolve yes no if as than hypothetical above below over under greater less least most more equal before after between'.split())
MONTHS = {name.lower(): i for i, name in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'], 1)}
ALIASES = {'btc': 'bitcoin', 'eth': 'ethereum', 'cpi': 'consumer price index', 'fed': 'federal reserve', 'relegated': 'relegation'}
THRESHOLD = re.compile(r'\b(at least|at most|greater than or equal to|less than or equal to|greater than|less than|above|below|over|under|exceed|exceeds)\s*(\$)?\s*(-?\d[\d,]*(?:\.\d+)?)\s*(%|percent|k\b|million\b|billion\b|basis points|bps\b|points\b|degrees celsius|degrees fahrenheit|celsius|fahrenheit|c\b|f\b|dollars\b|usd\b)?', re.I)
OPERATORS = {'at least': '>=', 'greater than or equal to': '>=', 'at most': '<=', 'less than or equal to': '<=', 'above': '>', 'over': '>', 'greater than': '>', 'exceed': '>', 'exceeds': '>', 'below': '<', 'under': '<', 'less than': '<'}


def normalize(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    for word, replacement in ALIASES.items():
        text = re.sub(r'\b' + word + r'\b', replacement, text)
    return text


def tokens(text):
    return {sys.intern(word) for word in re.findall(r'[a-z]+', normalize(text)) if word not in STOP}


def features(contract):
    for key in ('question', 'title', 'subtitle', 'yes_sub_title', 'description', 'rules_primary', 'rules_secondary'):
        if key in contract:
            text_field(contract, key, empty=True)
    title = contract.get('question') or contract.get('title') or contract.get('yes_sub_title') or ''
    description = ' '.join(contract.get(key, '') for key in ('description', 'rules_primary', 'rules_secondary'))
    text = normalize(title + ' ' + description)
    dates = set()
    for year, month, day in re.findall(r'\b(20\d{2})-(\d{2})-(\d{2})\b', text):
        try:
            dates.add(datetime(int(year), int(month), int(day)).date().isoformat())
        except ValueError:
            pass
    for month, day, year in re.findall(r'\b(' + '|'.join(MONTHS) + r')\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b', text):
        try:
            dates.add(datetime(int(year), MONTHS[month], int(day)).date().isoformat())
        except ValueError:
            pass
    thresholds = set()
    for operator, currency, value, suffix in THRESHOLD.findall(text):
        number = Decimal(value.replace(',', ''))
        number *= {'k': 1000, 'million': 1000000, 'billion': 1000000000}.get(suffix, 1)
        units = {'%': '%', 'percent': '%', 'dollars': 'USD', 'usd': 'USD',
                 'points': 'points', 'basis points': 'bps', 'bps': 'bps',
                 'degrees celsius': 'C', 'celsius': 'C', 'c': 'C',
                 'degrees fahrenheit': 'F', 'fahrenheit': 'F', 'f': 'F'}
        unit = 'USD' if currency else units.get(suffix, 'unspecified')
        thresholds.add((OPERATORS[operator], format(number.normalize(), 'f'), unit))
    subjects = [title, contract.get('subtitle', ''), contract.get('yes_sub_title', '')]
    for side in contract.get('marketSides', []):
        if side.get('long') is True:
            if side.get('description') is not None:
                subjects.append(text_field(side, 'description', empty=True))
            if side.get('team') is not None:
                subjects.append(text_field(side['team'], 'name'))
    subject_text = ' '.join(filter(None, subjects))
    subject = tokens(subject_text) - set(MONTHS)
    metadata = contract.get('uninterpreted_metadata', {})
    event_time = None
    for key in ('occurrence_datetime', 'gameStartTime'):
        value = contract.get(key, metadata.get(key))
        if value not in (None, ''):
            event_time = utc_time(value).isoformat()
            break
    text_dates = dates
    if event_time:
        dates = {utc_time(event_time).date().isoformat()}
    # Descriptive subject words support retrieval when provider titles differ.
    cutoff = contract.get('close_time') or contract.get('endDate')
    return {'title': title, 'subject_text': subject_text, 'subject': subject, 'description': tokens(description),
            'dates': dates, 'text_dates': text_dates, 'event_time': event_time, 'thresholds': thresholds,
            'policy': set(re.findall(r'\b(first|final|revised|preliminary|not|cancelled|void)\b', text)),
            'cutoff': utc_time(cutoff).isoformat() if cutoff else None}


def overlap(left, right):
    return 10000 * len(left & right) // len(left | right) if left | right else 0


def compare(left, right, *, min_score=0):
    subject = overlap(left['subject'], right['subject'])
    score = subject * 5 // 10
    signals = {'subject_bps': subject}
    warnings = []
    for key, weight in (('dates', 1500), ('thresholds', 1500)):
        a, b = left[key], right[key]
        signals[key] = 'MATCH' if a and a == b else 'CONFLICT' if a and b else 'UNKNOWN'
        if signals[key] == 'MATCH':
            if key == 'thresholds' and any(unit == 'unspecified' for _, _, unit in a):
                signals[key] = 'VALUE_MATCH_UNITS_UNKNOWN'
                warnings.append('THRESHOLD_UNITS_UNKNOWN')
                score += weight // 3
            else:
                score += weight
        elif signals[key] == 'CONFLICT':
            score -= 2500
            warnings.append(key.upper() + '_CONFLICT')
        else:
            warnings.append(key.upper() + '_UNKNOWN')
    if left['event_time'] and right['event_time'] and left['event_time'] != right['event_time']:
        warnings.append('EVENT_TIMES_DIFFER')
        score -= 1500
    if left['policy'] != right['policy']:
        score -= 1500
        warnings.append('RESOLUTION_LANGUAGE_DIFFERS')
    if left['cutoff'] and right['cutoff']:
        if left['cutoff'] != right['cutoff']:
            warnings.append('CUTOFFS_DIFFER')
            score -= 500
    else:
        warnings.append('CUTOFF_UNKNOWN')
    # Description contributes at most 2,000 points. Prune only when even a
    # perfect description cannot enter the bounded result set (ties still rank).
    if max(0, score + 2000) < min_score:
        return None
    description = overlap(left['description'], right['description'])
    if subject < 2000 and description < 3500:
        return None
    signals['description_bps'] = description
    score = max(0, score + description * 2 // 10)
    return (score, signals, warnings) if score >= min_score else None


def _eligible(con, row, now):
    if not row['available']:
        return False
    age = (now - utc_time(row['observed_at'])).total_seconds()
    if not -5 <= age <= 86400:
        return False
    contract = json.loads(row['evidence_json'])['contract']
    cutoff = contract.get('close_time') or contract.get('endDate')
    if cutoff and utc_time(cutoff) <= now:
        return False
    return True


def _pools(con, now, max_instruments):
    pools, coverage = [], {}
    for venue in registry.VENUES:
        rows = registry._rows(con, '''SELECT h.*,v.evidence_json,v.hypothetical,v.contract_sha256
            FROM registry_instruments h JOIN rule_versions v ON v.id=h.version_id
            WHERE h.venue=? ORDER BY h.source_id''', (venue,))
        runs = registry._rows(con, 'SELECT * FROM collection_runs WHERE venue=? ORDER BY id DESC', (venue,))
        latest = runs[0] if runs else None
        full = next((run for run in runs if json.loads(run['scope_json']).get('filter') is None), None)
        members = None
        if full and full['status'] == 'COMPLETE':
            members = {r[0] for r in con.execute('SELECT source_id FROM catalogue_entries WHERE run_id=?', (full['id'],))}
        eligible = []
        for row in rows:
            if not _eligible(con, row, now):
                continue
            if not row['hypothetical']:
                if any(run and run['status'] in {'FAILED', 'INTERRUPTED', 'RUNNING'} for run in (latest, full)):
                    continue
                if members is not None and row['source_id'] not in members:
                    continue
            eligible.append(row)
        coverage[venue] = {'stored': len(rows), 'eligible': len(eligible),
                           'latest_run_status': latest['status'] if latest else None,
                           'full_catalogue_status': full['status'] if full else None,
                           'full_catalogue_run_id': full['id'] if full else None,
                           'full_catalogue_received_at': full['finished_at'] if full else None,
                           'truncated': bool(max_instruments and len(eligible) > max_instruments)}
        if max_instruments:
            eligible = eligible[:max_instruments]
        for row in eligible:
            row['features'] = features(json.loads(row.pop('evidence_json'))['contract'])
        pools.append(eligible)
    return pools, coverage


def liquidity(con, venue, source_id, now):
    rows = registry._rows(con, '''SELECT b.*,r.ts_utc,r.raw_body,r.validation_status,r.body_sha256,r.schema_version,r.endpoint,r.truncated,r.http_status
        FROM book_captures b JOIN raw_observations r ON r.id=b.observation_id
        WHERE r.venue=? AND b.source_id=? ORDER BY b.observation_id DESC LIMIT 1''', (venue, source_id))
    if not rows:
        return {'quality': 'MISSING', 'depth_proxy': None}
    row = rows[0]
    quality = book_freshness(row['source_ts'], row['ts_utc'], now=now, max_age=60)
    result = {'quality': quality, 'depth_proxy': None, 'observation_id': row['observation_id'],
              'received_at': row['ts_utc'], 'source_ts': row['source_ts'], 'executable': False}
    adapter = kalshi if venue == 'kalshi' else polymarket_us
    if (row['validation_status'] != 'VALID' or row['schema_version'] != adapter.SCHEMA_VERSION
            or row['endpoint'] != adapter.book_url(source_id) or row['truncated'] or row['http_status'] != 200
            or not isinstance(row['raw_body'], bytes)
            or hashlib.sha256(row['raw_body']).hexdigest() != row['body_sha256']):
        result['quality'] = 'INVALID'
        return result
    if quality not in {'FRESH', 'UNKNOWN_SOURCE_TIME'}:
        return result
    try:
        data = load_json(row['raw_body'])
        adapter.validate_book(data)
        if venue == 'kalshi':
            book = data['orderbook_fp']
            sides = [[Decimal(level[1]) for level in book[key]] for key in ('yes_dollars', 'no_dollars')]
        else:
            book = data['marketData']
            if book['marketSlug'] != source_id:
                raise ValueError('book identity mismatch')
            sides = [[Decimal(level['qty']) for level in book[key]] for key in ('bids', 'offers')]
        result['depth_proxy'] = str(min(sum(side, Decimal(0)) for side in sides))
    except (ValueError, TypeError):
        result['quality'] = 'INVALID'
    return result


def _links(con, row):
    adapter = kalshi if row['venue'] == 'kalshi' else polymarket_us
    links = [adapter.detail_url(row['source_id'])]
    for source in registry._rows(con, '''SELECT v.evidence_json,v.source_url FROM registry_supplements h
            JOIN supplement_versions v ON v.id=h.version_id WHERE h.venue=? AND h.source_id=?''',
                                (row['venue'], row['source_id'])):
        links.append(source['source_url'])
        evidence = json.loads(source['evidence_json'])
        links.extend(evidence[key] for key in ('contract_url', 'contract_terms_url') if key in evidence)
    links.extend(r[0] for r in con.execute('SELECT source_url FROM document_heads WHERE venue=? AND source_id=?',
                                         (row['venue'], row['source_id'])))
    return list(dict.fromkeys(links))


def discover(con, *, limit=20, max_instruments=None, now=None, _pair_keys=None):
    if not 1 <= limit <= 1000 or (max_instruments is not None and not 1 <= max_instruments <= 1000000):
        raise ValueError('candidate limits: 1..1000 results; optional instrument cap 1..1000000')
    now = now or registry.now_utc()
    pools, coverage = _pools(con, now, max_instruments)
    index, descriptions = defaultdict(set), defaultdict(set)
    for i, row in enumerate(pools[1]):
        for token in row['features']['subject']:
            index[token].add(i)
        for token in row['features']['description']:
            descriptions[token].add(i)
    rare = {token: postings for token, postings in descriptions.items()
            if len(postings) <= max(10, min(100, len(pools[1]) // 100))}
    allowed = defaultdict(set)
    poly_indices = {row['source_id']: i for i, row in enumerate(pools[1])}
    if _pair_keys is not None:
        for kalshi_id, poly_id in _pair_keys:
            if poly_id in poly_indices:
                allowed[kalshi_id].add(poly_indices[poly_id])
    cache = {}
    def depth(row):
        key = (row['venue'], row['source_id'])
        if key not in cache:
            cache[key] = liquidity(con, *key, now)
        return cache[key]
    score_floor = 0
    def matches():
        for k in pools[0]:
            possible = set()
            if _pair_keys is not None:
                possible = allowed[k['source_id']]
            else:
                for token in k['features']['subject']:
                    possible.update(index.get(token, ()))
                terms = sorted((t for t in k['features']['description'] if t in rare),
                               key=lambda t: (len(rare[t]), t))[:3]
                hits = Counter(i for token in terms for i in rare[token])
                possible.update(i for i, count in hits.items() if count >= min(2, len(terms)))
            for i in sorted(possible):
                p = pools[1][i]
                if k['hypothetical'] != p['hypothetical']:
                    continue
                comparison = compare(k['features'], p['features'], min_score=score_floor)
                if comparison is None:
                    continue
                score, signals, warnings = comparison
                kd, pd = depth(k), depth(p)
                quantities = [d['depth_proxy'] for d in (kd, pd)]
                quantity = min(map(Decimal, quantities)) if all(q is not None for q in quantities) else None
                # Source-time-qualified depth wins ties; unknown is never invented as zero.
                quality = 2 if all(d['quality'] == 'FRESH' for d in (kd, pd)) else 1 if quantity is not None else 0
                row = {'kalshi_id': k['source_id'], 'polymarket_us_id': p['source_id'],
                       'kalshi_title': k['features']['title'], 'polymarket_us_title': p['features']['title'],
                       'metadata_overlap_bps': signals['subject_bps'], 'equivalence_score_bps': score,
                       'signals': signals, 'warnings': warnings, 'hypothetical': bool(k['hypothetical']),
                       'status': 'UNVERIFIED', 'trading_authorized': False,
                       'reason': 'HEURISTIC_ONLY_HUMAN_REVIEW_REQUIRED', 'algorithm': VERSION,
                       'liquidity': {'kalshi': kd, 'polymarket_us': pd, 'paired_depth_proxy': str(quantity) if quantity is not None else None},
                       'versions': [k['version_id'], p['version_id']]}
                yield (-score, -quality, -(quantity or Decimal(0)), k['source_id'], p['source_id']), row, k, p
    best = []
    for item in matches():
        if len(best) < limit or item[0] < best[-1][0]:
            best.append(item)
            best.sort(key=lambda entry: entry[0])
            del best[limit:]
            if len(best) == limit:
                score_floor = best[-1][1]['equivalence_score_bps']
    result = []
    for _, row, k, p in best:
        row['definition_links'] = {'kalshi': _links(con, k), 'polymarket_us': _links(con, p)}
        row['features'] = {venue: {key: sorted(value) if isinstance(value, set) else value
                                  for key, value in item['features'].items()}
                           for venue, item in (('kalshi', k), ('polymarket_us', p))}
        row['prior_reviews'] = registry._rows(con, '''SELECT id,status,reason FROM pairs
            WHERE kalshi_id=? AND polymarket_us_id=? ORDER BY id''', (k['source_id'], p['source_id']))
        result.append(row)
    return {'algorithm': VERSION, 'ranked_at': now.isoformat(), 'coverage': coverage, 'candidates': result}


def refresh_queue(con, **kwargs):
    report = discover(con, **kwargs)
    try:
        con.execute('BEGIN IMMEDIATE')
        con.execute('DELETE FROM discovery_queue')
        con.executemany('INSERT INTO discovery_queue VALUES(?,?,?,?)',
                        [(r['kalshi_id'], r['polymarket_us_id'], report['ranked_at'], dumps(r)) for r in report['candidates']])
        con.execute('INSERT OR REPLACE INTO discovery_state VALUES(1,?,?)', (report['ranked_at'], dumps(report)))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return report


def queue(con, *, limit=20, now=None):
    # Recompute validity/ranking at read time; stored snapshots are never authority.
    keys = con.execute('SELECT kalshi_id,polymarket_us_id FROM discovery_queue').fetchall()
    report = discover(con, limit=limit, now=now, _pair_keys=keys)
    stored = con.execute('SELECT refreshed_at FROM discovery_state WHERE id=1').fetchone()
    report['last_queue_refresh'] = stored[0] if stored else None
    return report
