"""M5R offline sensitivities and attribution; never approvals or live eligibility."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal, localcontext

from .conditional_research import classification, quality
from .fees import FeeModel, fill_fees, quote_fee_bound
from .mechanics import check_book
from .models import AskLevel
from .orderbooks import exact, walk_depth
from .quality_capture import Engine, seconds
from .validation import utc_time
from .validation import field, text_field
from .fee_capture import fee_parameters
from . import kalshi

VERSION = 'economic-viability/m5r-v1'
ZERO = Decimal(0)
SIDES = ('NO', 'YES')


def fee_history(series_id, event_id, responses):
    """Validate retrospective public history without treating it as account proof."""
    series, event, changes, overrides = responses
    kalshi.validate_series(series)
    kalshi.validate_event(event)
    s,e = series['series'],event['event']
    if s['ticker'] != series_id or e['series_ticker'] != series_id or e['event_ticker'] != event_id:
        raise ValueError('fee history identity mismatch')
    current = fee_parameters(s)
    event_override = (e.get('fee_type_override'),e.get('fee_multiplier_override'))
    if event_override != (None,None): current = fee_parameters(e,override=True)
    histories = [field(changes,'series_fee_change_arr',list),field(overrides,'event_fee_changes',list)]
    if text_field(overrides,'cursor',empty=True):
        raise ValueError('incomplete fee history pagination')
    for index,history in enumerate(histories):
        seen=set()
        for row in history:
            identity=text_field(row,'id')
            if identity in seen or text_field(row,'series_ticker') != series_id:
                raise ValueError('fee history identity or duplicate')
            seen.add(identity);utc_time(text_field(row,'scheduled_ts'))
            if index:
                if text_field(row,'event_ticker') != event_id:
                    raise ValueError('fee event history identity')
                if 'fee_type_override' not in row or 'fee_multiplier_override' not in row:
                    raise ValueError('missing paired fee override')
                if (row['fee_type_override'],row['fee_multiplier_override']) != (None,None):
                    fee_parameters(row,override=True)
            else: fee_parameters(row)
    return dict(series=series_id,event=event_id,current_parameters=current,
        current_event_override=event_override != (None,None),
        series_changes=histories[0],event_changes=histories[1],
        historical_account_applicability='UNKNOWN',empty_history_is_historical_proof=False)


def sensitivity(books, pair, *, at, budget, kalshi_fraction=None, reserve=ZERO,
                us_coefficient=Decimal('.0695')):
    """Gross-optimal displayed depth with explicit split cash caps and fee scenarios.

    A flexible split is an ex-ante funding assumption, never an instantaneous
    cross-venue transfer. Fees remain hypothetical even when a formula is sourced.
    """
    with localcontext() as ctx:
        ctx.prec = 80
        return _sensitivity(books, pair, at, budget, kalshi_fraction, reserve, us_coefficient)


def _sensitivity(books, pair, at, budget, fraction, reserve, us_coefficient):
    group = classification(pair)
    budget = exact(budget, positive=True, string=False)
    reserve = exact(reserve, string=False)
    us_coefficient = exact(us_coefficient, positive=True, string=False)
    if us_coefficient not in tuple(map(Decimal,('.0695','.075','.085','.095'))):
        raise ValueError('unsupported published non-table-tennis fee sensitivity')
    if reserve >= budget:
        raise ValueError('reserve must leave positive research capital')
    if fraction is not None:
        fraction = exact(fraction, positive=True, string=False)
        if fraction >= 1:
            raise ValueError('both venues require cash')
    if len(books) != 2 or [(b.venue, b.source_id) for b in books] != [
            ('kalshi', pair['kalshi_id']), ('polymarket_us', pair['polymarket_us_id'])]:
        raise ValueError('ordered source-bound pair required')
    checked = quality(books, [b.as_dict(now=at) for b in books], at)
    out = dict(schema=VERSION, classification=group, verification='UNVERIFIED',
        actual_net_profit_usd=None, cash_release_at=None, trading_authorized=False,
        actual_fills=None, strict_arbitrage_eligible=False, quality=checked,
        budget_usd=budget, reserve_usd=reserve, kalshi_fraction=fraction,
        fee_applicability='UNKNOWN; all fee calculations below are HYPOTHETICAL',
        cases=[], payout_assumption='HYPOTHETICAL $1 combined ordinary payout per matched unit')
    if not checked['timestamp_depth_overlap']:
        return out
    for book, side in zip(books, SIDES):
        check_book(book, side)
    step = max(b.quantity_step for b in books)
    if step not in (Decimal('.01'), Decimal(1)):
        raise ValueError('unsupported common lot')
    ladders = [books[0].no_asks, books[1].yes_asks]
    # Revalidate the typed boundary: callers cannot smuggle invalid fixture prices.
    for b, ladder in zip(books, ladders):
        previous = ZERO
        for level in ladder:
            p = exact(level.price, positive=True, price=True, string=False)
            q = exact(level.quantity, positive=True, string=False)
            if p >= 1 or p <= previous or q % b.quantity_step:
                raise ValueError('invalid ordered ladder or lot')
            if not any(x.start <= p <= x.end and (p-x.start) % x.step == 0 for x in b.price_bands):
                raise ValueError('off-grid price')
            previous = p
    cap = min(sum((x.quantity for x in ladder), ZERO) for ladder in ladders)
    available = budget-reserve
    caps = None if fraction is None else (available*fraction, available*(1-fraction))

    def walks(q):
        return [walk_depth(b, side, q, now=at) for b, side in zip(books, SIDES)] if q else []

    def costs(q):
        return [w.quote_cost for w in walks(q)] if q else [ZERO, ZERO]

    def search(predicate, upper):
        lo, hi = 0, int(upper//step)
        while lo < hi:
            mid = (lo+hi+1)//2
            if predicate(mid*step): lo = mid
            else: hi = mid-1
        return lo*step

    def within(values):
        return sum(values) <= available and (caps is None or all(v <= c for v,c in zip(values,caps)))

    maximum = search(lambda q: within(costs(q)), cap)
    q = search(lambda q: sum(costs(q))-sum(costs(q-step)) < step, maximum)
    depth = walks(q)
    purchase = costs(q)
    gross = q-sum(purchase)
    out.update(maximum_displayed_quantity=cap, maximum_quote_funded_quantity=maximum,
        gross_optimal_quantity=q, purchase_per_venue_usd=purchase,
        split_caps_usd=caps, gross_usd=gross, combined_fee_break_even_usd=gross,
        combined_fee_break_even_per_unit_usd=gross/q if q else None,
        idle_before_fees_usd=budget-sum(purchase),
        one_leg_loss_before_fees_usd=purchase,
        both_legs_zero_loss_before_fees_usd=sum(purchase),
        depth_limited=maximum == (cap//step)*step)
    # Declared one-fill-per-price-level partition versus one-contract fragments.
    # These are scenarios, not predictions about matching or fee applicability.
    for precision in (Decimal('.0001'), Decimal('.01')):
        models = [FeeModel(b.venue,b.source_id,s,c,precision if i == 0 else Decimal('.01'),
            ZERO,'HYPOTHETICAL','HYPOTHETICAL','published-formula-sensitivity')
            for i,(b,s,c) in enumerate(zip(books,SIDES,(Decimal('.07'),us_coefficient)))]

        def bounds(quantity):
            ws = walks(quantity)
            return [quote_fee_bound(m,w.levels,b.quantity_step)
                    for m,w,b in zip(models,ws,books)] if quantity else [ZERO,ZERO]

        bounded = search(lambda quantity: within([c+f for c,f in zip(costs(quantity),bounds(quantity))]), q)
        per_level = [fill_fees(m,w.levels)['total'] for m,w in zip(models,depth)] if q else [ZERO,ZERO]
        fragmented = []
        for model, walk in zip(models,depth):
            fragments = []
            for level in walk.levels:
                whole = int(level.quantity)
                fragments.extend([AskLevel(level.price,Decimal(1))]*whole)
                remainder = level.quantity-whole
                if remainder: fragments.append(AskLevel(level.price,remainder))
            fragmented.append(fill_fees(model,fragments)['total'])
        if not q: fragmented = [ZERO,ZERO]
        upper = bounds(q)
        out['cases'].append(dict(label='HYPOTHETICAL_STANDARD_TAKER_NO_DISCOUNTS',
            kalshi_multiplier=Decimal(1), kalshi_balance_precision=precision,
            us_coefficient=us_coefficient, assumed_settlement_fee_usd=ZERO,
            actual_account_or_historical_applicability='UNKNOWN',
            per_level_fees_usd=per_level, one_contract_partition_fees_usd=fragmented,
            minimum_lot_no_rebate_fee_bound_usd=upper,
            per_level_net_usd=gross-sum(per_level),
            one_contract_partition_net_usd=gross-sum(fragmented),
            conservative_net_lower_bound_usd=gross-sum(upper),
            gross_quantity_fits_with_bound=within([c+f for c,f in zip(purchase,upper)]),
            maximum_quantity_with_bound_and_positive_gross=bounded,
            bound_funded_purchase_usd=costs(bounded), bound_funded_fees_usd=bounds(bounded),
            bound_funded_net_usd=bounded-sum(costs(bounded))-sum(bounds(bounded))))
    return out


def cause(code):
    """Exhaustive attribution with explicit OTHER; never silently drop failures."""
    suffix = code.split(':',1)[-1]
    if 'SKEW' in code: return 'cross_venue_skew'
    if 'METADATA' in code and 'ROTATION' not in code: return 'metadata_validity'
    if suffix in {'SOURCE_NOT_WITHIN_2S','STALE_SOURCE','FUTURE_SOURCE','UNKNOWN_SOURCE_TIME','SOURCE_AFTER_RECEIPT'}:
        return 'kalshi_source_age' if code.startswith('kalshi:') else 'us_source_age'
    if suffix in {'RECEIPT_NOT_WITHIN_2S','STALE_RECEIPT','FUTURE_RECEIPT'}: return 'receipt_age'
    if 'MISSING_BOOK' in code: return 'startup_missing_state'
    if any(s in code for s in ('DISCONNECTED','PENDING','ROTATION','RECEIVER_ENDED','BUDGET_COMPLETE','SEQUENCE','GAP')):
        return 'continuity_or_local_barrier'
    return 'other_fail_closed'


class Attribution(Engine):
    """Read-only diagnostic companion to an independently audited Engine replay.

    Combination bins are exclusive; reason/category totals overlap. Removing a
    category measures an arithmetic ceiling, not a proposal to accept stale books.
    """
    def __init__(self, pair, start, deadline):
        super().__init__(pair,start,deadline)
        self.bins = Counter()
        self.overlap = Counter()
        self.sole = Counter()
        self.latencies = {c:dict(source_to_receipt=[],receipt_to_available=[],arrival_source_stale=0,
                                source_gap=[],unchanged_source=0) for c in ('kalshi','us_ws')}
        self.last_source = {}

    def advance(self, at):
        at = min(utc_time(at),self.deadline)
        if at < self.previous: raise ValueError('event clock regressed')
        cuts = {self.previous,at}
        for state in self.states.values():
            b = state.book
            if b is None: continue
            for stamp,age in [(b.received_at,2),(b.source_ts,2),(b.metadata_received_at,60),(b.market_close_at,0)]:
                if stamp:
                    for point in (utc_time(stamp),utc_time(stamp)+timedelta(seconds=age)):
                        if self.previous < point < at: cuts.add(point)
        ordered = sorted(cuts)
        for left,right in zip(ordered,ordered[1:]):
            width = seconds(right-left)
            codes = self.assess('us_ws',left+(right-left)/2)['quality']['rejections']
            categories = sorted({cause(c) for c in codes})
            self.bins['+'.join(categories) or 'VALID'] += width
            for category in categories: self.overlap[category] += width
            if len(categories) == 1: self.sole[categories[0]] += width
        super().advance(at.isoformat())

    def event(self, event, book=None):
        super().event(event,book)
        channel = event.get('channel')
        if book is not None and channel in self.latencies:
            r = self.latencies[channel]
            lag = seconds(utc_time(book.received_at)-utc_time(book.source_ts)) if book.source_ts else None
            if lag is not None:
                r['source_to_receipt'].append(lag)
                r['arrival_source_stale'] += int(lag > 2 or lag < 0)
            r['receipt_to_available'].append(seconds(utc_time(event['at'])-utc_time(book.received_at)))
            if book.source_ts:
                old = self.last_source.get(channel)
                if old is not None:
                    gap = seconds(utc_time(book.source_ts)-utc_time(old))
                    if gap > 0: r['source_gap'].append(gap)
                    elif gap == 0: r['unchanged_source'] += 1
                self.last_source[channel] = book.source_ts

    def report(self):
        strict = self.finish()
        if sum(self.bins.values()) != strict['planned_wall_seconds'] or self.bins['VALID'] != strict['valid_local_market_state_seconds']['us_ws']:
            raise ValueError('attribution failed to reconcile strict coverage')
        def quantiles(values):
            values = sorted(values)
            return dict(n=len(values),minimum=values[0] if values else None,
                median=values[(len(values)-1)//2] if values else None,
                p95=values[max(0,(len(values)*95+99)//100-1)] if values else None,
                maximum=values[-1] if values else None)
        return dict(strict=strict,exclusive_combinations_seconds=self.bins,
            overlapping_category_seconds=self.overlap,
            sole_category_seconds=self.sole,
            latency_seconds={c:{k:quantiles(v) if isinstance(v,list) else v for k,v in r.items()}
                             for c,r in self.latencies.items()},
            continuity='UNKNOWN even during diagnostic VALID intervals',
            metric='Sole-category removal is an offline arithmetic ceiling, not physical causation or eligibility.',
            trading_authorized=False)
