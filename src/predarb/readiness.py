"""Read-only M5A E readiness snapshot. No refresh, approvals, credentials or services."""
from datetime import timedelta, timezone
from decimal import Decimal
import sqlite3

from . import mechanics, registry
from .book_store import inspect_book, load_book
from .book_stream import SEQUENCE_PROTOCOL_END
from .economics import policy
from .fee_store import current_profile
from .operations import health
from .orderbooks import walk_depth
from .research import clock, session
from .validation import utc_time
from .ws_store import PROTOCOL_SCHEMAS

VERSION = 'research-readiness/m5a-e-v1'
MAX_PAIRS = 50  # Same whole-registry bound as scan_once, including terminal rows.


def check(code, passed, detail, action='', *, expires_at=None):
    return {'code': code, 'status': 'PASS' if passed else 'BLOCKED',
            'detail': detail, 'next_action': '' if passed else action, 'expires_at': expires_at}


def _pair(con, row, now, horizon):
    pair_id, k_source, p_source, stored, hypothetical = row
    result = {'pair_id': pair_id, 'kalshi_id': k_source, 'polymarket_us_id': p_source,
              'stored_status': stored, 'hypothetical': bool(hypothetical), 'checks': [],
              'books': [], 'fees': [], 'ready_now': False, 'horizon_supported': False}
    checks = result['checks']
    if hypothetical:
        checks.append(check('REAL_PAIR', False, 'Hypothetical registry evidence cannot establish live readiness.',
                            'Collect real instruments and complete human pair, fee and mechanics reviews.'))
        return result
    checks.append(check('REAL_PAIR', True, 'Real registry identities.'))
    pair = None
    try:
        pair = registry.review(con, pair_id, now=now, persist=False)
        result['effective_status'] = pair['status']
        approved = pair['status'] == 'APPROVED' and not pair['approval_blocker']
        checks.append(check('PAIR_APPROVAL', approved, pair['approval_blocker'] or pair['reason'],
                            'Refresh rule evidence and complete a new human pair review.', expires_at=pair['expires_at']))
        valid_mechanics = pair['mechanics_assessment']['status'] == 'REVIEWED_RESEARCH_ONLY'
        checks.append(check('MECHANICS_REVIEW', valid_mechanics, pair['mechanics_assessment'],
                            'Complete source-bound mechanics and cash-availability review.'))
    except (ValueError, KeyError, TypeError) as exc:
        checks.append(check('PAIR_APPROVAL', False, str(exc), 'Repair or refresh registry evidence; do not reuse cached approval.'))
    sides = pair['review'].get('legs', {}) if pair and isinstance(pair['review'], dict) else {}
    books = []
    schemas = []
    for venue, source in zip(mechanics.VENUES, (k_source, p_source)):
        side = sides.get(venue)
        try:
            if side not in {'YES', 'NO'}:
                raise ValueError('selected side is missing; a human pair review is required')
            mechanics.route(venue, side)
            checks.append(check(venue + '.POSITION_ROUTE', True, side))
        except ValueError as exc:
            checks.append(check(venue + '.POSITION_ROUTE', False, str(exc), 'Select supported, reviewed cash-funded long legs.'))
        try:
            if side not in {'YES', 'NO'}:
                raise ValueError('fee side cannot be inferred before pair review')
            _, evidence = current_profile(con, venue, source, side, now=now, hypothetical=False)
            profile = evidence['profile']
            expires = min((profile['expires_at'], profile['effective_until']), key=utc_time)
            result['fees'].append({'venue': venue, 'profile_id': evidence['id'], 'sha256': evidence['sha256'], 'expires_at': expires})
            checks.append(check(venue + '.FEES', True, 'Current capture-bound operator applicability.', expires_at=expires))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            checks.append(check(venue + '.FEES', False, str(exc), 'Capture current fee sources and obtain explicit operator applicability approval.'))
        try:
            # Inspect the newest row even if its receipt is in the future; never hide a bad refresh.
            latest = con.execute('''SELECT b.observation_id,r.schema_version FROM book_captures b
                JOIN raw_observations r ON r.id=b.observation_id WHERE r.venue=? AND b.source_id=?
                ORDER BY b.observation_id DESC LIMIT 1''', (venue, source)).fetchone()
            if latest is None:
                raise ValueError('MISSING_BOOK')
            observed, schema = latest
            inspected = inspect_book(con, observed, now=now)
            book, _, _ = load_book(con, observed, now=now)
            if (book.venue, book.source_id) != (venue, source):
                raise ValueError('PAIR_BOOK_IDENTITY_MISMATCH')
            result['books'].append({key: inspected[key] for key in
                                    ('observation_id', 'venue', 'source_id', 'received_at', 'source_ts',
                                     'transport', 'continuity', 'data_usable', 'rejections')})
            if not inspected['data_usable']:
                raise ValueError(';'.join(inspected['rejections']))
            mechanics.check_book(book, side)
            if venue == 'kalshi' and (book.transport != 'KALSHI_AUTHENTICATED_WS' or schema not in PROTOCOL_SCHEMAS.values()):
                raise ValueError('TIMESTAMPED_KALSHI_STREAM_REQUIRED')
            books.append(book)
            schemas.append(schema)
            lifetime = timedelta(seconds=5 if venue == 'kalshi' else 60)
            expires = min(utc_time(book.received_at) + lifetime, utc_time(book.source_ts) + timedelta(seconds=60),
                          utc_time(book.metadata_received_at) + timedelta(seconds=60))
            if book.market_close_at:
                expires = min(expires, utc_time(book.market_close_at))
            checks.append(check(venue + '.BOOK', True, 'Current raw provenance, timestamps, route and depth shape passed.',
                                expires_at=expires.isoformat()))
        except (ValueError, KeyError, TypeError) as exc:
            checks.append(check(venue + '.BOOK', False, str(exc),
                                'Capture fresh timestamped books and metadata; keep the Kalshi stream connected.'))
    if len(books) == 2:
        comparable = all(abs(utc_time(getattr(books[0], key)) - utc_time(getattr(books[1], key))) <= timedelta(seconds=2)
                         for key in ('source_ts', 'received_at'))
        checks.append(check('BOOK_COMPARABILITY', comparable, 'Source and receipt clocks must each be within two seconds.',
                            'Collect contemporaneous books from both venues.'))
        try:
            step = max(book.quantity_step for book in books)
            if step not in {Decimal('.01'), Decimal('1')}:
                raise ValueError('unsupported common quantity step')
            if not all(walk_depth(book, sides[book.venue], step, now=now).complete for book in books):
                raise ValueError('insufficient displayed depth for one common lot')
            checks.append(check('COMMON_LOT_DEPTH', True, {'contracts': str(step)}))
            result['common_lot'] = str(step)
        except (ValueError, TypeError) as exc:
            checks.append(check('COMMON_LOT_DEPTH', False, str(exc), 'Wait for complete displayed liquidity on both selected sides.'))
        deadline = SEQUENCE_PROTOCOL_END if schemas[0] == PROTOCOL_SCHEMAS['sequence-v1'] else None
        result['protocol_valid_until'] = deadline.isoformat() if deadline else None
        result['horizon_supported'] = deadline is None or now + horizon < deadline
        result['horizon_check'] = check('PROTOCOL_HORIZON', result['horizon_supported'],
                                       {'requested_until': (now + horizon).isoformat(), 'protocol_valid_until': result['protocol_valid_until']},
                                       'Revalidate the clocked protocol before crossing the sequence-v1 cutoff; do not extend it automatically.')
    else:
        checks.append(check('BOOK_COMPARABILITY', False, 'Both usable books are required.', 'Resolve both venue book checks.'))
    result['ready_now'] = all(item['status'] == 'PASS' for item in checks)
    result['valid_until'] = min((c['expires_at'] for c in checks if c['expires_at']), key=utc_time, default=None)
    return result


def _report(con, *, now, session_id, horizon_days, backup_dir):
    report = {'schema': VERSION, 'evaluated_at': now.isoformat(), 'requested_horizon_days': horizon_days,
              'requested_until': (now + timedelta(days=horizon_days)).isoformat(), 'checks': [], 'pairs': [],
              'ready_now': False, 'prerequisites_pass': False, 'protocol_supports_requested_horizon': False, 'status': 'BLOCKED',
              'verification': 'UNVERIFIED', 'trading_authorized': False,
              'multiweek_acceptance': False, 'thirty_day_acceptance': False,
              'deployment_verified': False, 'fees_or_profit_evaluated': False,
              'protocol_constraints': {'sequence_v1_valid_until': SEQUENCE_PROTOCOL_END.isoformat(),
                                       'action': 'Revalidate clocked mode live before the sequence-v1 cutoff; never extend compatibility automatically.'},
              'renewal_required': 'Books need continuous refresh; pair, fee and mechanics evidence expire within 24 hours. Readiness is a snapshot, not a run guarantee.'}
    checks = report['checks']
    version = con.execute('PRAGMA user_version').fetchone()[0]
    report['database_schema'] = version
    checks.append(check('DATABASE_SCHEMA', version in (7, 8, 9), {'actual': version, 'supported': [7, 8, 9]},
                        'Back up and migrate the archive with an authorized writer before using this report.'))
    if version not in (7, 8, 9):
        return report
    counts = con.execute('SELECT COUNT(*),COALESCE(SUM(hypothetical),0) FROM pairs').fetchone()
    hypothetical_sessions = con.execute("SELECT COUNT(*) FROM research_sessions WHERE mode='HYPOTHETICAL_REPLAY'").fetchone()[0]
    report['registry'] = {'total_pairs': counts[0], 'hypothetical_pairs': counts[1], 'pair_limit': MAX_PAIRS,
                          'truncated': counts[0] > MAX_PAIRS}
    checks.append(check('REGISTRY_SCOPE', counts[0] <= MAX_PAIRS, report['registry'], 'Use a research archive within the scanner\'s 50-pair limit.'))
    checks.append(check('LIVE_ARCHIVE', counts[1] == 0 and hypothetical_sessions == 0,
                        {'hypothetical_pairs': counts[1], 'hypothetical_sessions': hypothetical_sessions},
                        'Use a separate archive for live research; never promote hypothetical evidence.'))
    rows = con.execute('SELECT id,kalshi_id,polymarket_us_id,status,hypothetical FROM pairs ORDER BY id LIMIT ?', (MAX_PAIRS,)).fetchall()
    for row in rows:
        try:
            report['pairs'].append(_pair(con, row, now, timedelta(days=horizon_days)))
        except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            report['pairs'].append({'pair_id': row[0], 'ready_now': False, 'horizon_supported': False,
                                    'checks': [check('PAIR_EVIDENCE_ERROR', False, str(exc), 'Repair the archive or recapture evidence.')]})
    eligible = [pair for pair in report['pairs'] if pair['ready_now']]
    report['ready_pair_count'] = len(eligible)
    checks.append(check('CURRENT_PAIR_DATA', bool(eligible), {'ready_pairs': len(eligible)}, 'Resolve the per-pair approval, mechanics, fee and book blockers.'))
    report['discovery'] = {'queue_size': con.execute('SELECT COUNT(*) FROM discovery_queue').fetchone()[0],
                           'latest_ranked_at': None, 'status': 'NOT_OBSERVED', 'required_for_approved_pair_readiness': False}
    discovery = con.execute('SELECT refreshed_at FROM discovery_state WHERE id=1').fetchone()
    if discovery:
        report['discovery'].update(latest_ranked_at=discovery[0], status='RECENT' if now - timedelta(hours=24) <= utc_time(discovery[0]) <= now else 'STALE_OR_FUTURE')
    report['latest_collections'] = [dict(zip(('venue', 'status', 'finished_at'), row)) for row in con.execute('''
        SELECT venue,status,finished_at FROM collection_runs WHERE id IN (SELECT MAX(id) FROM collection_runs GROUP BY venue)''')]
    if session_id is None:
        checks.append(check('SESSION', False, 'No session selected.', 'Create or select a LIVE_READ_ONLY session and pass --session-id.'))
    else:
        try:
            current = session(con, session_id)
            config = policy(current['config'])
            live = current['mode'] == 'LIVE_READ_ONLY' and utc_time(current['started_at']) <= now
            report['session'] = {'id': session_id, **current}
            checks.append(check('SESSION', live, {'mode': current['mode'], 'started_at': current['started_at']}, 'Select a current LIVE_READ_ONLY session.'))
            checks.append(check('RESEARCH_BUDGETS', all(config[v + '_budget'] > 0 for v in mechanics.VENUES),
                                current['config'], 'Declare positive hypothetical research budgets within $10,000; this does not fund accounts.'))
            searchable = [pair['pair_id'] for pair in eligible
                          if 1 <= config['max_contracts'] // Decimal(pair['common_lot']) <= 10000]
            checks.append(check('SEARCH_LIMIT', bool(searchable), {'searchable_ready_pairs': searchable},
                                'Resolve pair data or configure 1..10,000 common lot increments for at least one ready pair.'))
            eligible = [pair for pair in eligible if pair['pair_id'] in searchable]
            operational = health(con, session_id, now=now, backup_dir=backup_dir, record=False)
            report['operations'] = operational
            checks.append(check('HOST_HEALTH', operational['ready'], operational['alerts'], 'Resolve disk, database integrity and clock synchronization failures.'))
            backup_codes = [item['code'] for item in operational['alerts'] if item['code'].startswith('BACKUP_')]
            checks.append(check('BACKUP_OBSERVED', not backup_codes, {'alerts': backup_codes, 'full_content_verification_performed': False},
                                'Create and verify a fresh backup; pass its directory with --backup-dir.'))
            report['run_evidence'] = {'latest_observation': operational['research'],
                                      'cycles': operational['metrics']['research_cycles_total'],
                                      'sustained_run_audited': False}
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
            checks.append(check('SESSION_OR_OPERATIONS', False, str(exc), 'Select a valid session and repair missing operational evidence.'))
    report['ready_now'] = all(item['status'] == 'PASS' for item in checks)
    compatible = any(pair['horizon_supported'] for pair in eligible)
    checks.append(check('REQUESTED_PROTOCOL_HORIZON', compatible,
                        {'compatible_ready_pairs': sum(pair['horizon_supported'] for pair in eligible)},
                        'Resolve current data blockers and any protocol cutoff within the requested horizon.'))
    report['protocol_supports_requested_horizon'] = compatible
    report['prerequisites_pass'] = report['ready_now'] and compatible
    report['status'] = 'PREREQUISITES_PASS_NOW' if report['prerequisites_pass'] else 'BLOCKED'
    report['valid_until'] = min((pair['valid_until'] for pair in eligible if pair.get('valid_until')), key=utc_time, default=None)
    return report


def report(con, *, now=None, session_id=None, horizon_days=21, backup_dir=None):
    now = now or clock()
    if now.tzinfo is None or type(horizon_days) is not int or not 1 <= horizon_days <= 31:
        raise ValueError('readiness requires an aware clock and a 1..31 day horizon')
    if session_id is not None and (type(session_id) is not int or session_id < 1):
        raise ValueError('session-id must be a positive integer')
    now = now.astimezone(timezone.utc)
    # A consistent WAL read snapshot, preserving any outer transaction. No migrations/writes.
    con.execute('SAVEPOINT readiness_snapshot')
    try:
        result = _report(con, now=now, session_id=session_id, horizon_days=horizon_days, backup_dir=backup_dir)
        all_checks = result['checks'] + [item for pair in result['pairs'] for item in pair['checks']]
        result['next_actions'] = list(dict.fromkeys(item['next_action'] for item in all_checks if item['next_action']))
        return result
    finally:
        con.execute('ROLLBACK TO readiness_snapshot')
        con.execute('RELEASE readiness_snapshot')


def render_text(report):
    lines = [f"Research readiness: {report['status']}", f"Evaluated at: {report['evaluated_at']}",
             f"Ready pairs: {report.get('ready_pair_count', 0)}; ready now: {report['ready_now']}",
             f"Earliest ready-pair evidence expiry: {report.get('valid_until') or 'not established'}",
             f"Requested horizon: {report['requested_horizon_days']} days; protocol coverage: {report['protocol_supports_requested_horizon']}",
             'sequence-v1 cutoff: ' + report['protocol_constraints']['sequence_v1_valid_until'],
             report['protocol_constraints']['action']]
    for item in report['checks']:
        lines.append(f"[{item['status']}] {item['code']}: {item['detail']}")
    for pair in report['pairs']:
        lines.append(f"Pair {pair['pair_id']}: {'PASS NOW' if pair['ready_now'] else 'BLOCKED'}")
        for item in pair['checks']:
            if item['status'] != 'PASS':
                lines.append(f"  {item['code']}: {item['detail']} Next: {item['next_action']}")
        if pair.get('horizon_check', {}).get('status') == 'BLOCKED':
            lines.append('  Protocol horizon: ' + pair['horizon_check']['next_action'])
    lines.extend('Next: ' + action for action in report['next_actions'])
    lines += [report['renewal_required'], 'Multiweek acceptance: not established. Trading authorized: false.']
    return '\n'.join(lines) + '\n'
