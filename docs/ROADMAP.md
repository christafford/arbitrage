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
real pair was approved, and no trading was implemented. M4 was separately
authorized afterward.

## M4 — Economics and recording — IN PROGRESS (2026-10-21)

- [x] Versioned supported taker models by venue/instrument/side/time, exact hypothetical fill rounding and conservative quote fee bounds; archived operator-declared applicability, bounded expiry and explicit settlement fees. No guessed zero fees or installed live profiles.
- [x] Per-level two-leg cost, fee bounds, positive explicit slippage reserve and conservative net edge; complete bounded common-lot search and stale/depth/approval gates.
- [x] Independent venue research budgets, simultaneous-full-fills assumption labeled, reviewed settlement delays and locked-capital ranking. Synthetic US NO capital mechanics are unsupported and rejected.
- [x] Derived-detail retention (at least 31 days), durable audit/summaries/source hashes, aggregates and CSV exports. Raw source evidence is retained; total archive growth still needs an operational policy.
- [x] Bounded/resumable read-only polling, optional public refresh for approved pairs, rejection records, cadence/equal-quote sampling metrics and schema-4 migration.
- [ ] Actual 30-day scanner run with audit trail, current reviewed pairs and fee applicability, useful fresh cross-venue data, measured quote lifespan and audited rejection records.

Acceptance: 30-day scanner with audit trail; no unreviewed pairs, measured book lifespan and record of rejection reasons.

Implementation evidence: **124 tests passed**, hypothetical end-to-end demo,
both bounded live collector smoke runs, preserved-copy M3 migration and research
CLI smoke checks. Hypothetical demo selected 200 contracts / $183.46 modeled
capital / $16.54 conditional profit bound, then rejected stale books. A live-mode
smoke recorded an unreviewed-pair rejection and performed no unreviewed economics.
This is not 30-day evidence. See [M4 results](M4_RESULTS.md),
[economics guide](ECONOMICS.md).

M4 is **not complete**: no actual 30-day run/audit, no real approved pair or fee
profile, and no timestamped Kalshi live source. REST's unknown source time remains
a hard rejection. Real quote-lifespan measurement and operational evidence remain
pending. No orders, credentials or funding were added. M5 implementation was
separately authorized while this M4 acceptance remained open.

## M5 — Paper execution and operational hardening — IN PROGRESS (2026-10-22 UTC)

- [x] Exact hypothetical adverse-selection, one-leg/partial-fill, hedge-deadline, cancellation-race and outage models; reviewed payout downside and fee/reserve bounds. No actual positions or orders.
- [x] Local health/metrics/journal alerts, clock/disk/WAL checks, single-writer guard, graceful monitor signals, verified SQLite backup/new-path restore and hardened systemd templates/docs. Units syntax-checked, not installed or activated.
- [x] Implement gated paper intents and immutable later-quote comparison inputs/results, bounded monitor integration and deterministic isolated hypothetical replay.
- [x] Pre-run M5 hardening: expose empty/data-gated cycles and disabled refresh; reject orphan/malformed backup metadata; detect clock divergence after scan/paper work. See [verification](M5_HARDENING.md).
- [ ] Actual live forward shadow comparison and multiweek zero-money run; reproducible coverage/incident/downside audit with useful fresh approved data.

Acceptance: multiweek zero-money run, reproducible reports, no high-severity incidents, realistic downside scenarios documented.

Implementation evidence: **154 tests passed**, seven hypothetical stress cases,
both live collector compatibility checks, preserved-copy M4 migration, verified
backup/restore fingerprints, actual SIGTERM stop after a completed cycle and
systemd unit syntax verification. One-leg outage modeled a conditional $85 loss
and 200 unhedged contracts; unequal fills modeled $64.69 loss and 160 unhedged.
These are assumed paper outcomes, not actual losses/fills. Evidence and operational
limits: [M5 results](M5_RESULTS.md), [paper guide](PAPER_EXECUTION.md),
[operations](OPERATIONS.md).

M5 is **not complete**: no actual multiweek run, live intent/fill observations,
enabled service or sustained incident audit. M4's live approval/fee/source-time
prerequisites remain unresolved. No credentials, real orders/cancellations,
funding or M6 work were added. **Stop before M6.**

## M1/M2 discovery extension — IMPLEMENTED (2026-10-22 UTC)

- [x] Bounded, rate-paced active catalogue refresh for both US venues and hourly timer templates.
- [x] Search all fresh instruments by default using subjects, normalized descriptions, event dates and thresholds; expose conflicts and unknowns.
- [x] Rank by heuristic equivalence with exact displayed-depth tie-breaking and explicit stale/unknown liquidity.
- [x] Persist a review queue with definition links, evidence versions and prior decisions; preserve every human approval requirement.
- [x] Schema-6 migration, fixtures, offline integration tests, CLI smoke checks and operational documentation.
- [x] 2026-10-24 correction: accept documented optional/null US metadata `updatedAt` without inventing source time; preserve strict book clocks and failed-run history. See [verification and recovery](DISCOVERY_UPDATED_AT_RESULTS.md).
- [x] 2026-10-25 sports-discovery correction: dedicated NBA/NFL full-game identity matching, strict league/team/type/date/side checks, separate timestamp roles and explicit postponement warnings; unsupported recognized sports cannot use generic overlap. Scoped live refresh and activity checks are documented in [sports results](SPORTS_DISCOVERY_RESULTS.md).

See [verification](DISCOVERY_RESULTS.md) for executed tests/live coverage and
[operation](DISCOVERY.md) for limits. This extension does not satisfy M4/M5's
pending sustained-run acceptance or authorize M6. No real equivalence was approved.

## M5A — Live research readiness — IN PROGRESS (2026-10-22 UTC)

A/B were authorized first. The operator separately authorized **Workstream C** on
2026-10-23, then **Workstream D**, and **Workstream E** on 2026-10-24. Stop before M6.

- [x] A: reuse the implemented discovery extension and ranked UNVERIFIED human-review queue; existing live catalogue coverage remains partial.
- [x] B implementation: authenticated read-only Kalshi transport, protected external credentials, raw/sanitized provenance, sequenced snapshot/delta validation and recovery, M3/M4 integration, offline tests and documentation.
- [x] B live acceptance for explicit pre-rollout `sequence-v1`: authenticated timestamped snapshots/deltas, actual reconnect recovery and deterministic replay passed on 2026-10-23. The longer run captured 3 snapshots and 219 deltas across 3 generations and recovered after a real message timeout; a separate clean run exited 0. **Compatibility expires 2026-10-29 00:00 UTC; the default clocked protocol still requires live revalidation after the announced rollout.** See [B acceptance evidence](M5B_SEQUENCE_RESULTS.md).
- [ ] Human approval of equivalent real pairs; never an agent decision.
- [x] C tooling: public fee-source capture, unapproved review packets, exact model/provenance and scheduled-change gates, failed-refresh invalidation, offline replay and live capture checks. See [C results](M5C_RESULTS.md).
- [ ] C operator acceptance: account/instrument applicability and actual live fee profiles remain unapproved; sample packets are ready for review.
- [x] D implementation/source verification: explicit mechanics reviews, source/route checks, cash-availability timing, exact scenario cashflows, fractional payout gates and paper integration. US short-exposure restrictions remain; see [D results](M5D_RESULTS.md).
- [ ] D operator acceptance: real instrument/account mechanics and cash-timing assumptions remain unreviewed; no real settlement observations or approvals were fabricated.
- [x] E tooling: read-only research-readiness CLI report with current approval/mechanics/fee/book gates, session policy, host/backup observations, protocol horizon, explicit blockers and offline tests. See [E verification](M5E_RESULTS.md) and [operator guide](READINESS.md).
- [ ] E operational acceptance: a real passing snapshot, deployed refresh cadence and sustained useful research observations remain pending; CLI completion is not multiweek acceptance.

Evidence and explicit gaps: [M5A results](M5A_RESULTS.md),
[WebSocket setup and failure behavior](KALSHI_WEBSOCKET.md). Offline simulation
does not establish live acceptance. M4/M5 sustained-run acceptance remains pending.
No real equivalence approval, fee approval, order, funding or M6 work.

### M5A collection-soak operational extension — authorized 2026-10-25

- [x] Bounded single-writer Kalshi streaming / US polling coordinator in an isolated archive; explicit selected instruments, no pair/economic decisions.
- [x] Periodic freshness/skew samples, safe retry/cooldown, signal shutdown, protocol horizon, disk/storage guards, heartbeat reporting and verified backup pauses; fixtures, unit/integration tests and operator guide.
- [ ] Actual 24-hour run and post-run inspection of gaps, freshness, reconnects, growth, restore/replay. Starting a process does not satisfy this criterion.

See [collection soak](COLLECTION_SOAK.md) and [implementation/live evidence](SOAK_RESULTS.md).
Rejected Fed contracts may be used for collection testing only. Overall M5A,
M4's 30-day economics and M5's multiweek acceptance remain open.

## M6 — OPTIONAL live trading proposal (DO NOT IMPLEMENT WITHOUT EXPLICIT GO-AHEAD)

- [ ] Human-approved security/risk design; separate order execution module, off by default.
- [ ] Explicit proof of eligibility, current fee/access/terms, and risk parameters.
- [ ] Stage-gated $200–$500 funding pilot with operator sign-off before each increase.

## M1/M2 private embedding discovery extension — authorized 2026-10-27

- [x] Environment-configured llama.cpp inference, dynamic dimension validation,
  batched content/model cache, bounded retries/timeouts and persistent circuit breaker.
- [x] Existing deterministic matcher survives inference failures; semantic candidates
  retain stale-data, sports, conflict, human-review and no-trading gates.
- [x] Schema-8 migration, labeled protocol fixtures, unit/integration tests,
  repeatable retrieval recall benchmark and operator documentation.
- [x] Live gaming-PC HTTPS connectivity and raw schema capture; actual invalid
  vector output is rejected and preserved as a regression fixture.
- [x] Valid actual model/dimension probe and measured model recall: replacement
  `qwen3-embedding-8b` returns 4,096 valid dimensions; live recall@3 was 6/6 versus
  2/6 deterministic on the small hypothetical corpus, with 15/15 warm cache hits.
  See [acceptance evidence and limits](EMBEDDING_RESULTS.md).

This is one research discovery extension. It does not complete M4/M5 acceptance,
provide full-catalogue semantic coverage or authorize M6/live-money work.


### Private embedding discovery category correction — 2026-10-27

- [x] Correct generic US futures metadata classification using explicit non-sports
  categories, retaining unknown/positive-sports exclusions and all approval gates.
- [x] Preserve broad sports exclusions in queue reports and distinguish selected
  from completed embedding counts; official source capture and real fixtures.
- [x] Regression/unit/integration tests and fresh-cache reranking verification;
  [results and remaining coverage limits](EMBEDDING_CATEGORY_RESULTS.md).

This repairs the existing discovery extension. Partial paging and the 512-input
per-venue semantic cap remain explicit; no sports-format expansion or trading
milestone is authorized by this change.

## M5I — Production-scale semantic discovery — IMPLEMENTED; BROAD ACCEPTANCE PARTIAL (2026-10-28 UTC)

- [x] Resumable public catalogue walks, page checkpoints, bounded per-venue budgets,
  schema-9 migration and interrupted-page replay; no first-provider-page coverage claim.
- [x] Separate persistent metadata/FTS/vector sidecar; 339,137 archived heads
  synchronized, new/modified-version priority, unchanged-text reuse and bounded
  asynchronous inference. Source collection does not take the AI worker lock.
- [x] Sports identity + keyword + persistent approximate vector retrieval, current
  source/TTL/model checks, horizon/mechanics filtering, verified-liquidity tie-breaking,
  contradiction priority and diversity across both venues' event groupings.
- [x] Genuine 49-definition labeled corpus, measured Recall@20/@100, precision,
  false negatives, throughput, model/source provenance and zero additional labeled
  reviewable events versus the deterministic baseline. No model-quality gain inferred
  from the earlier synthetic 6/6 benchmark.
- [x] Failure/restart/model/change/staleness/partial-index tests, full-suite and CLI
  smoke validation, dependency/unit checks and 20 freshly captured review candidates.
- [ ] Complete production vector backfill and query traversal; current coverage is
  576/121,065 Kalshi and 560/9,027 US eligible definitions at the measured snapshot.
- [ ] Broad independently adjudicated retrieval quality and incremental reviewable
  semantic yield; approximate bucket saturation and partial coverage remain limits.

See [measured results and 20-event review shortlist](M5I_RESULTS.md),
[operations](M5I_OPERATIONS.md), and exact linked evidence. Implementation and
bounded validation are complete; broad production acceptance is **not complete**.
No service was activated, real contract approved, or trading/funding path added.
Stop after M5I; M6 remains unauthorized and previous sustained-run gaps remain open.
