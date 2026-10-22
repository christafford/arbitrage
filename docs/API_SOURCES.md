# Official API sources and versioned contracts

Verified directly on **2026-10-21 UTC**, with public response retrievals at
19:51–19:58 UTC. Each JSON fixture records its own URL, retrieval timestamp,
upstream schema version, sanitizer description, and SHA-256 of the unchanged body.
See [M1 results](M1_RESULTS.md) and [fixture notes](../tests/fixtures/README.md).

## Kalshi

Production origin: `https://external-api.kalshi.com/trade-api/v2`.
Official embedded OpenAPI version: **3.34.0**; local validation contract:
`kalshi-3.34.0/m1-v1`.

| Official source | Fields/behavior used |
| --- | --- |
| [Public market data](https://docs.kalshi.com/getting_started/quick_start_market_data) | Public, credential-free market data |
| [Get markets](https://docs.kalshi.com/api-reference/market/get-markets) | `/markets`, `status=open`, `mve_filter=exclude`, `limit`, opaque `cursor`; stop at empty cursor |
| [Market details](https://docs.kalshi.com/api-reference/market/get-market) | `/markets/{ticker}`; IDs, fixed-point dollar/count strings, rules, metadata update time and deadlines |
| [Event details](https://docs.kalshi.com/api-reference/events/get-event) | `/events/{event_ticker}`; series identity and settlement sources |
| [Series details](https://docs.kalshi.com/api-reference/market/get-series) | `/series/{series_ticker}`; contract and contract-term URLs, prohibitions |
| [Book schema](https://docs.kalshi.com/api-reference/market/get-market-orderbook) | `/markets/{ticker}/orderbook`; `orderbook_fp.yes_dollars` and `no_dollars` contain `[price,quantity]` strings |
| [Rate limits](https://docs.kalshi.com/getting_started/rate_limits) | Token budgets vary by tier; use exponential backoff on 429 |

The book contains YES/NO **bids**, without an exchange book timestamp in the
verified REST schema. M1 captures both ladders without complement conversion.
Market `updated_time` is a metadata timestamp, not a book timestamp. No fallback
to legacy integer-cent `orderbook` data is permitted by this adapter contract.

## Polymarket US

Production public origin: **`https://gateway.polymarket.us`**.
Official MarketService OpenAPI version: **1.0.0**; local validation contract:
`polymarket-us-marketservice-1.0.0/m1-v1`. The upstream version is not an immutable
schema pin: local validation and captured bytes provide the actual contract evidence.

| Official source | Fields/behavior used |
| --- | --- |
| [Quickstart](https://docs.polymarket.us/getting-started/quickstart) | Public market data requires no credentials |
| [Get markets](https://docs.polymarket.us/api-reference/markets/get-markets) | `/v1/markets`, `limit`, `offset`, `active`, `closed`, `slug`, `orderBy=id`, `orderDirection=asc`; response has `markets`, no total or cursor |
| [Market details](https://docs.polymarket.us/api-reference/markets/get-market-by-slug) | `/v1/market/slug/{slug}` (**singular** `market`); description, IDs, sides, instrument identifiers, update time, end date, asset terms |
| [Book schema](https://docs.polymarket.us/api-reference/markets/get-market-book) | `/v1/markets/{slug}/book`; `marketData`, `bids`, `offers`, `px.value`, USD currency, `qty`, state and `transactTime` |
| [Market structure](https://docs.polymarket.us/concepts/events-and-markets) | Slugs identify markets for book queries; asset-specific terms are separate metadata |
| [Rule structure](https://docs.polymarket.us/learn/advanced/rule-structure) | Resolution conditions can include alternative settlement; descriptions alone never establish cross-venue equivalence |
| [Rate limits](https://docs.polymarket.us/api-reference/rate-limits) | Retail general limit 25 requests/s per source IP/location; back off on 429 |

Stop offset traversal only on an empty page; advance by the actual returned count.
A short nonempty page does not prove exhaustion, because servers may cap page sizes.
A live scoped traversal returned counts `[1,0]`. An unscoped two-page sample returned
`[2,2]` with distinct IDs. Sorting reduces movement but does not make offset paging
an atomic snapshot. Duplicates are counted, repeated/no-progress pages fail, and a
page budget yields `PARTIAL`, never `COMPLETE`. Completeness refers to terminal
pagination for the requested filter, not a venue-wide point-in-time census.

The older [data guide](https://docs.polymarket.us/data-guide/overview) describes
institutional `/v1/refdata/instruments`, `/symbols`, `/metadata` and `/v1/orderbook`.
Its [production environment](https://docs.polymarket.us/trader-guide/environments)
is `api.prod.polymarketexchange.com`. An unauthenticated instruments request returned
**HTTP 401**. M1 therefore uses the officially documented public gateway for the
same US venue: instrument identities and metadata come from market records and
`marketSides`. It does not implement the authenticated institutional interface.
The starter's `api.polymarket.us/v1/refdata/instruments` assumption was removed.
No `polymarket.com`, Gamma, or international CLOB endpoint is used.

## Terms and data rights checked

- [Kalshi Developer Agreement v1.1](https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf),
  sections 3–5: API use/storage is restricted to facilitating the member's own
  trading; sharing requires prior written authorization. The agreement also
  specifies membership, responsible API use and bounded retries.
- [Polymarket US terms entry point](https://polymarket.us/tos) linked on the official
  documentation. Its currently linked document displays an **October 22, 2026**
  effective date, one day after this verification. Sections 4–7 restrict use and
  data redistribution/bulk downloads; automation must use authorized APIs. Record
  the displayed date rather than assuming the published future-dated text settles
  the operator's currently applicable agreement.

These are recorded source restrictions, not a license grant or an eligibility
finding. Captures are for this operator's local research. Provider material is
not covered by this project's MIT code license. No data was pushed, published,
or redistributed in this milestone. Broader data use requires the applicable
venue permission; the published Polymarket terms date needs rechecking before
ongoing collection. Collection is an explicit bounded CLI action, not a daemon.

## M2 verification — 2026-10-21

Rechecked the official market/detail and US rule-structure sources above for the
registry. It reuses M1's verified metadata, rules and side identities without any
new API endpoint. Collected Kalshi event/series evidence and official contract URLs
are fingerprinted separately. Market terms, deadlines, outcome identities and
uninterpreted additional metadata participate in version changes; quote/volume
updates do not establish or approve equivalence. Polymarket asset-specific terms
remain uninterpreted evidence, not automatically matched conditions.

Full legal sources/clarifications are operator-imported from official US URLs;
the original bytes and exact UTF-8 resolution text are archived with separate
hashes and declared retrieval time. This does not independently authenticate the
source file or confer data rights. A human must verify source fidelity and all
settlement cases; see [pair review](PAIR_REVIEW.md). No live equivalence decision
was made during implementation or validation.

## M3 verification — 2026-10-21

Official documents were fetched again before M3 implementation. The
[manifest](evidence/M3_API_CHECKS.json) records canonical URLs, downloaded document
hashes and local save timestamps around 21:12 UTC. New unchanged book/detail
responses were captured at 21:23 UTC; see the
[M3 fixture](../tests/fixtures/m3-live-snapshots.json) for per-response timestamps,
hashes and schemas. Upstream versions remain Kalshi **3.34.0** and US public
MarketService **1.0.0**; normalization contract: `binary-books/m3-v1`.

| Official source | M3 interpretation |
| --- | --- |
| [Kalshi fixed-point migration](https://docs.kalshi.com/getting_started/fixed_point_migration) | Use fixed-point strings; count precision is 0.01. Market `price_ranges`, not a guessed label mapping, establish price grids |
| [Kalshi market](https://docs.kalshi.com/api-reference/market/get-market) and [book](https://docs.kalshi.com/api-reference/market/get-market-orderbook) | Active binary $1/default-bound markets only; opposing bids produce complementary asks with unchanged quantity. REST has no book timestamp |
| [Kalshi orderbook updates](https://docs.kalshi.com/websockets/orderbook-updates) | Snapshot/delta fixed-point fields, subscription-scoped `seq`, market `clock`, envelope `sending_ts_ms`; snapshot includes updates through its clock, subsequent deltas must be beyond it |
| [US market detail](https://docs.polymarket.us/api-reference/markets/get-market-by-slug) and [book](https://docs.polymarket.us/api-reference/markets/get-market-book) | Explicit tradable long/short instrument identities, `orderPriceMinTickSize`, `minimumTradeQty`; YES bids/offers, USD quantities/prices, `transactTime` |
| [US fractional contracts](https://docs.polymarket.us/learn/trading/basics/fractional-shares) | Supported conservative quantity grids are 0.01 or 1 when the market minimum matches; unknown minima are refused, not treated as universal lot specifications |
| [US buying YES versus selling NO](https://docs.polymarket.us/learn/trading/basics/buying-yes-vs-selling-no) | Short-YES exposure represents synthetic NO; `1-bid` is a quote/payoff representation, not a separate NO-token buy route |
| [US market WebSocket](https://docs.polymarket.us/api-reference/websocket/markets) | Authenticated market-data snapshots; no assumed sequence/delta continuity contract |

Kalshi's sequence is not per market when multiple markets share a subscription.
The offline helper therefore requires one market per subscription. Its clock can
skip/repeat across deltas and is not checked as a contiguous counter. Send time
is labeled provider send time, never mutation time. Both documented WebSockets
require authentication; neither was connected or tested live. Only public REST
collectors and deterministic hypothetical stream replay were run.

Missing Kalshi REST source time blocks fresh comparisons; receipt time, HTTP Date
and metadata timestamps are never substituted. All quotes remain `UNVERIFIED`.
See [M3 results](M3_RESULTS.md) for measured evidence and [book inspection](BOOKS.md)
for fail-closed rules. M1 data-use restrictions above still apply; no new rights
or real-pair equivalence finding is claimed.

## M4 fee verification — 2026-10-21

Primary documents were checked before implementing fee math. The
[manifest](evidence/M4_API_CHECKS.json) records downloaded Markdown hashes and
save times. A direct Kalshi PDF fetch returned HTTP 429; the current official PDF
was successfully read through the browser tool, without claiming a local PDF hash.

| Official source | Supported use |
| --- | --- |
| [Kalshi schedule, effective July 7, 2026](https://kalshi.com/docs/kalshi-fee-schedule.pdf) | General taker coefficient 0.07 times reviewed series multiplier; exceptions and account charges must be checked |
| [Kalshi fee rounding](https://docs.kalshi.com/getting_started/fee_rounding) | Six-decimal trade-fee ceiling, account balance alignment, per-order accumulator and capped rounding rebates |
| [Kalshi series](https://docs.kalshi.com/api-reference/market/get-series) and [scheduled fee changes](https://docs.kalshi.com/api-reference/exchange/get-series-fee-changes) | Fee type/multiplier and scheduled applicability; no global default mapping of every instrument |
| [Polymarket US fee schedule](https://docs.polymarket.us/fees) | Effective October 19, 2026, 17:00 UTC: symmetric taker coefficient 0.0695; Table Tennis 0.10; cent half-even rounding with cumulative taker-order cap |

US combos use a different curve and are unsupported. Maker/tier rebates are not
credited. The previous flat US fee assumptions are not used. Kalshi balance
precision differs for direct/non-direct accounts and must be declared. Fee
applicability, settlement costs, account exceptions and changes are reviewed for
each exact market/side and bounded time window; no live profile was automatically
approved. See [economics guide](ECONOMICS.md).

Public depth does not expose resting-order fragmentation. M4 distinguishes exact
rounding for a declared hypothetical fill partition from conservative fee bounds
for quotes. Source documents and operator applicability declarations are archived
with hashes; they do not establish fills, eligibility or trading authority.
No new authenticated API, account endpoint or order method was called. Terms and
provider data restrictions above continue to apply. [M4 results](M4_RESULTS.md)
document the tests and remaining 30-day acceptance gap.

## M5 operational verification — 2026-10-22 UTC

M5 consumes M3's versioned normalized books and M4's fee/provenance contracts;
it introduces no new venue fields, authenticated connection or order endpoint.
Paper arrival/cancel/participation fields are explicitly local hypothetical
model inputs, not claimed exchange execution reports.

Operational implementation checked current primary documentation:

- [SQLite online backup](https://www.sqlite.org/backup.html): use the snapshot API,
  verify contents and restore to a new path; do not copy a live main file alone.
- [systemd service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
  and [execution environment](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html):
  bounded service lifecycle, exit/restart behavior and filesystem/account limits.
- [timedatectl](https://www.freedesktop.org/software/systemd/man/latest/timedatectl.html):
  read synchronization state through machine-readable `show`; this does not
  establish measured clock offset or configure the host's time service.

The [source/unit manifest](evidence/M5_SOURCE_AND_UNIT_CHECKS.json) records URLs,
verification time, local systemd version and actual successful unit syntax check.
No units or time settings were activated/changed. [M5 results](M5_RESULTS.md)
distinguish hypothetical stress evidence, actual short host/restore tests and the
remaining live/multiweek acceptance gaps. Provider rights and review requirements
above still apply before any ongoing collection.
