"""Pure, pessimistic PAPER stress cases over later quote samples. No order transport."""
from dataclasses import asdict
from decimal import Decimal, ROUND_FLOOR, localcontext

from .economics import seconds
from . import mechanics
from .fees import fill_fees, quote_fee_bound
from .models import AskLevel
from .orderbooks import exact, walk_depth
from .validation import field, object_value, utc_time

VERSION = 'paper-stress/m5a-d-v1'


def policy(data):
    object_value(data)
    required = {'max_hedge_latency_ms', 'cancel_after_ms', 'cancel_ack_delay_ms', 'participation', 'max_price_drift'}
    if set(data) != required:
        raise ValueError('paper policy requires exactly: ' + ', '.join(sorted(required)))
    for key in ('max_hedge_latency_ms', 'cancel_after_ms', 'cancel_ack_delay_ms'):
        value = field(data, key, int)
        if not 0 <= value <= 60000 or (key != 'cancel_ack_delay_ms' and value == 0):
            raise ValueError('paper latency must be bounded in 0..60000 milliseconds')
    participation = exact(data['participation'], positive=True, price=True)
    drift = exact(data['max_price_drift'], price=True)
    return dict(data, participation=participation, max_price_drift=drift)


def simulate(initial, later, models, sides, quantity, review, config, *, created_at, now,
             reserve_per_leg, outages=(False, False)):
    """Each comparison is an independent hypothetical scenario, never cumulative fills.

    A late sample within an assumed cancel-ack window pessimistically permits fills.
    Samples after that window assume effective cancellation, explicitly unverified.
    """
    with localcontext() as context:
        context.prec = 80
        config = policy(config)
        quantity = exact(quantity, positive=True, string=False)
        reserve_per_leg = exact(reserve_per_leg, string=False)
        if len(initial) != 2 or len(later) != 2 or len(models) != 2 or len(sides) != 2:
            raise ValueError('exactly two paper legs required')
        explicit_mechanics = 'mechanics' in review or any(not book.source_id.startswith('HYPOTHETICAL-') for book in initial)
        if explicit_mechanics:
            mechanics.scenario_terms(field(review, 'settlement_scenarios', list), now=now)
        if len(outages) != 2 or any(type(value) is not bool for value in outages):
            raise ValueError('two explicit outage booleans required')
        created = utc_time(created_at)
        if now < created:
            raise ValueError('paper comparison precedes intent')
        request_ms = min(config['cancel_after_ms'], config['max_hedge_latency_ms'])
        ack_ms = request_ms + config['cancel_ack_delay_ms']
        legs, flags = [], []
        for index, (old, book, model, side) in enumerate(zip(initial, later, models, sides)):
            if (book.venue, book.source_id) != (old.venue, old.source_id):
                raise ValueError('PAPER_BOOK_IDENTITY_MISMATCH')
            if book.issues(now=now):
                raise ValueError('PAPER_BOOK_REJECTED: ' + ';'.join(book.issues(now=now)))
            mechanics.check_book(old, side)
            mechanics.check_book(book, side)
            if book.source_ts is None or old.source_ts is None:
                raise ValueError('known source times required')
            if utc_time(book.source_ts) > now:
                raise ValueError('future source time cannot establish a causal paper comparison')
            if utc_time(book.received_at) <= utc_time(old.received_at) or utc_time(book.source_ts) <= utc_time(old.source_ts):
                raise ValueError('LATER_QUOTES_REQUIRED')
            arrival = seconds(utc_time(book.received_at) - created) * 1000
            if arrival <= 0 or utc_time(book.received_at) > now:
                raise ValueError('paper sample is not causal at evaluation')
            model.check(venue=book.venue, source_id=book.source_id, side=side, now=now)
            # Old quotes are a historical reference, not represented as fresh at the later clock.
            depth = walk_depth(old, side, quantity, now=created)
            if not depth.complete:
                raise ValueError('initial paper quantity lacks depth')
            threshold = depth.levels[-1].price + config['max_price_drift']
            asks = book.yes_asks if side == 'YES' else book.no_asks
            initial_asks = old.yes_asks if side == 'YES' else old.no_asks
            change = asks[0].price - initial_asks[0].price
            filled, used, cost = Decimal('0'), [], Decimal('0')
            reason = 'ASSUMED_VISIBLE_DEPTH_PARTICIPATION'
            if outages[index]:
                reason = 'HYPOTHETICAL_API_OUTAGE'
            elif arrival > ack_ms:
                reason = 'CANCEL_ACK_ASSUMED_BEFORE_SAMPLE'
            else:
                if arrival > request_ms:
                    flags.append('POSSIBLE_FILL_DURING_CANCEL_ACK_WINDOW')
                for level in asks:
                    if level.price > threshold:
                        break
                    available = (level.quantity * config['participation'] / book.quantity_step).to_integral_value(rounding=ROUND_FLOOR) * book.quantity_step
                    take = min(quantity - filled, available)
                    if take:
                        used.append(AskLevel(level.price, take));filled += take;cost += take * level.price
                    if filled == quantity:
                        break
                if not filled:
                    reason = 'PRICE_CAP_OR_PARTICIPATION_PREVENTS_FILL'
            if filled < quantity:
                flags.append('PARTIAL_OR_NO_FILL')
            legs.append({'venue': book.venue, 'side': side, 'arrival_ms': arrival, 'filled': filled,
                         'unfilled': quantity - filled, 'quote_cost': cost, 'price_change': change,
                         'price_cap_threshold': threshold, 'levels': [asdict(row) for row in used],
                         'fee_bound_including_settlement': quote_fee_bound(model, used, book.quantity_step),
                         'declared_partition_fee': fill_fees(model, used)['total'], 'reason': reason})
        payouts = []
        for row in review['settlement_scenarios']:
            values = [exact(row[venue + '_payout'], price=True) for venue in ('kalshi', 'polymarket_us')]
            if sum(values) != 1:
                raise ValueError('review does not establish complementary payouts')
            payouts.append(sum(leg['filled'] * value for leg, value in zip(legs, values)))
        if not payouts:
            raise ValueError('settlement scenarios required')
        cashflows = None
        if explicit_mechanics:
            cashflows = mechanics.payout_cashflows(review['settlement_scenarios'], [leg['filled'] for leg in legs])
            payouts = [row['total_payout'] for row in cashflows]
        unhedged = abs(legs[0]['filled'] - legs[1]['filled'])
        if unhedged:
            flags.append('UNHEDGED_PAPER_EXPOSURE')
        hedge_latency = abs(legs[0]['arrival_ms'] - legs[1]['arrival_ms']) if all(leg['filled'] for leg in legs) else None
        if hedge_latency is not None and hedge_latency > config['max_hedge_latency_ms']:
            flags.append('MAX_HEDGE_LATENCY_EXCEEDED')
        reserve = reserve_per_leg * sum(leg['filled'] for leg in legs)
        funding = [mechanics.capital(book, side, leg['quote_cost'], leg['fee_bound_including_settlement'],
                                     reserve_per_leg * leg['filled'])
                   for book, side, leg in zip(later, sides, legs)]
        capital = sum(leg['research_cash_required'] for leg in funding)
        return {'version': VERSION, 'status': 'STRESS_MODELED', 'legs': legs, 'unhedged_contracts': unhedged,
                'mechanics_version': mechanics.VERSION, 'funding': funding, 'settlement_cashflows': cashflows,
                'hedge_latency_ms': hedge_latency, 'cancel_request_ms': request_ms, 'cancel_ack_assumed_ms': ack_ms,
                'reserve': reserve, 'capital_bound': capital, 'worst_reviewed_payout': min(payouts),
                'worst_net_bound': min(payouts) - capital, 'best_net_bound': max(payouts) - capital,
                'downside_bound': max(Decimal('0'), capital - min(payouts)), 'flags': sorted(set(flags)),
                'assumptions': ['HYPOTHETICAL_FILLS_FROM_LATER_QUOTES', 'INDEPENDENT_COMPARISON_NOT_A_POSITION',
                                'PARTICIPATION_AND_CANCEL_ACK_ARE_ASSUMED', 'NO_UNOBSERVED_PRIOR_FILLS_ASSUMED',
                                'NO_RESCUE_TRADE_OR_REBALANCING'],
                'unobserved_pre_sample_fills_possible': True, 'empirical_fill_probability_estimated': False,
                'severity': 'HIGH' if unhedged or 'MAX_HEDGE_LATENCY_EXCEEDED' in flags else 'INFO',
                'verification': 'UNVERIFIED', 'trading_authorized': False}
