"""Bounded exact two-leg research evaluator; no execution, leverage or synthetic shorts."""
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal, localcontext

from .fees import quote_fee_bound
from .orderbooks import exact, walk_depth
from .validation import utc_time

VERSION = 'economics/m4-v1'
VENUES = ('kalshi', 'polymarket_us')


def policy(data):
    required = {'max_contracts', 'kalshi_budget', 'polymarket_us_budget', 'reserve_per_leg', 'min_profit'}
    if set(data) != required:
        raise ValueError('policy requires exactly: ' + ', '.join(sorted(required)))
    result = {key: exact(value) for key, value in data.items()}
    if result['max_contracts'] <= 0 or result['reserve_per_leg'] <= 0:
        raise ValueError('positive contract limit and explicit positive per-leg reserve required')
    if result['kalshi_budget'] + result['polymarket_us_budget'] > 10000:
        raise ValueError('research budget exceeds $10,000 ceiling')
    return result


def seconds(delta):
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def evaluate(books, sides, models, settlement_at, config, *, now, max_age=60):
    """Search every common supported lot up to the requested limit (at most 10,000).

    Select highest positive conservative total profit within independent venue budgets.
    A failed smaller quantity does not hide larger quantities that overcome rounding.
    Caller must establish reviewed complementarity; production scanner does so first.
    """
    with localcontext() as context:
        context.prec = 80
        config = policy(config)
        if len(books) != 2 or len(sides) != 2 or len(models) != 2 or len(settlement_at) != 2:
            raise ValueError('exactly two legs required')
        days = []
        for book, venue, side, model, settlement in zip(books, VENUES, sides, models, settlement_at):
            if book.venue != venue:
                raise ValueError('venue order mismatch')
            if book.issues(now=now, max_age=max_age):
                raise ValueError('BOOK_REJECTED: ' + ';'.join(book.issues(now=now, max_age=max_age)))
            if venue == 'polymarket_us' and side != 'YES':
                raise ValueError('SYNTHETIC_US_NO_UNSUPPORTED_CAPITAL_MECHANICS')
            model.check(venue=venue, source_id=book.source_id, side=side, now=now)
            duration = seconds(utc_time(settlement) - now) / 86400
            if duration <= 0:
                raise ValueError('settlement must be in the future')
            days.append(duration)
        # M3 supported steps divide one another (.01 or 1), so max is their common lattice.
        steps = [book.quantity_step for book in books]
        if any(step not in {Decimal('.01'), Decimal('1')} for step in steps):
            raise ValueError('unsupported lot lattice')
        step = max(steps)
        count = int(config['max_contracts'] // step)
        if count < 1 or count > 10000:
            raise ValueError('SEARCH_LIMIT: require 1..10000 common lot increments')
        best = None
        tested = 0
        exhausted = False
        for index in range(1, count + 1):
            quantity = step * index
            depth = [walk_depth(book, side, quantity, now=now, max_age=max_age) for book, side in zip(books, sides)]
            if not all(item.complete for item in depth):
                exhausted = True
                break
            tested += 1
            fees = [quote_fee_bound(model, item.levels, book.quantity_step)
                    for model, item, book in zip(models, depth, books)]
            reserve = quantity * config['reserve_per_leg']
            capital = [item.quote_cost + fee + reserve for item, fee in zip(depth, fees)]
            if any(amount > config[venue + '_budget'] for amount, venue in zip(capital, VENUES)):
                continue
            profit = quantity - sum(capital)
            if profit <= 0 or profit < config['min_profit']:
                continue
            capital_days = sum(amount * duration for amount, duration in zip(capital, days))
            candidate = {'contracts': quantity, 'quote_costs': [item.quote_cost for item in depth],
                         'fee_bounds': fees, 'reserve_per_venue': reserve, 'capital_per_venue': capital,
                         'total_capital': sum(capital), 'net_profit_bound': profit,
                         'locked_capital_days': capital_days, 'profit_per_capital_day': profit / capital_days,
                         'settlement_at': settlement_at, 'depth': [asdict(item) for item in depth]}
            if best is None or (profit, -sum(capital)) > (best['net_profit_bound'], -best['total_capital']):
                best = candidate
        return {'version': VERSION, 'status': 'MODELED_EDGE' if best else 'REJECTED', 'best': best,
                'rejections': [] if best else ['NO_POSITIVE_EDGE_WITHIN_DEPTH_AND_BUDGETS'],
                'quantities_tested': tested, 'depth_exhausted': exhausted,
                'assumptions': ['SIMULTANEOUS_FULL_FILLS_HYPOTHETICAL', 'HOLD_TO_REVIEWED_SETTLEMENT',
                                'NO_REBATES_OR_TRANSFERS', 'UNKNOWN_FILL_PARTITION_FEE_UPPER_BOUND'],
                'verification': 'UNVERIFIED', 'trading_authorized': False}
