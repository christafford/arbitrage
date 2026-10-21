# Codex roadmap (execute sequentially)

Milestones are **not complete merely because files exist**. Every milestone needs measured acceptance evidence and tests. The initial repository provides portions of M0 and M1, not a complete scanner.

## M0 — Local baseline (starter code)

- [x] Python package, CLI, SQLite WAL, pure arithmetic test fixtures.
- [x] Read-only raw collectors for provider API exploration.
- [x] Mock sample and no-trade demo.
- [ ] CI verified in a networked environment, documentation checked against live responses.

Acceptance: `pip install -e .`, `predarb demo`, `predarb report`, all tests succeed offline; collectors fail clearly if inaccessible.

## M1 — Read-only venue catalogues

- [ ] Verify current official US API schemas and licensing/ToS; make sanitized fixtures for each.
- [ ] Kalshi pagination, market/event details, exact rule evidence and book snapshots.
- [ ] Polymarket US pagination, symbols/instruments/metadata, book data, exact rule evidence.
- [ ] Strict schema validation, separate provider timestamps, retry/backoff, rate limits, deduplication.
- [ ] Tests against provider fixtures, error and drift behavior.

Acceptance: real raw snapshots from BOTH US venues; known schema, no fabricated defaults; counts reconcile with paginated responses.

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
