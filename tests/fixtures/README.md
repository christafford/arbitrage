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
