# Public US provider fixtures

`kalshi-ws-missing-clock-live.json` is **actual rejected production evidence**,
captured on 2026-10-23 UTC during Workstream B diagnostics. It contains market
metadata, acknowledgment, initial snapshot, incremental delta and an explicit
snapshot-request response. Each body has endpoint, receipt time, local schema,
SHA-256 and (for frames) verified exact-wire hash. Public-shaped frame bytes are
unchanged; no signed headers, keys or account identifiers are included. All book
messages lack `msg.clock`. Offline tests preserve their rejection under the
original clock-required contract; separate explicit pre-rollout tests also
exercise `sequence-v1`. Original rejected archives are never relabeled or rewritten.
See [protocol discrepancy](../../docs/KALSHI_PROTOCOL_DISCREPANCY.md).

`kalshi-ws-sequence-live.json` is **actual accepted pre-rollout evidence** captured
on 2026-10-23 UTC. It retains 225 exact public-shaped frames across three
connections, with per-generation public metadata, receipt times, schema versions,
hashes and connection boundaries. It includes real recovery after a message
timeout. Authentication headers and account identifiers are excluded. All 222
book states replay identically in two isolated test archives; no market clock is
invented. Capture-time validity never establishes current quote usability, contract
equivalence or fills. See [B acceptance](../../docs/M5B_SEQUENCE_RESULTS.md).

The original REST fixtures below are **real public API snapshots**, captured without credentials on
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

`m5-operations-hypothetical.json` contains **HYPOTHETICAL** backup metadata and
clock faults with a 2030 test clock. Hashes are synthetic placeholders and its
snapshot stand-ins are deliberately not valid SQLite backups. It tests structural
and age monitoring, separately from real SQLite backup/restore tests. No venue API
schema or retrieved host evidence is represented by this fixture.

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

`discovery-hypothetical.json` is an explicitly hypothetical `discovery-v1`
matching fixture with a 2030 replay clock. It covers alias/description/date and
threshold normalization. Existing sanitized live pages/details/books supply the
provider-schema replay; altered test sequences remain hypothetical. No fixture
attests real contract equivalence.

## M5A WebSocket

`m5a-ws-hypothetical.json` is an explicitly hypothetical acknowledgment fixture
for local schema `kalshi-ws/m5a-v1`, paired with the existing M3 snapshot and
generated deltas in `test_kalshi_ws.py`. Its source-check timestamp identifies
the official document retrieval, **not a live frame receipt**. No authenticated
live fixture exists: the operator confirmed credentials are unavailable.

## M5A C fee sources (2026-10-23 UTC)

`m5c-kalshi-live.json` and `m5c-polymarket_us-live.json` preserve 7 and 2 actual
credential-free responses, respectively. Each includes the original UTF-8 body,
URL, HTTP status, allowlisted headers, exact receipt time, SHA-256 and local schema
`live-fee-evidence/m5a-c-v1`. Kalshi upstream API is 3.34.0; US MarketService is
1.0.0. Source Markdown is retained verbatim alongside JSON. The top-level request
is the local capture manifest, not a venue response. Provider rights reserved;
these are local research/replay fixtures, not redistribution permission.

Test mutations for fee changes, overrides, malformed fields, clock drift and
simulated human approvals are explicitly HYPOTHETICAL. No real fee or pair
approval is a fixture outcome. The sample Kalshi market had already reached its
close; fee capture does not establish trading availability or book freshness.
The operator-supplied PDF stays in ignored local data storage; its hash/provenance
are recorded in `docs/evidence/M5C_API_CHECKS.json`.

## M5A D payout/collateral/settlement mechanics

`m5d-us-documents-live.json` contains three unchanged official public US Markdown
responses, with retrieval UTC, exact URL, allowed headers, original UTF-8 body and
SHA-256. Local document schema: `official-mechanics-documents/m5a-d-v1`. They are
prose evidence, not a new venue API schema. Provider rights reserved; local
research only. The full ten-source retrieval manifest is in
`docs/evidence/M5D_API_CHECKS.json`; original archives are in ignored local data.

`m5d-hypothetical.json` is an explicitly HYPOTHETICAL operator review for the M4
synthetic instruments at their fixed 2030 clock. It binds existing synthetic source
hashes to payout/collateral/timing roles, selects isolated cash-funded longs and
assumes cash availability one and three days after settlement. These delays,
account statements and approvals were not observed at either venue. Exceptional
payouts and altered partial-fill cases exercise fail-closed rounding and downside
checks. Neither fixture establishes real settlement equivalence or trading authority.

`soak-hypothetical.json` is a local collection-run configuration used with the
synthetic M3 metadata/books and an accelerated clock. Transport errors, timing,
disk conditions and shutdowns in those tests are hypothetical. Registry observation
is isolated so synthetic IDs cannot enter the real registry.

`soak-us-stale-live.json` instead contains two exact public API bodies from the
2026-10-25 smoke: US market detail and a book with an actually stale source clock.
Each has its official endpoint, original receipt time, schema, body hash and
allowlisted headers. No credentials/private account payloads are included. Replay
retains `STALE_SOURCE`; receiving the response does not invent a new source time.

`sports-discovery-live.json` preserves six exact public market-detail responses
for the Denver–Arizona, Lakers–Jazz and Memphis–Sacramento event identities. It
also includes two explicitly reserialized market excerpts from archived catalogue
pages for the observed soccer/college-football false match. Original parent hashes,
receipt clocks, URLs, schemas and representation labels distinguish excerpts from
whole responses. Same-event identity is not payout equivalence. Mutations and
registry decisions in the sports tests are hypothetical; no live pair is approved.

`embeddings-hypothetical.json` is a synthetic `llama-embeddings/v1` protocol fixture
plus six hand-labeled review-retrieval pairs and unrelated distractors. Its vectors
are hand-authored; `retrieved_at=null` intentionally makes no live capture claim.
The real service benchmark, when available, is separate from offline integration
recall. No labels approve settlement equivalence.

`embedding-invalid-live.json` records the actual 2026-10-27 private-service probe:
model ID `qwen3-reranker-0.6b`, with an invalid 1,024-element response containing
14 nulls and 1,010 zeros. Model info is a labeled sanitized consumed-field excerpt;
the embedding body is exact. SHA-256, parent hash, UTC retrieval time, endpoint,
headers and local schema are recorded. Tests replay this as a rejection, never
promote it to a valid model embedding or normalize nulls to zero.
