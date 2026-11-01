"""M5O isolated, unapproved conditional price research. Never execution eligibility.

The approved economics evaluator is intentionally not changed. This module asks
what displayed cash-long depth would cost IF ordinary outcomes aligned and both
legs filled. Unknown fees, account requirements and exceptional payouts stay unknown.
"""
from decimal import Decimal, localcontext

from . import mechanics, registry
from .orderbooks import exact, walk_depth
from .stream_comparison import comparison

VERSION = 'conditional-price-research/m5o-v1'
CAPITAL = ('5', '25', '100', '500')


def contract_fingerprint(venue, market):
    excluded = registry.K_VOLATILE if venue == 'kalshi' else registry.P_VOLATILE | {'marketSides'}
    contract = {k: v for k, v in market.items() if k not in excluded}
    if venue == 'polymarket_us':
        contract['marketSides'] = [{k: v for k, v in side.items()
            if k not in {'price', 'quote', 'createdAt', 'updatedAt'}} for side in market['marketSides']]
    return registry.digest(contract)


def classification(pair):
    # No assistant-produced configuration can confer STRICT status. Real approvals
    # still go through registry/research and their source-bound validity checks.
    if pair.get('classification') not in {'CONDITIONAL', 'DISCOVERY'}:
        raise ValueError('M5O has no source-bound STRICT approval; use approved research workflow')
    if pair['classification'] == 'CONDITIONAL' and not pair.get('ordinary_basis'):
        raise ValueError('conditional classification requires an explicit ordinary-outcome basis')
    if not pair.get('residual_risks'):
        raise ValueError('unresolved risk disclosure required')
    return pair['classification']


def quality(books, inspected, now):
    reports = {}
    for book, saved in zip(books, inspected):
        reasons = sorted(set(saved['rejections']) | set(book.issues(now=now)))
        reports[book.venue] = dict(source_ts=book.source_ts, received_at=book.received_at,
            rejections=reasons, data_usable=not reasons,
            connected='STREAM_DISCONNECTED' not in reasons)
    return comparison(reports, now)


def quote_cases(books, pair, *, now, inspected):
    """Only unchanged data-quality gates can admit conditional gross price math.

    Budgets are quote costs before UNKNOWN fees/collateral. Both ladders must pass
    normalizer/grid/lot/state/metadata checks, plus two-second source/receipt ages
    and skews. Synthetic US NO is never modeled as a cash long.
    """
    group = classification(pair)
    if len(books) != 2 or [b.venue for b in books] != ['kalshi', 'polymarket_us']:
        raise ValueError('exact ordered venue pair required')
    if len(inspected) != 2 or [b.source_id for b in books] != [pair['kalshi_id'], pair['polymarket_us_id']]:
        raise ValueError('pair/book identity mismatch')
    checked = quality(books, inspected, now)
    result = {'schema': VERSION, 'classification': group, 'quality': checked,
        'strict_arbitrage_eligible': False, 'trading_authorized': False,
        'verification': 'UNVERIFIED', 'net_edge_usd': None,
        'fee_status': 'UNKNOWN_UNREVIEWED', 'cash_release_at': None,
        'supported_direction': 'KALSHI_NO_PLUS_US_LONG_YES',
        'reverse_direction': 'BLOCKED_US_SYNTHETIC_NO_COLLATERAL_UNMODELED',
        'residual_risks': pair['residual_risks'], 'capital_cases': [],
        'fill_assumption': 'HYPOTHETICAL_SIMULTANEOUS_FULL_FILLS_OF_DISPLAYED_DEPTH'}
    if not checked['timestamp_depth_overlap'] or group == 'DISCOVERY':
        result['status'] = 'DISCOVERY_ONLY' if group == 'DISCOVERY' else 'REJECTED_DATA_QUALITY'
        return result
    for book, side in zip(books, ('NO', 'YES')):
        mechanics.check_book(book, side)
    with localcontext() as ctx:
        ctx.prec = 80
        step = max(b.quantity_step for b in books)
        if step not in {Decimal('0.01'), Decimal('1')}:
            raise ValueError('unsupported common lot')
        ladders = [books[0].no_asks, books[1].yes_asks]
        cap = min(sum(x.quantity for x in side) for side in ladders)
        cap = (cap // step) * step

        def cost(q):
            return [walk_depth(b, s, q, now=now).quote_cost for b, s in zip(books, ('NO', 'YES'))]

        # Concave gross profit: marginal prices increase along the two ladders.
        # Find its maximum on the common lot lattice, with exact Decimal costs.
        def best_quantity(upper):
            lo, hi = 0, int(upper // step)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                q = mid * step
                marginal = sum(cost(q)) - (sum(cost(q-step)) if mid > 1 else Decimal(0))
                if marginal < step: lo = mid
                else: hi = mid - 1
            return lo * step

        for dollars in CAPITAL:
            budget = Decimal(dollars)
            lo, hi = 0, int(cap // step)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if sum(cost(mid * step)) <= budget: lo = mid
                else: hi = mid - 1
            maximum = lo * step
            best = best_quantity(maximum)
            q = best or maximum
            costs = cost(q) if q else [Decimal(0), Decimal(0)]
            gross = q - sum(costs)
            result['capital_cases'].append({
                'quote_only_budget_usd': dollars,
                'maximum_matched_displayed_quantity': cap,
                'maximum_quantity_within_quote_budget': maximum,
                'evaluated_quantity': q,
                'prefee_capital_per_venue_usd': dict(zip(('kalshi', 'polymarket_us'), costs)),
                'prefee_capital_usd': sum(costs), 'all_in_capital_usd': None,
                'ordinary_combined_payout_assumption_usd': q,
                'gross_edge_usd': gross, 'fee_adjusted_edge_usd': None,
                'positive_conditional_discrepancy': q > 0 and gross > 0,
                'combined_fee_break_even_usd': max(Decimal(0), gross),
                'depth_limited_before_budget': maximum == cap,
                'loss_if_selected_legs_both_pay_zero_before_fees_usd': sum(costs),
                'exceptional_payout_basis': pair.get('exceptional_scenario', 'UNVERIFIED'),
                'hypothetical_combined_fee_per_unit_sensitivity': {
                    fee: gross - q * Decimal(fee) for fee in ('0.01', '0.02', '0.05')},
                'settlement_delay_seconds': None, 'cash_release_delay_seconds': None,
                'fees_and_additional_collateral': 'UNKNOWN',
            })
    result['status'] = 'CONDITIONAL_GROSS_ONLY'
    return result
