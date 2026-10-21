"""Versioned taker fee math. Actual fill sequences and quote upper bounds are distinct."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext

from .orderbooks import exact
from .validation import field, identifier, text_field, utc_time

VERSION = 'taker-fees/m4-v1'
CENT = Decimal('.01')
MICRO = Decimal('.000001')
ONE = Decimal('1')


def rounded(value, quantum, mode):
    return (value / quantum).to_integral_value(rounding=mode) * quantum


@dataclass(frozen=True)
class FeeModel:
    venue: str
    source_id: str
    side: str
    coefficient: Decimal
    balance_precision: Decimal
    settlement_fee_per_contract: Decimal
    effective_from: str
    effective_until: str
    version: str

    def check(self, *, venue, source_id, side, now):
        if (venue, source_id, side) != (self.venue, self.source_id, self.side):
            raise ValueError('FEE_IDENTITY_MISMATCH')
        if not utc_time(self.effective_from) <= now < utc_time(self.effective_until):
            raise ValueError('FEE_OUTSIDE_EFFECTIVE_WINDOW')


def model_from_profile(data):
    if text_field(data, 'schema') != VERSION:
        raise ValueError('unsupported fee schema')
    venue, source_id, side = (text_field(data, k) for k in ('venue', 'source_id', 'side'))
    identifier(source_id)
    if side not in {'YES', 'NO'}:
        raise ValueError('invalid fee side')
    kind = text_field(data, 'kind')
    with localcontext() as context:
        context.prec = 80
        if venue == 'kalshi':
            if kind not in {'quadratic', 'quadratic_with_maker_fees', 'quadratic_with_combo_maker_fees'}:
                raise ValueError('unsupported Kalshi fee type; no flat/combo model')
            multiplier = exact(text_field(data, 'multiplier'))
            if multiplier > 100:
                raise ValueError('unsupported fee multiplier')
            coefficient = Decimal('.07') * multiplier
            precision = exact(text_field(data, 'balance_precision'), positive=True)
            if precision not in {Decimal('.0001'), CENT}:
                raise ValueError('explicit direct/non-direct balance precision required')
        elif venue == 'polymarket_us':
            if kind not in {'standard', 'table_tennis'}:
                raise ValueError('unsupported US fee type; no combo model')
            coefficient = Decimal('.0695') if kind == 'standard' else Decimal('.10')
            precision = CENT
            if utc_time(text_field(data, 'effective_from')) < utc_time('2026-10-19T17:00:00Z'):
                raise ValueError('US fee model predates verified schedule')
        else:
            raise ValueError('unsupported fee venue')
    start, end = (text_field(data, k) for k in ('effective_from', 'effective_until'))
    if utc_time(start) >= utc_time(end):
        raise ValueError('invalid fee window')
    settlement_fee = exact(text_field(data, 'settlement_fee_per_contract'))
    return FeeModel(venue, source_id, side, coefficient, precision, settlement_fee, start, end, text_field(data, 'version'))


def fill_fees(model, fills):
    """Exact documented rounding for a DECLARED buy-fill partition of one taker order.

    Does not predict resting-order fragmentation, rebates from account tiers, or executions.
    """
    with localcontext() as context:
        context.prec = 80
        total = accumulator = cumulative_raw = Decimal('0')
        rows = []
        for fill in fills:
            p, q = exact(fill.price, positive=True, price=True, string=False), exact(fill.quantity, positive=True, string=False)
            if p >= 1:
                raise ValueError('invalid fill price')
            raw = model.coefficient * q * p * (ONE - p)
            if model.venue == 'kalshi':
                cost = p * q
                trade = rounded(raw, MICRO, ROUND_CEILING)
                rounding = rounded(cost + trade, model.balance_precision, ROUND_CEILING) - cost - trade
                accumulator += rounding
                rebate = min(rounded(accumulator, model.balance_precision, ROUND_FLOOR),
                             rounded(trade + rounding, model.balance_precision, ROUND_FLOOR))
                accumulator -= rebate
                charge = trade + rounding - rebate
            else:
                cumulative_raw += raw
                charge = min(rounded(raw, CENT, ROUND_HALF_EVEN),
                             max(Decimal('0'), rounded(cumulative_raw, CENT, ROUND_HALF_EVEN) - total))
                trade, rounding, rebate = raw, charge - raw, Decimal('0')
            total += charge
            rows.append({'price': p, 'quantity': q, 'raw_fee': raw, 'trade_fee': trade,
                         'rounding_adjustment': rounding, 'rebate': rebate, 'charge': charge})
        return {'total': total, 'fills': rows, 'version': VERSION, 'partition': 'DECLARED_HYPOTHETICAL'}


def quote_fee_bound(model, levels, quantity_step):
    """Conservative fee bound without knowing the number of resting orders per level.

    Kalshi: split into smallest supported count units, discard rebates. US: documented
    order-wide half-even cumulative cap, independent of fill fragmentation. No discounts.
    """
    with localcontext() as context:
        context.prec = 80
        step = exact(quantity_step, positive=True, string=False)
        if step not in {Decimal('.01'), ONE}:
            raise ValueError('unsupported fill quantity granularity')
        raw = bound = Decimal('0')
        for level in levels:
            p, q = level.price, level.quantity
            if q % step:
                raise ValueError('off-grid fee quantity')
            raw += model.coefficient * q * p * (ONE - p)
            if model.venue == 'kalshi':
                unit_fee = rounded(model.coefficient * step * p * (ONE - p), MICRO, ROUND_CEILING)
                bound += (q / step) * (rounded(p * step + unit_fee, model.balance_precision, ROUND_CEILING) - p * step)
        if model.venue == 'polymarket_us':
            bound = rounded(raw, CENT, ROUND_HALF_EVEN)
        return bound + sum(level.quantity for level in levels) * model.settlement_fee_per_contract
