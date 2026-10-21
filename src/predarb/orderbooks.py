"""Exact, read-only binary book normalization. Data quality never authorizes trading."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

from . import kalshi, polymarket_us
from .models import AskLevel
from .validation import SchemaError, amount, decimal_value, field, identifier, text_field, utc_time

NORMALIZER_VERSION = 'binary-books/m3-v1'
ONE = Decimal('1')


def exact(value, *, positive=False, price=False, string=True):
    number = decimal_value(value, positive=positive, price=price, string=string)
    if number.adjusted() > 20 or number.as_tuple().exponent < -8 or len(number.as_tuple().digits) > 29:
        raise SchemaError('unsupported decimal precision/range; no rounding permitted')
    return number


@dataclass(frozen=True)
class PriceBand:
    start: Decimal
    end: Decimal
    step: Decimal


@dataclass(frozen=True)
class Book:
    venue: str
    source_id: str
    yes_asks: tuple[AskLevel, ...]
    no_asks: tuple[AskLevel, ...]
    price_bands: tuple[PriceBand, ...]
    quantity_step: Decimal | None
    minimum_quantity: Decimal | None
    received_at: str
    metadata_received_at: str
    source_ts: str | None
    timestamp_kind: str
    transport: str
    continuity: str
    mechanism_yes: str
    mechanism_no: str
    rejections: tuple[str, ...]
    market_close_at: str | None = None
    sequence: int | None = None

    def issues(self, *, now, max_age=60):
        if type(max_age) is not int or not 1 <= max_age <= 3600:
            raise ValueError('max_age must be an integer in 1..3600 seconds')
        if now.tzinfo is None:
            raise ValueError('now must have an explicit timezone')
        reasons = list(self.rejections)
        if self.market_close_at is not None and now >= utc_time(self.market_close_at):
            reasons.append('MARKET_CLOSED_AT_EVALUATION')
        for stamp, label in ((self.received_at, 'RECEIPT'), (self.metadata_received_at, 'METADATA'),
                             (self.source_ts, 'SOURCE')):
            if stamp is None:
                reasons.append('UNKNOWN_SOURCE_TIME')
                continue
            age = now - utc_time(stamp)
            if age > timedelta(seconds=max_age): reasons.append('STALE_' + label)
            if age < timedelta(seconds=-5): reasons.append('FUTURE_' + label)
        if self.source_ts is not None and utc_time(self.source_ts) > utc_time(self.received_at) + timedelta(seconds=5):
            reasons.append('SOURCE_AFTER_RECEIPT')
        if utc_time(self.metadata_received_at) > utc_time(self.received_at):
            reasons.append('METADATA_AFTER_BOOK')
        return tuple(dict.fromkeys(reasons))

    def as_dict(self, *, now, max_age=60):
        result = asdict(self)
        issues = self.issues(now=now, max_age=max_age)
        return result | {'normalizer_version': NORMALIZER_VERSION, 'rejections': issues,
                         'data_usable': not issues, 'verification': 'UNVERIFIED', 'trading_authorized': False}


def market_rules(venue, source_id, metadata, *, now):
    """Return the documented price grid and quantity granularity, without guessing absent fields."""
    identifier(source_id)
    if venue == 'kalshi':
        kalshi.validate_market(metadata)
        if metadata['ticker'] != source_id:
            raise SchemaError('market identity mismatch')
        if metadata['market_type'] != 'binary' or exact(metadata['notional_value_dollars']) != ONE:
            raise SchemaError('only binary $1 notional markets are supported')
        if metadata.get('settlement_bounds_type') != 'default':
            raise SchemaError('unsupported settlement bounds')
        if metadata['status'] != 'active':
            raise SchemaError('market is not active')
        if utc_time(metadata['open_time']) > now or utc_time(metadata['close_time']) <= now:
            raise SchemaError('market is outside its open/close window')
        bands = []
        for item in field(metadata, 'price_ranges', list):
            start = exact(text_field(item, 'start'), price=True)
            end = exact(text_field(item, 'end'), price=True)
            step = exact(text_field(item, 'step'), price=True, positive=True)
            if start >= end or (end - start) % step != 0:
                raise SchemaError('invalid price band extent/step')
            bands.append(PriceBand(start, end, step))
        if not bands or bands[0].start != 0 or bands[-1].end != 1:
            raise SchemaError('price ranges must cover [0,1]')
        if any(left.end != right.start for left, right in zip(bands, bands[1:])):
            raise SchemaError('overlapping or discontinuous price ranges')
        return tuple(bands), Decimal('0.01'), Decimal('0.01')
    if venue != 'polymarket_us':
        raise SchemaError('unsupported US venue')
    polymarket_us.validate_market(metadata)
    if metadata['slug'] != source_id:
        raise SchemaError('market identity mismatch')
    if not metadata['active'] or metadata['closed'] or metadata['status'] != 'MARKET_STATUS_OPEN':
        raise SchemaError('market is not open')
    if utc_time(metadata['endDate']) <= now:
        raise SchemaError('market deadline passed')
    sides = field(metadata, 'marketSides', list)
    if len(sides) != 2 or {field(side, 'long', bool) for side in sides} != {True, False}:
        raise SchemaError('expected explicit long and short instrument sides')
    for side in sides:
        if side['identifier'] != source_id or side['marketSideType'] != 'MARKET_SIDE_TYPE_INSTRUMENT':
            raise SchemaError('ambiguous instrument side mapping')
        if field(side, 'tradable', bool) is not True:
            raise SchemaError('instrument side is not tradable')
    if 'orderPriceMinTickSize' not in metadata or 'minimumTradeQty' not in metadata:
        raise SchemaError('tick and quantity metadata required')
    tick = exact(metadata['orderPriceMinTickSize'], positive=True, price=True, string=False)
    minimum = exact(metadata['minimumTradeQty'], positive=True, string=False)
    # Official US fractional-contract guide: supported market steps are 0.01 or 1.
    # Other minimums do not establish a known lot step; refuse rather than infer one.
    if minimum not in {Decimal('0.01'), ONE} or ONE % tick != 0:
        raise SchemaError('unsupported tick/lot specification')
    return (PriceBand(Decimal('0'), ONE, tick),), minimum, minimum


def _levels(raw, *, bands, step):
    result = []
    seen = set()
    for price, quantity in raw:
        p, q = exact(price, positive=True, price=True), exact(quantity, positive=True)
        if p >= 1 or p in seen:
            raise SchemaError('duplicate or invalid book price')
        if not any(band.start <= p <= band.end and (p - band.start) % band.step == 0 for band in bands):
            raise SchemaError('off-grid price')
        if q % step != 0:
            raise SchemaError('off-grid quantity')
        seen.add(p)
        result.append(AskLevel(p, q))
    return tuple(result)


def _build(venue, source_id, payload, metadata, *, received_at, metadata_received_at,
           source_ts, timestamp_kind, transport, continuity, now, sequence=None):
    """Callers must archive inputs first. Rejections retain no partially validated ladder."""
    yes = no = bands = ()
    step = minimum = None
    reasons = []
    mechanism_yes = 'BUY_YES_FROM_COMPLEMENTARY_NO_BID' if venue == 'kalshi' else 'BUY_LONG_FROM_OFFER'
    mechanism_no = 'BUY_NO_FROM_COMPLEMENTARY_YES_BID' if venue == 'kalshi' else 'SYNTHETIC_NO_FROM_SELL_YES_AT_BID'
    utc_time(received_at)
    utc_time(metadata_received_at)
    if source_ts is not None: utc_time(source_ts)
    with localcontext() as context:
        context.prec = 80
        try:
            bands, step, minimum = market_rules(venue, source_id, metadata, now=now)
            if venue == 'kalshi':
                kalshi.validate_book(payload)
                raw = payload['orderbook_fp']
                yes_bids = _levels(raw['yes_dollars'], bands=bands, step=step)
                no_bids = _levels(raw['no_dollars'], bands=bands, step=step)
                if yes_bids and no_bids and max(x.price for x in yes_bids) + max(x.price for x in no_bids) >= ONE:
                    raise SchemaError('crossed or locked complementary bids')
                yes = _levels([(str(ONE - x.price), str(x.quantity)) for x in no_bids], bands=bands, step=step)
                no = _levels([(str(ONE - x.price), str(x.quantity)) for x in yes_bids], bands=bands, step=step)
            elif venue == 'polymarket_us':
                polymarket_us.validate_book(payload)
                raw = payload['marketData']
                if raw['marketSlug'] != source_id or raw['state'] != 'MARKET_STATE_OPEN':
                    raise SchemaError('book identity/state mismatch')
                bids = _levels([(x['px']['value'], x['qty']) for x in raw['bids']], bands=bands, step=step)
                offers = _levels([(x['px']['value'], x['qty']) for x in raw['offers']], bands=bands, step=step)
                if bids and offers and max(x.price for x in bids) >= min(x.price for x in offers):
                    raise SchemaError('crossed or locked bid/offer book')
                yes = offers
                no = _levels([(str(ONE - x.price), str(x.quantity)) for x in bids], bands=bands, step=step)
            yes = tuple(sorted(yes, key=lambda level: level.price))
            no = tuple(sorted(no, key=lambda level: level.price))
            if not yes and not no: reasons.append('EMPTY_BOOK')
            elif not yes or not no: reasons.append('PARTIAL_BOOK')
            if continuity not in {'INDEPENDENT_FULL_SNAPSHOT', 'SEQUENCED'}:
                reasons.append('UNVERIFIED_CONTINUITY')
        except (ValueError, TypeError, KeyError) as exc:
            yes = no = ()
            reasons.append('INVALID_BOOK: ' + str(exc))
    return Book(venue, source_id, yes, no, bands, step, minimum, received_at, metadata_received_at,
                source_ts, timestamp_kind, transport, continuity, mechanism_yes, mechanism_no,
                tuple(reasons), market_close_at=metadata.get('close_time' if venue == 'kalshi' else 'endDate')
                if isinstance(metadata.get('close_time' if venue == 'kalshi' else 'endDate'), str) else None, sequence=sequence)


def normalize_rest(venue, source_id, payload, metadata, *, received_at, metadata_received_at, now):
    """Each REST response replaces the whole snapshot. No synthetic source timestamp or sequence."""
    if venue not in {'kalshi', 'polymarket_us'}:
        raise ValueError('unsupported US venue')
    source_ts = None
    if venue == 'polymarket_us':
        source_ts = text_field(field(payload, 'marketData', dict), 'transactTime')
    return _build(venue, source_id, payload, metadata, received_at=received_at,
                  metadata_received_at=metadata_received_at, source_ts=source_ts,
                  timestamp_kind='TRANSACTION_TIME' if source_ts else 'ABSENT', transport='REST_SNAPSHOT',
                  continuity='INDEPENDENT_FULL_SNAPSHOT', now=now)


@dataclass(frozen=True)
class Depth:
    requested: Decimal
    covered: Decimal
    quote_cost: Decimal
    complete: bool
    reason: str
    levels: tuple[AskLevel, ...]


def walk_depth(book, side, quantity, *, now, max_age=60):
    """Hypothetical depth coverage only: no fees, profit, fill or execution assertion."""
    issues = book.issues(now=now, max_age=max_age)
    if issues:
        raise ValueError('book rejected: ' + '; '.join(issues))
    if side not in {'YES', 'NO'}:
        raise ValueError('side must be YES or NO')
    with localcontext() as context:
        context.prec = 80
        quantity = exact(quantity, positive=True, string=False)
        if quantity < book.minimum_quantity or quantity % book.quantity_step:
            raise ValueError('requested depth is below minimum or off lot grid')
        remaining, cost = quantity, Decimal('0')
        used = []
        for level in book.yes_asks if side == 'YES' else book.no_asks:
            take = min(remaining, level.quantity)
            if take:
                used.append(AskLevel(level.price, take))
                cost += take * level.price
                remaining -= take
            if not remaining: break
        return Depth(quantity, quantity - remaining, cost, not remaining,
                     'COVERED' if not remaining else 'DEPTH_EXHAUSTED', tuple(used))
