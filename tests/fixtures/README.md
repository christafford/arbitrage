# Public US provider fixtures

These are **real public API snapshots**, captured without credentials on
2026-10-21 UTC. They are historical observations, not hypothetical prices,
trade signals, approved equivalent contracts, or evidence of fills.

Each JSON envelope has the exact request URL, UTC retrieval time, HTTP status,
allowlisted headers, upstream/local schema version, unchanged raw JSON body as a
string, and the body's SHA-256. Infrastructure IDs and `Set-Cookie` headers were
removed. No fields, prices, quantities, instrument IDs or resolution text in a
response body were changed. JSON envelope formatting is not part of the body hash.

- `kalshi-*` uses Trade API 3.34.0, local contract `kalshi-3.34.0/m1-v1`.
- `poly-*` uses US public MarketService 1.0.0, local contract
  `polymarket-us-marketservice-1.0.0/m1-v1`.
- `*-page.json` / `*-page2.json` are consecutive unscoped catalogue pages.
- `*-scoped-acceptance.json` contains every response in a complete scoped
  acceptance collection, including the real terminal pagination response, details
  and selected books. Its `run` records the original collection summary.
- `*-live.json` contains individual detail, event, series or book samples.
- `m3-live-snapshots.json` contains three new real public book/detail pairs captured
  at 21:23 UTC on 2026-10-21, with exact normalization expectations and evaluation
  clocks. Each nested response preserves its unchanged body, SHA-256, URL,
  receipt time and schema contract. Its sanitizer removes infrastructure and
  cookie headers, not payload fields. Replay verifies hashes and exact results.

`m3-hypothetical.json` is explicitly **HYPOTHETICAL**, with synthetic market IDs,
rules, quotes, dates and a 2030 replay clock. It exercises exact complementary
depth, fractional sizes, US synthetic NO and offline Kalshi sequence recovery.
Its representative metadata shape derives from the public schemas; it establishes
no real settlement equivalence or observed stream behavior. Generated variations
in tests and `scripts/m3_demo.py` are also hypothetical.

`m4-hypothetical.json` extends the synthetic shapes with inverse propositions,
two long-buy ladders, explicit hypothetical fee applicability/settlement costs
and budgets. It is used only in isolated replay databases, with a 2030 clock.
Its fee rates exercise the implemented math; the fixture is not evidence that
those rates apply to real instruments. Fee-document declarations in the demo
are visibly hypothetical. The actual official fee-document check is recorded
separately in [M4 sources](../../docs/API_SOURCES.md).

`m5-hypothetical.json` declares seven **HYPOTHETICAL** later-quote/outage/liquidity/
price/latency scenarios and a paper policy. The demo generates full provider-shaped
ticks from the M4 synthetic fixture and archives each byte sequence before
normalization. These are assumed fills/cancel windows, not actual feed changes,
observed executions or measured fill probabilities. The generated SQLite paper
tables preserve input hashes and independent case results; see
[M5 results](../../docs/M5_RESULTS.md).

Offline tests validate unchanged captures and replay their request sequences.
Altered failure/overlap/empty-book scenarios are explicitly labeled
**HYPOTHETICAL** in tests and are never written over these captures. Acceptance
replay injects original receipt times and a fixed clock, then compares two runs
for identical counts, rule evidence hashes and book freshness classifications.
Nanosecond source timestamp strings remain unchanged in raw storage; Python
uses microsecond precision only when computing ages.

Provider data rights are reserved by each venue, separately from the MIT license
on this project's code. Keep these samples local; do not publish or redistribute
without applicable permission. See [official sources and restrictions](../../docs/API_SOURCES.md).
