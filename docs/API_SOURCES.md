# Official API sources and M1 contracts

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
