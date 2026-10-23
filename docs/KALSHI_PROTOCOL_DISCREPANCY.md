# Workstream B: production market-clock discrepancy

**Workstream B live acceptance remains blocked.** Authentication, subscription
and real market-data reception work. Production snapshots and deltas lack the
market clock required by the current official schema and by this project's
continuity validator. No missing clock is replaced with a sequence number,
receipt time, send time or zero. No real book was promoted to usable evidence.

## Official contract checked

On 2026-10-23 at 03:17 UTC, retrieved the official
[AsyncAPI](https://docs.kalshi.com/asyncapi.yaml),
[orderbook reference](https://docs.kalshi.com/websockets/orderbook-updates),
[connection reference](https://docs.kalshi.com/websockets/websocket-connection)
and [quickstart](https://docs.kalshi.com/getting_started/quick_start_websockets).
[Hashes and retrieval times](evidence/M5B_API_CHECKS.json) preserve this check;
original source files are retained under `data/m5b-protocol-check/`.

The published API version is 2.0.0. Both snapshot and delta payloads require
`msg.clock`. The documentation distinguishes this exchange clock from subscription
`seq` and says the snapshot covers changes through its clock. No subscription
parameter in this schema enables clock emission. The supported `get_snapshot`
command was tested rather than assuming that an explicit snapshot would differ.

The schema also announces a future change to the default for `use_yes_price`.
The adapter now sends `use_yes_price=false` explicitly, preserving its supported
NO-leg price convention. That setting was accepted during the live diagnostic;
it did not produce clock fields.

## Actual production diagnostic

Used existing protected RSA credentials with the fixed production endpoint
`wss://external-api-ws.kalshi.com/trade-api/ws/v2`. There were two bounded
12-second receive windows, one per market, with at most 150 frames each. The
script sent only a single-market subscription and one documented snapshot
request per connection. No order/account commands or support messages were sent.

| Market | Snapshots | Deltas | Frames with market clock |
| --- | ---: | ---: | ---: |
| `KXBTCD-26OCT2317-T83499.99` | 2 | 26 | 0 |
| `KXFEDCUT-31DEC28-31DEC26` | 2 | 0 | 0 |

Each connection also returned an acknowledgment. In each case the second snapshot
responded to command ID 2, the explicit `get_snapshot` request. Every book message
was missing `msg.clock`; source send timestamps were present. This reproduces the
discrepancy across initial snapshots, requested snapshots and incremental updates.
The absence of deltas in the brief second-market window is not evidence of a feed
failure. Reconnect transport worked; valid reconstructed-book continuity did not.

All diagnostic frames were archived before inspection and marked
`DIAGNOSTIC_ONLY_UNVALIDATED_PROTOCOL`; none entered normalization/economics.
The archive is `data/m5b-diagnostic-20261023T033342Z/capture.sqlite3`.
[Diagnostic evidence](evidence/M5B_PROTOCOL_DIAGNOSTIC.json) records commands,
receipt times, frame IDs, types, source-time/clock presence and connection outcomes.
The [representative fixture](../tests/fixtures/kalshi-ws-missing-clock-live.json)
preserves four exact public-shaped frames with verified hashes and their market
metadata. Authentication headers, signatures, credential contents and account
identifiers are excluded. This evidence stays local under venue data-use limits.

## Implementation and verification

The adapter now emits fixed, credential-safe protocol failure codes:
`MISSING_MARKET_CLOCK`, `INVALID_MARKET_CLOCK`, `MISSING_SOURCE_TIMESTAMP` and
`INVALID_SOURCE_TIMESTAMP`. Rejected observation and connection records preserve
the same code; CLI output identifies the blocker directly. Market clocks must
fit the documented int64 range. Validation still discards derived depth, rejects
unknown/malformed input and requires a valid snapshot before applying deltas.
No schema migration or historical acceptance change was made.

Executed baseline full discovery: **219 tests passed**. After changes, executed:

```bash
.venv/bin/python -m unittest discover -s tests -p '*stream*.py' -v
.venv/bin/python -m unittest discover -s tests -p test_kalshi_ws.py -v
.venv/bin/python -m unittest discover -s tests -v
```

The intermediate targeted runs passed 14 stream tests and 25 capture/authentication
tests. The final full run passed **224 tests**, including the subsequently added
actual-fixture replay tests. [Full test output](evidence/M5B_TESTS.txt) names every
test. New tests cover safe failure codes, missing/invalid clock and time fields,
clock loss after a valid snapshot, rejection barriers and fresh-generation recovery,
explicit subscription pricing, actual-frame hashes/privacy and repeated rejection
of the real missing-clock messages. Existing stale/invalid-price/partial-liquidity,
disconnect, gap, provenance, migration and research integration tests also ran.

[Seven CLI smoke checks](evidence/M5B_SMOKE.json) record exact commands and results:
the changed production capture exited **2 as expected**, with two
`MISSING_MARKET_CLOCK` failures, four messages and zero usable books. Help, book
listing, schema-7 backup, full backup verification and hypothetical demo/report
all exited 0. No tests or live captures established accepted book continuity.

## Remaining acceptance requirement

The venue needs to clarify why its published required field is absent from these
production messages, or provide a documented supported protocol/endpoint that
the adapter can validate. This report is prepared locally; no support message
was sent. A question for venue support is:

> On the production orderbook WebSocket, why is `msg.clock` absent from both
> snapshots and deltas despite being required in the current AsyncAPI schema?
> Does emitting it require a documented configuration or rollout, or is there
> an officially supported alternate continuity contract?

After that discrepancy is resolved, capture accepted timestamped snapshots and
sequential deltas, then demonstrate valid recovery after an actual reconnect and
repeat deterministic replay. Until those checks pass, Workstream B stays open.
Human equivalence review, fees, coordinated US polling, C–E, sustained M4/M5 runs
and M6 remain outside this change. Credentials and service settings were not changed.
