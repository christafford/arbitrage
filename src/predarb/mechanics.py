"""M5A D: reviewed cash-funded long positions; no margin or short execution model."""
from datetime import timedelta
from decimal import Decimal, localcontext

from .orderbooks import exact
from .validation import field, text_field, utc_time

VERSION = 'payout-mechanics/m5a-d-v1'
VENUES = ('kalshi', 'polymarket_us')
CASES = {'YES', 'NO', 'VOID', 'CANCELLED', 'SUSPENDED', 'SOURCE_REVISION'}
ROUTES = {
    ('kalshi', 'YES'): 'BUY_YES_FROM_COMPLEMENTARY_NO_BID',
    ('kalshi', 'NO'): 'BUY_NO_FROM_COMPLEMENTARY_YES_BID',
    ('polymarket_us', 'YES'): 'BUY_LONG_FROM_OFFER',
}
ROLES = ('payout_rules', 'collateral', 'settlement_timing')


def route(venue, side):
    if venue == 'polymarket_us' and side == 'NO':
        raise ValueError('SYNTHETIC_US_NO_UNSUPPORTED_CAPITAL_MECHANICS: requires full payout collateral; 1-bid is not collateral')
    if (venue, side) not in ROUTES:
        raise ValueError('UNKNOWN_POSITION_MECHANISM')
    return ROUTES[venue, side]


def check_book(book, side):
    expected = route(book.venue, side)
    actual = book.mechanism_yes if side == 'YES' else book.mechanism_no
    if actual != expected:
        raise ValueError('BOOK_POSITION_MECHANISM_MISMATCH')
    return expected


def template():
    return {'schema': VERSION, 'reviewed': False, 'position_scope': '',
            'netting': '', 'funding': '', 'timing_basis': '',
            'venues': {venue: {'route': '', 'currency': '', 'notional': '',
                               'additional_collateral_per_contract': '',
                               'account_scope_reviewed': '', 'payout_precision_reviewed': '',
                               'documents': {role: [] for role in ROLES}}
                       for venue in VENUES}}


def scenario_terms(scenarios, *, now):
    """Validate cash availability separately from determination/settlement timestamps."""
    if type(scenarios) is not list or not 6 <= len(scenarios) <= 30:
        raise ValueError('MECHANICS: six settlement cases required, at most 30 scenarios')
    covered = set()
    latest = [None, None]
    for row in scenarios:
        case = text_field(row, 'case')
        if case not in CASES:
            raise ValueError('MECHANICS: unknown settlement case')
        covered.add(case)
        text_field(row, 'condition')
        with localcontext() as context:
            context.prec = 80
            payouts = [exact(text_field(row, v + '_payout'), price=True) for v in VENUES]
            if sum(payouts) != 1:
                raise ValueError('MECHANICS: reviewed payouts are not complementary')
        for i, venue in enumerate(VENUES):
            settlement = utc_time(text_field(row, venue + '_settlement_at'))
            available = utc_time(text_field(row, venue + '_cash_available_at'))
            if not now < settlement <= available:
                raise ValueError('MECHANICS: cash availability must follow future settlement')
            # Bound only local input magnitude, not a claim about venue settlement guarantees.
            if available > now + timedelta(days=36525):
                raise ValueError('MECHANICS: cash timing exceeds supported 100-year research horizon')
            latest[i] = max(latest[i], available) if latest[i] else available
    if covered != CASES:
        raise ValueError('MECHANICS: missing settlement cases')
    return [value.isoformat() for value in latest]


def validate_review(data, bundle, *, now):
    mechanics = field(data, 'mechanics', dict)
    if text_field(mechanics, 'schema') != VERSION or field(mechanics, 'reviewed', bool) is not True:
        raise ValueError('MECHANICS_REVIEW_REQUIRED')
    constants = {'position_scope': 'NEW_ISOLATED_LONG_POSITIONS', 'netting': 'NONE',
                 'funding': 'CASH_ONLY_NO_PROCEEDS_REUSE', 'timing_basis': 'OPERATOR_CONSERVATIVE_ASSUMPTION'}
    for key, value in constants.items():
        if text_field(mechanics, key) != value:
            raise ValueError('UNSUPPORTED_MECHANICS: ' + key)
    venues = field(mechanics, 'venues', dict)
    if set(venues) != set(VENUES):
        raise ValueError('MECHANICS: exact venues required')
    legs = field(data, 'legs', dict)
    mapping = field(data, 'outcome_mapping', dict)
    if (set(legs) != set(VENUES) or set(mapping) != {'YES', 'NO'} or
            any(type(value) is not str for value in mapping.values()) or set(mapping.values()) != {'YES', 'NO'}):
        raise ValueError('MECHANICS: exact legs and bijective outcome mapping required')
    for head in bundle['instruments']:
        venue = head['venue']
        terms = field(venues, venue, dict)
        if text_field(terms, 'route') != route(venue, text_field(legs, venue)):
            raise ValueError('MECHANICS: selected route mismatch')
        if text_field(terms, 'currency') != 'USD' or exact(text_field(terms, 'notional')) != 1:
            raise ValueError('MECHANICS: only USD one-dollar contracts supported')
        if exact(text_field(terms, 'additional_collateral_per_contract')) != 0:
            raise ValueError('MECHANICS: additional collateral unsupported')
        for key in ('account_scope_reviewed', 'payout_precision_reviewed'):
            text_field(terms, key)
        documents = {doc['raw_sha256']: doc for doc in head['documents']}
        evidence = field(terms, 'documents', dict)
        if set(evidence) != set(ROLES):
            raise ValueError('MECHANICS: payout, collateral and settlement source roles required')
        for role in ROLES:
            references = field(evidence, role, list)
            if not 1 <= len(references) <= 10 or any(type(value) is not str for value in references):
                raise ValueError('MECHANICS: source hashes required for ' + role)
            if len(set(references)) != len(references):
                raise ValueError('MECHANICS: duplicate source hashes')
            for digest in references:
                if digest not in documents:
                    raise ValueError('MECHANICS: source is not in the current instrument review bundle')
                retrieved = utc_time(documents[digest]['retrieved_at'])
                if not now - timedelta(hours=24) <= retrieved <= now + timedelta(seconds=5):
                    raise ValueError('MECHANICS: stale or future source')
    scenarios = field(data, 'settlement_scenarios', list)
    latest = scenario_terms(scenarios, now=now)
    if mapping[legs['kalshi']] == legs['polymarket_us']:
        raise ValueError('MECHANICS: selected legs are not complementary')
    for scenario in scenarios:
        if scenario['case'] in {'YES', 'NO'}:
            expected = [int(legs['kalshi'] == scenario['case']), int(legs['polymarket_us'] == mapping[scenario['case']])]
            if [exact(scenario[v + '_payout'], price=True) for v in VENUES] != expected:
                raise ValueError('MECHANICS: payout contradicts selected legs and outcome mapping')
    return latest


def assess(data, bundle, *, now):
    if data is None:
        return {'status': 'UNVERIFIED', 'reasons': ['MECHANICS_REVIEW_REQUIRED'], 'trading_authorized': False}
    try:
        latest = validate_review(data, bundle, now=now)
        return {'status': 'REVIEWED_RESEARCH_ONLY', 'latest_cash_available_at': latest,
                'timing_basis': 'OPERATOR_CONSERVATIVE_ASSUMPTION', 'trading_authorized': False}
    except ValueError as exc:
        return {'status': 'UNVERIFIED', 'reasons': [str(exc)], 'trading_authorized': False}


def capital(book, side, quote_cost, fee_bound, reserve):
    mechanism = check_book(book, side)
    with localcontext() as context:
        context.prec = 80
        cost, fee, held = (exact(value, string=False) for value in (quote_cost, fee_bound, reserve))
        return {'venue': book.venue, 'source_id': book.source_id, 'side': side, 'mechanism': mechanism,
                'purchase_cash_debit': cost, 'fee_cash_reserved': fee, 'slippage_cash_reserved': held,
                'additional_collateral': Decimal('0'), 'sale_proceeds': Decimal('0'),
                'research_cash_required': cost + fee + held,
                'netting': 'NONE', 'proceeds_reused': False}


def payout_cashflows(scenarios, quantities):
    """Only exact cent-representable payouts; never guess fractional settlement rounding.

    Quantities may differ for paper partial fills. Return per-venue cash events so
    reserve/capital cannot be confused with a second collateral charge or payout.
    scenario_terms must have checked cases/timing before this numerical hot path.
    """
    if len(quantities) != 2:
        raise ValueError('two settlement quantities required')
    with localcontext() as context:
        context.prec = 80
        quantities = [exact(q, string=False) for q in quantities]
        results = []
        for row in scenarios:
            amounts = [q * exact(text_field(row, v + '_payout'), price=True) for q, v in zip(quantities, VENUES)]
            if any(amount % Decimal('.01') for amount in amounts):
                raise ValueError('PAYOUT_PRECISION_UNVERIFIED: settlement would require sub-cent rounding')
            results.append({'case': row['case'], 'condition': row['condition'], 'payout_per_venue': amounts,
                            'total_payout': sum(amounts),
                            'cash_available_at': [row[v + '_cash_available_at'] for v in VENUES]})
        if not results:
            raise ValueError('settlement cashflows required')
        return results
