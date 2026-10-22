"""Transport-independent Kalshi orderbook validation and deterministic replay.

One market per subscription is required: Kalshi seq is scoped to the subscription,
not the market. clock may repeat across deltas and is not a contiguous sequence.
"""
from datetime import datetime, timezone
from copy import deepcopy
from decimal import Decimal, localcontext

from . import kalshi
from .orderbooks import _build, _levels, exact, market_rules
from .validation import SchemaError, field, identifier, text_field


class KalshiBookStream:
    def __init__(self, source_id, metadata, *, metadata_received_at):
        self.source_id = identifier(source_id)
        self.metadata, self.metadata_received_at = deepcopy(metadata), metadata_received_at
        self.generation = 0
        self.reconnect()

    def reconnect(self):
        self.generation += 1
        self.sid = self.seq = self.clock = self.snapshot_clock = self.market_id = None
        self.last_send_ms = self.high_seq = None
        self.connected = True
        self.yes, self.no = {}, {}
        self.state, self.reason = 'NEEDS_SNAPSHOT', 'NEW_CONNECTION'
        self.current = None

    def replace_metadata(self, metadata, *, received_at):
        self.metadata, self.metadata_received_at = deepcopy(metadata), received_at
        self.reconnect()  # A changed tick/lot/state context requires a fresh snapshot.

    def disconnect(self):
        self.connected = False
        self._invalidate('DISCONNECTED')

    def _invalidate(self, reason):
        self.state, self.reason, self.current = 'NEEDS_SNAPSHOT', reason, None
        self.yes, self.no = {}, {}

    def apply(self, frame, *, received_at, now, generation):
        """Replay a previously archived frame. Any error discards derived depth."""
        try:
            if not self.connected or generation != self.generation:
                raise SchemaError('reconnect required or wrong connection generation')
            message_type = text_field(frame, 'type')
            if message_type not in {'orderbook_snapshot', 'orderbook_delta'}:
                raise SchemaError('unsupported message type')
            sid, seq = field(frame, 'sid', int), field(frame, 'seq', int)
            sent = field(frame, 'sending_ts_ms', int)
            if sid < 1 or seq < 0 or not 0 <= sent <= 253402300799999:
                raise SchemaError('invalid sid/seq/sending timestamp')
            if self.sid is not None and sid != self.sid:
                raise SchemaError('subscription changed without reconnect')
            prior_high_seq = self.high_seq
            self.high_seq = max(seq, self.high_seq if self.high_seq is not None else seq)
            message = field(frame, 'msg', dict)
            if text_field(message, 'market_ticker') != self.source_id:
                raise SchemaError('wrong market; only a single-market subscription is supported')
            market_id = text_field(message, 'market_id')
            clock = field(message, 'clock', int)
            if clock < 0 or (self.clock is not None and clock < self.clock):
                raise SchemaError('clock regressed; reconnect and request a fresh snapshot')
            if self.market_id is not None and market_id != self.market_id:
                raise SchemaError('market identity changed')
            if self.last_send_ms is not None and sent < self.last_send_ms:
                raise SchemaError('sending timestamp regressed')
            self.clock, self.last_send_ms = clock, sent  # Retain observed frontiers even if depth is invalid.
            if message_type == 'orderbook_delta' and self.state != 'SYNCED':
                raise SchemaError('fresh snapshot required before any delta')
            if self.state == 'SYNCED' and seq != self.seq + 1:
                raise SchemaError('sequence gap, duplicate or out-of-order message')
            if self.state != 'SYNCED' and prior_high_seq is not None and seq <= prior_high_seq:
                raise SchemaError('recovery snapshot sequence must advance beyond every observed frame')
            with localcontext() as context:
                context.prec = 80
                bands, step, _ = market_rules('kalshi', self.source_id, self.metadata, now=now)
                if message_type == 'orderbook_snapshot':
                    raw = {'orderbook_fp': {'yes_dollars': field(message, 'yes_dollars_fp', list),
                                            'no_dollars': field(message, 'no_dollars_fp', list)}}
                    kalshi.validate_book(raw)
                    yes = _levels(raw['orderbook_fp']['yes_dollars'], bands=bands, step=step)
                    no = _levels(raw['orderbook_fp']['no_dollars'], bands=bands, step=step)
                    self.yes = {level.price: level.quantity for level in yes}
                    self.no = {level.price: level.quantity for level in no}
                    self.snapshot_clock = clock
                else:
                    if clock <= self.snapshot_clock:
                        raise SchemaError('delta overlaps the snapshot clock')
                    side = text_field(message, 'side')
                    if side not in {'yes', 'no'}:
                        raise SchemaError('unknown delta side')
                    # Signed delta is documented; counts must remain nonnegative and on the .01 grid.
                    raw_delta = text_field(message, 'delta_fp')
                    magnitude = exact(raw_delta[1:] if raw_delta.startswith('-') else raw_delta)
                    delta = -magnitude if raw_delta.startswith('-') else magnitude
                    if delta % step:
                        raise SchemaError('off-grid quantity delta')
                    price = exact(text_field(message, 'price_dollars'), positive=True, price=True)
                    _levels([(str(price), str(step))], bands=bands, step=step)
                    levels = self.yes if side == 'yes' else self.no
                    updated = levels.get(price, Decimal('0')) + delta
                    if updated < 0:
                        raise SchemaError('negative reconstructed liquidity')
                    if updated == 0: levels.pop(price, None)
                    else: levels[price] = updated
                payload = {'orderbook_fp': {
                    'yes_dollars': [[str(p), str(q)] for p, q in self.yes.items()],
                    'no_dollars': [[str(p), str(q)] for p, q in self.no.items()]}}
                # Integer arithmetic preserves provider millisecond time exactly.
                source_ts = datetime.fromtimestamp(sent // 1000, timezone.utc).replace(
                    microsecond=(sent % 1000) * 1000).isoformat()
                book = _build('kalshi', self.source_id, payload, self.metadata, received_at=received_at,
                              metadata_received_at=self.metadata_received_at, source_ts=source_ts,
                              timestamp_kind='PROVIDER_SEND_TIME', transport='OFFLINE_WS_REPLAY',
                              continuity='SEQUENCED', now=now, sequence=seq)
                if any(reason.startswith('INVALID_BOOK') for reason in book.rejections):
                    raise SchemaError('; '.join(book.rejections))
            self.sid, self.seq, self.clock, self.market_id = sid, seq, clock, market_id
            self.last_send_ms, self.high_seq = sent, seq
            self.state, self.reason, self.current = 'SYNCED', None, book
            return book
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self._invalidate(str(exc))
            raise ValueError('stream invalidated: ' + str(exc)) from exc
