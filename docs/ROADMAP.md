# Codex roadmap (execute sequentially)

Milestones are **not complete merely because files exist**. Every milestone needs measured acceptance evidence and tests. The initial repository provides portions of M0 and M1, not a complete scanner.

## M0 — Local baseline (starter code)

- [x] Python package, CLI, SQLite WAL, pure arithmetic test fixtures.
- [x] Read-only raw collectors for provider API exploration.
- [x] Mock sample and no-trade demo.
- [ ] CI verified in a networked environment, documentation checked against live responses.

Acceptance: `pip install -e .`, `predarb demo`, `predarb report`, all tests succeed offline; collectors fail clearly if inaccessible.

## M1 — Read-only venue catalogues — COMPLETE (2026-10-21)

- [x] Verify current official US API schemas and licensing/ToS; make sanitized fixtures for each.
- [x] Kalshi cursor pagination, selected market/event/series details, exact rule evidence and book snapshots.
- [x] Polymarket US public gateway offset pagination, instrument identities/side metadata, book data, exact provider rule evidence. Institutional refdata returned 401; public US MarketService is the documented credential-free implementation.
- [x] Strict consumed-field schema validation, separate provider timestamps, retry/backoff, conservative rate limits, deduplication and explicit partial runs.
- [x] Tests against real provider fixtures, failure/drift behavior and deterministic complete-run replay.

Acceptance passed: real raw snapshots from BOTH US venues; versioned known schemas;
no fabricated price/quantity/timestamp defaults; counts reconcile with paginated
responses. Final live scoped runs: Kalshi pages `[1,1]`, 2 unique markets, 2 books,
8 raw responses; Polymarket US pages `[1,0]`, 1 unique market, 1 book, 4 raw responses.
Both reached terminal pagination. **41 offline tests passed**, plus installation,
demo/report and both live collector smoke commands. Full evidence, actual scopes,
terms restrictions and limitations: [M1 results](M1_RESULTS.md).

No remaining M1 implementation blocker on the public path. Kalshi REST source book
time remains explicitly unknown. Full-venue atomic completeness, institutional
access and data redistribution rights are not claimed. All records remain
`UNVERIFIED`; no live trading was implemented. M2 was separately authorized afterward.

## M2 — Pair review registry — COMPLETE (2026-10-21)

- [x] Candidate generation from metadata only; no automatic approvals.
- [x] Human review workflow with exact imported resolution text, raw/text source hashes, versioned market/event/series evidence, approval identity/time, and bounded expiry/invalidation.
- [x] Explicit bijective outcome mapping, complementary leg selection, normal/void/cancellation/suspension/source-revision payout scenarios and settlement timing.
- [x] CLI to inspect forms, approve, reject, revoke, list and audit decisions; immutable history and schema-2 migration/backfill.

Acceptance passed: identical hypothetical titles with FIRST-versus-FINAL report
semantics remain REJECTED; changed market/event/series/document evidence invalidates
approvals without automatic restoration. CLI demonstration ended with one REJECTED,
one REVOKED and one INVALIDATED hypothetical pair. **63 tests passed**; both live
collector smoke commands and a preserved-copy M1 archive migration also passed.
Evidence, operator workflow and limits: [M2 results](M2_RESULTS.md),
[pair review guide](PAIR_REVIEW.md). No real pair was approved. M3 was separately
authorized afterward.

## M3 — Order-book normalization — COMPLETE (2026-10-21)

- [x] Normalize YES/NO ask representations for both US venues with documented side semantics; US NO explicitly represents synthetic short-YES exposure, with no execution authorization.
- [x] Check timestamps and documented supported grids; offline Kalshi sequence-gap, snapshot/reconnect, clock and connection-generation recovery. REST snapshots replace independently; no invented US sequence protocol.
- [x] Reject stale/incomplete/crossed/off-grid or incomparable data; recheck raw provenance, current metadata, registry validity and source/receipt skew. Schema-3 assessments and local inspection CLI preserve replay.

Acceptance passed: real and hypothetical fixture tests cover complementary bids,
exact depth exhaustion, stale/partial/empty/crossed books and recovery failures.
**101 tests passed**, offline demo and both bounded live US collector smoke runs
passed. Three live books normalized: both Kalshi books correctly rejected unknown
source time; US book passed at capture and was later rejected as stale. Preserved-copy
M2 migration passed. Evidence: [M3 results](M3_RESULTS.md), [book guide](BOOKS.md).

No remaining M3 fixture/normalization acceptance failure. Authenticated streaming
was not connected; recovery is tested offline. Kalshi REST cannot supply a
freshness-qualified live comparison. All live evidence remains `UNVERIFIED`, no
real pair was approved, and no trading was implemented. **Stop before M4.**

## M4 — Economics and recording

- [ ] Versioned exact fee models by venue/instrument/time; do not guess 0 fees.
- [ ] Per-level achievable two-leg cost, fees, slippage reserve, conservative net edge.
- [ ] Capital allocations across venues, simultaneous fills assumption labeled, locked-capital ranking.
- [ ] Retention, aggregates, summary and CSV exports.

Acceptance: 30-day scanner with audit trail; no unreviewed pairs, measured book lifespan and record of rejection reasons.

## M5 — Paper execution and operational hardening

- [ ] Model adverse selection, one-leg fill, partial fills, max hedge latency, cancellations, API outages.
- [ ] systemd deployment docs, backup/restore drill, metrics, alerting, time sync, disk monitoring.
- [ ] Forward-test shadow executions without actual orders; compare to later observed ticks.

Acceptance: multiweek zero-money run, reproducible reports, no high-severity incidents, realistic downside scenarios documented.

## M6 — OPTIONAL live trading proposal (DO NOT IMPLEMENT WITHOUT EXPLICIT GO-AHEAD)

- [ ] Human-approved security/risk design; separate order execution module, off by default.
- [ ] Explicit proof of eligibility, current fee/access/terms, and risk parameters.
- [ ] Stage-gated $200–$500 funding pilot with operator sign-off before each increase.
