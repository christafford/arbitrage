# M5Q — current US stream continuity review

Official sources were freshly archived on November 8, 2026, at 06:17 UTC before
interpretation. [Exact URLs, bytes hashes and receipts](evidence/M5Q_API_CHECKS.json)
bind the local sources under `data/m5q/run-20261108/sources/`. MarketService remains
1.0.0; stream prose has no immutable semantic version. The existing consumed fields
and adapter contracts are unchanged. Kalshi Get Market remains 3.36.0.

| Question | Current documented evidence | Research conclusion |
| --- | --- | --- |
| Snapshot shape | [Markets WebSocket](https://docs.polymarket.us/api-reference/websocket/markets) describes full displayed order-book snapshots, bid/offer levels and `transactTime`; displayed top levels are not all exchange liquidity | Apply each accepted full snapshot using existing metadata/grid validation; no invented deltas |
| Sequence | [Overview](https://docs.polymarket.us/api-reference/websocket/overview) advises ordered processing and describes sequential delivery; the consumed market frame has no documented contiguous counter, replay cursor or checksum | Gap detection remains UNKNOWN; ordered transport alone does not establish completeness |
| Liveness | Overview describes heartbeat messages and reconnecting when they stop | Heartbeat/pong activity describes transport, not the freshness of a specific book |
| Recovery | Overview recommends reconnection with exponential backoff | No documented market-state resume watermark or recoverable sequence position is available in this contract; reconnect starts a new generation and waits for a snapshot |
| Quiet resting book | No checked source says a heartbeat renews `transactTime`, certifies no missed changes, or supplies a per-market no-change watermark | Unchanged resting depth cannot be treated as continuously validated under this consumed protocol |
| Time semantics | [Book schema](https://docs.polymarket.us/api-reference/markets/get-market-book) supplies transaction time; no send-time watermark is defined | Preserve source, receive and local availability clocks separately |

The overview's snake_case/numeric subscription example and the Markets page's
camelCase/string-enum example remain different. The existing authenticated probe
uses the latter, previously accepted live. This review does not invent a second
schema or change signing/subscription behavior.

Existing M5P instrumentation already separates verified snapshot availability,
local observed depth mutation, authenticated activity, continuity loss, source
time and receipt time. It records generation boundaries, raw frames and replayable
local-state intervals. Additional liveness instrumentation would not close the
missing provider guarantee, so M5Q does not introduce an alternative freshness
policy. Every historical and new strict two-second result retains its meaning.

Passing local-state coverage means that archived local state passed the existing
checks during the integrated interval. It is not a finding of continuous exchange
validity, executable fills, settlement equivalence or economic eligibility.

The [collateral source](https://docs.polymarket.us/market-structure/collateral-and-margin)
distinguishes a long purchase debit from a short's full-payout collateral and net
buying-power effect. The existing unsupported synthetic-NO direction remains
blocked. [Settlement documentation](https://docs.polymarket.us/learn/markets/contract-settlement)
describes finalization before settlement and market-specific alternatives; it does
not establish an instrument-specific cash-release deadline. No current fee prose
or metadata coefficient is an independently reviewed historical fee profile.
