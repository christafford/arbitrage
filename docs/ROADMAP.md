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
`UNVERIFIED`; no live trading was implemented. **Stop before M2.**

## M2 — Pair review registry

- [ ] Candidate generation from metadata only; no automatic approvals.
- [ ] Human reviewed paired rules with source hashes and approval expiry/invalidation.
- [ ] Explicit complement mapping, payout/void scenarios and settlement timing.
- [ ] CLI to review/approve/revoke and audit decisions.

Acceptance: intentionally near-identical-but-different example remains rejected. Changed rules revoke approved mapping.

## M3 — Order-book normalization

- [ ] Normalize YES/NO actionable ask depth for each venue with documented side semantics.
- [ ] Check sequence gaps, snapshot/reconnect, timestamps, tick/lot increments.
- [ ] Reject stale/incomplete or incomparable data.

Acceptance: fixture tests for complementary bids, depth exhaustion, stale and partial books, crossed data.

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
