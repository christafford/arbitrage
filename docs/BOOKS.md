# Read-only book inspection (M3)

Collectors now archive each selected book and its preceding market detail before
normalizing depth. `predarb books` inspects that evidence locally; it makes no
network requests. All collected evidence remains `UNVERIFIED`, and every result
sets `trading_authorized=false`. `data_usable` means quote-quality checks passed
at the evaluation time. It does not establish equivalent settlement, a fill,
profit, collateral requirements or permission to trade.

## Inspect an archive

```bash
predarb books list --db data/research.sqlite3
predarb books inspect 12 --db data/research.sqlite3
predarb books inspect 12 --db data/research.sqlite3 --side YES --quantity 1
predarb books --help
```

Replace `12` with an observation ID returned by `books list`. The optional side
and exact decimal quantity must be supplied together. Depth coverage walks sorted
levels once, reporting requested/covered quantity, consumed levels and quote cost.
Insufficient depth returns `complete=false` and `DEPTH_EXHAUSTED`, with the actual
covered quantity; it never extrapolates missing liquidity. These are explicitly
hypothetical calculations. Fees, profit and execution are outside M3.

`list` exits 0 for a descriptive list, including rejected books. `inspect` and
`pair` exit 2 for a requested book/comparison rejected by quality checks. Bad
arguments, missing observations, invalid provenance or rejected depth requests
exit 1. Successful inspection exits 0; a covered quote is not a trading signal.

By default each command evaluates the book at the current UTC time. A saved
assessment describes capture-time quality only; inspection recomputes validity
from raw bytes and current context. For deterministic historical replay:

```bash
predarb books inspect 12 --db data/m3-live-smoke.sqlite3 \
  --at 2026-10-21T21:23:29.028171+00:00 --side YES --quantity 1
```

That particular ID/time belongs to the local M3 smoke archive. The response says
`historical_replay=true`; it is not a current quote. The same observation is
stale when inspected later without `--at`.

## Side semantics and supported grids

| Venue | YES ask representation | NO ask representation |
| --- | --- | --- |
| Kalshi binary $1 contracts | `1 - NO bid`, same quantity | `1 - YES bid`, same quantity |
| Polymarket US instrument | YES offer, same quantity | `1 - YES bid`, same quantity, explicitly synthetic short-YES exposure |

Polymarket US NO levels carry
`SYNTHETIC_NO_FROM_SELL_YES_AT_BID`. They do not identify a separate purchasable
NO token. This is a quote/payoff representation; order routing, short-position
mechanics, collateral and account permissions are not implemented. Only explicit
long/short, tradable instrument sides matching the exact market slug are accepted.

Prices and quantities use `Decimal` without rounding. Kalshi uses the market's
contiguous `price_ranges` covering [0,1], rather than inferring ticks from the
structure label, and its documented 0.01 count granularity. Only active binary
markets with $1 notional and default settlement bounds are supported. Polymarket
US uses `orderPriceMinTickSize`; supported `minimumTradeQty` values are 0.01 and 1,
with a conservative quantity lattice of that size. The minimum field alone is
not a universal lot-step specification. Other minima are rejected until their
increments are documented. Off-grid quantities and prices, unknown fields
required for interpretation, unsupported states/currencies, nonfinite values,
duplicate prices and ambiguous identities fail closed. Exact inputs support up
to eight decimal places within bounded magnitude; no float conversion is used.

Both ladders are required. Empty/one-sided snapshots, crossed or locked books
are rejected. Malformed ladders expose no partially validated depth. Structurally
valid but stale or one-sided depth may remain visible for diagnosis, with rejection
flags that prevent depth calculations.

## Time, continuity and comparison gates

Receipt time, metadata receipt time and provider book time are separate. The
default maximum age is 60 seconds; `--max-age` accepts integers 1..3600. Each use
rechecks all three clocks, known market close time, source-after-receipt anomalies
and timestamps more than five seconds into the future. Newer metadata requires
a fresh book; newer captured depth supersedes older depth. Only final COMPLETE
or PARTIAL collection runs can supply inspected books. PARTIAL catalogue coverage
does not by itself invalidate a complete selected-market snapshot.

Kalshi REST supplies no source book timestamp. Its diagnostic normalized levels
always carry `UNKNOWN_SOURCE_TIME` and cannot pass the freshness/depth/comparison
gate. HTTP Date, receipt time and metadata update time are never substituted.
Polymarket US uses `marketData.transactTime`. Every full REST response replaces
the snapshot; neither adapter invents REST sequence numbers or delta continuity.

`KalshiBookStream` is an **offline replay helper**, not a live connection. It
supports one market per subscription, checks subscription-scoped contiguous
`seq`, market identity, connection generation, nonregressing send time and market
`clock`. Clock values may repeat or skip across deltas; they are not sequence
numbers. Deltas must follow the snapshot clock. Gaps, duplicates, out-of-order
frames, negative reconstructed quantities and malformed data discard current
depth. Recovery needs a full snapshot beyond every observed sequence, or a new
connection generation and snapshot. Metadata replacement also clears depth.
Provider `sending_ts_ms` is labeled `PROVIDER_SEND_TIME`, not mutation time.

The documented Kalshi and US WebSocket connections require authentication; none
was connected or tested live. US documentation does not establish a sequence/delta
protocol for its market-data snapshots, so this implementation does not assume
one. Tests and the offline demo exercise Kalshi recovery using visibly hypothetical
frames archived before parsing. Authenticated transport and live continuity
validation remain future, separately scoped work.

For a separately human-approved registry pair:

```bash
predarb books pair PAIR_ID --db data/research.sqlite3 \
  --kalshi-observation KALSHI_ID --us-observation US_ID
```

Use actual integer IDs. This rechecks registry approval/expiry/evidence, exact
venue/market identity, both books and source/receipt clock skew. The default skew
limit is 2000 milliseconds; `--max-skew-ms` accepts 0..60000. Hypothetical pair
approvals cannot qualify live HTTP captures. A live Kalshi REST capture cannot
pass because source time is unknown. No real pair was approved for M3.

## Storage and replay

SQLite schema 3 adds `normalized_books` with exact raw book/detail references,
normalizer version `binary-books/m3-v1`, evaluation time, age limit and serialized
assessment. Raw SHA-256, validation status, schema, exact full-book/detail endpoint,
market identity and same-run detail-before-book provenance are verified on read.
Truncated/depth-limited or mismatched snapshots are refused. Back up an archive
before migration. M1/M2 raw data and registry decisions are preserved; old books
can be replayed from suitable detail provenance, but no historical assessment is
fabricated during migration.

To demonstrate conversion, exact depth coverage, staleness and stream recovery
without network access, choose a new empty output directory:

```bash
.venv/bin/python scripts/m3_demo.py --output data/my-m3-demo
```

The demo labels all inputs hypothetical, copies source bytes before parsing and
archives each replay frame with its hash. See [M3 results](M3_RESULTS.md) for the
executed tests, live capture results and remaining operational limits, and
[official sources](API_SOURCES.md) for the documented venue semantics.
