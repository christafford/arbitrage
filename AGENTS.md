# Codex operating instructions

You are implementing a **capital-constrained, US-only, research-first prediction-market arbitrage scanner**. The human operator has a *hard $10,000 cumulative external seed funding ceiling* and wants to begin with zero-dollar simulation and ultimately small experimental stakes, not immediate live trading.

## Mandatory workflow

1. Read README.md, docs/PRODUCT.md, docs/ARCHITECTURE.md, docs/RISK.md, docs/ROADMAP.md, docs/API_SOURCES.md before editing.
2. Take **one roadmap milestone at a time**; state what it changes, then implement code + fixtures + unit/integration tests + documentation together.
3. Before relying on an external API field, check the current **official US venue documentation**. Save representative *sanitized* JSON fixtures; document schema version and retrieval time. **Never silently use polymarket.com (international) APIs**.
4. Run `python -m unittest discover -s tests -v` and smoke commands after changes. Report exactly which tests executed; do not claim unrun tests passed.
5. Keep the default mode read-only and fail closed on uncertainty. If contracts cannot be confirmed equivalent, flag as `UNVERIFIED`, never actionable.
6. Do not add trading credentials, place-order endpoints, deposit logic, margin/leverage, or network-exposed admin endpoints as part of research milestones.
7. Never mark a milestone complete until its acceptance criteria and tests pass; explicitly list gaps and blockers.
8. Use integer cents or `Decimal` for money/price calculations; do not use binary floats for trading computations. Use UTC timestamps, provenance, and explicit stale-data handling.
9. Archive raw source responses before conversion. Error on unknown schema instead of inventing or defaulting missing prices/quantities.
10. Preserve deterministic offline replay and test paths; mocks and examples **must** be visibly labeled hypothetical.

## Engineering preferences

- Favor straightforward Python stdlib + SQLite initially on constrained hardware. Revisit C++ only if measured profiling justifies it.
- Modular adapters, strongly typed domain objects, deterministic pure profit evaluator, resumable polling, bounded retention.
- Structured UTC logs, request timeouts, retries with backoff (future task), rate-limit compliance, graceful shutdown.
- Single-writer SQLite, WAL, migrations before schema changes, backups and space thresholds.
- Explicit operator approvals for contract matching decisions. LLM output can suggest a match but cannot approve settlement equivalence.
- Future order workflows need idempotency, partial-fill accounting, position reconciliation, risk caps, and emergency stop. Do not implement orders until milestone authorization.

## Definition of done

Every added path has tests (success, missing fields, stale data, invalid prices, partial liquidity where relevant). Docs explain setup, verification, operational failure modes. Run code; inspect output; do not fabricate evidence. Keep changes focused and committed in small logical units where repository supports commits.

## M5I semantic discovery boundary

- Stop after M5I. No M6, orders, automatic equivalence decisions, or changes to
  settlement/fee/clock/collateral gates are authorized.
- Production semantic work uses the separate `.semantic.sqlite3` sidecar. Open the
  source archive read-only in workers; never hold its writer lock during inference.
- `discovery refresh` performs collection and bounded indexed retrieval without
  inference. Use `index-sync`, `index-work`, and `index-retrieve` for resumable
  asynchronous work. `--cached-catalogues` must make no venue requests.
- Catalogue coverage, metadata synchronization, vector coverage, and evaluated
  recall are separate denominators. Report UNKNOWN categories/deadlines honestly.
  A provider prefix or a filled review queue is not representative coverage.
- Preserve model namespaces, raw inference provenance, current source versions,
  stale-data exclusions, and deterministic retrieval during AI outages. Approximate
  bucket saturation and remaining traversal/backfill must remain visible.
- Genuine evaluation labels describe ordinary propositions, not legal equivalence.
  Assistant labels require independent operator adjudication before any quality
  claim beyond the documented corpus; never convert them into registry approvals.
- The October 28 M5I collection/backfill run stopped at its October 29 deadline;
  its units are disabled. Inspect `docs/M5I_RUN_20261028_RESULTS.md` and status files
  before further operational work; full backfill and contradiction handling remain open.
  Preserve its fixed deadline, namespace pin and checkpoints on restart. Completion
  of a batch or service startup is not completion of the backfill or run acceptance.
- The four observed M5I contradiction misses now have genuine regression fixtures
  and versioned on-read guards; see `docs/M5I_CORRECTIONS.md`. Never treat an empty
  old queue warning list or an unknown parsed field as approval. The operator restored
  inference on October 29; health passes but three probes miss the exact model
  pin. See `docs/evidence/M5I_RECOVERY_20261029.json`. Verify effective runtime
  settings/model provenance; preserve the existing pin and do not merge vectors.

- On October 29 the operator explicitly authorized a separate namespace. The new
  12-hour run uses `data/m5i/qwen-8f1b.semantic.sqlite3`, exact pin `8f1b745674ea82993cc5211498d606a86627ecedb6776637daeaf66e42611204`,
  and `data/m5i/run-20261029-newnamespace/config.json`; its fixed deadline is
  October 30 11:20:39 UTC (07:20:39 EDT). The original sidecar, namespace and
  expired run configuration remain preserved. Do not mix or relabel vectors.
  The new run stopped successfully at that deadline and its units are disabled.
  Inspect `docs/M5I_RUN_20261029_RESULTS.md` before operational work: 114,413
  eligible definitions remained unindexed at shutdown. The four subsequent keyword
  mismatch patterns now have v2 guards; bounded retrieval profiling measured a
  16% improvement with unchanged output. See `docs/M5I_CORRECTIONS_20261030.md`.
  Broader recognition, vector/query coverage and quality remain open. The 20 freshly
  checked sports candidates are UNVERIFIED; no restart or M6 is implied.

- On October 30 the operator authorized continuation after the v2 mismatch repairs.
  A new 12-hour run resumes the same `qwen-8f1b.semantic.sqlite3` index and exact pin;
  inspect `docs/M5I_RUN_20261030.md` and `data/m5i/run-20261030-resume/`.
  Its fixed deadline was October 31 12:06:39 UTC (08:06:39 EDT). Both services
  stopped and are now disabled. See `docs/M5I_RUN_20261030_RESULTS.md`: US eligible
  coverage reached 100%, Kalshi 8.61%, with 117,488 definitions still unindexed.
  Broader entity/geography/range/event-type keyword mismatches remain; empty
  conflict lists never imply approval. Preserve namespaces, deadlines and progress;
  no new run or milestone completion is implied.

- October 31 v3 guards and a conflict-count retrieval tie-break repair the four
  latest observed patterns. See `docs/M5I_COMPATIBILITY_RESULTS.md`: a 42-pair
  genuine development corpus measures indexed recall 16/19 → 18/19, with one
  187.5-day horizon exclusion retained. Unlisted pairs are UNLABELED. Ordinary
  event labels never authorize removing resolution-language/settlement warnings.
  Broader recognition and independent adjudication remain open; services stay off.

## M5L explicit research authorization — October 31

The operator subsequently authorized M5L economic research and AI throughput
benchmarking. This supersedes the earlier development stop at M5I only for that
research scope. Preserve production model/index identity, expired run configuration,
all approval/settlement/fee/clock/collateral gates and historical evidence. M5L
uses isolated benchmark/evaluation/scheduler archives; no live-money execution,
new trading credentials, automatic approvals or renewal of expired runs is allowed.
See docs/M5L_RESULTS.md and docs/M5L_OPERATIONS.md. Independent adjudication was
explicitly left pending by the operator. The proposed M5M is not an authorized run;
M6 remains unauthorized.

## M5M authorized research boundary

The operator separately authorized M5M quote-synchronization diagnostics, a bounded
60-minute read-only capture and up to five objective non-sports review packets.
See `docs/M5M_OPERATIONS.md` and `docs/M5M_REVIEW_GUIDE.md`. This supersedes the
older milestone stop only for that research scope. No M6, orders, funds, automatic
equivalence/fee approval or renewal is authorized. Preserve Qwen3-Embedding-8B
Q6_K, pooling, batch 16 and the exact production namespace. Experimental
response-only freshness metrics must never replace the existing economic gates.
Sports independent discretionary settlement remains residual-risk research,
excluded from strict arbitrage. All human review remains pending unless an actual
explicit, source-bound decision is provided.

## M5N authenticated market-data continuation

The operator requested US streaming verification and supplied an existing local
credential file for read-only use. See `docs/M5N_STREAM_RESULTS.md` and
`docs/US_WEBSOCKET.md`: the original 401 blocker is resolved, a 120-second US
capture contains 64 books, and offline replay verifies them. NFL updates were
timely in that short window; the quiet Fed snapshot remained stale. US sequence
continuity and quiet-book validity remain UNKNOWN. The separate concurrent Kalshi
capture exhausted its connection budget and is INCOMPLETE. Do not relabel these
diagnostics as economic eligibility or restart expired services. Existing keys
may sign only the fixed market-data handshake; no account/order requests,
automatic approvals, funds or M6 are authorized.

The operator then authorized one independent 15-minute comparison, quiet-feed
documentation review and a Fed-hold review packet. That run stopped at its fixed
November 1 **17:25:27 UTC** deadline. See `docs/M5N_COMPARISON_RESULTS.md`:
504/900 samples passed the isolated timestamp/depth diagnostic; all 698 US frames
and 1,363 Kalshi raw responses were verified. This is not continuous coverage or
economic eligibility. US continuity/quiet-book validity and metadata-grid
integration remain open. `docs/M5N_FED_HOLD_REVIEW.md` and its source-bound blank
worksheet leave all human decisions pending. No new run or M6 is implied.

## M5O authorized continuous conditional research

The operator explicitly requested execution of `docs/M5O.md`: one new bounded
24-hour public-data observation of 10–20 diverse pairs, including conditional
gross economics for unresolved ordinary-outcome matches. See `docs/M5O_OPERATIONS.md`
and the evolving `docs/M5O_RESULTS.md`. This supersedes prior stops only for this
research scope. CONDITIONAL results disclose exceptional-payout risks; DISCOVERY
signals are not arbitrage; STRICT still requires all source-bound approvals.
Fees/collateral/cash release remain UNKNOWN without review. All existing production
gates, model namespaces and expired runs stay preserved. No funds, orders, automatic
approvals or M6. The new run has its own fixed deadline in
`data/m5o/run-20261101/config.json`; never renew it automatically. Completion of its
budget is not completion of research acceptance or proof of profitability.

November 2: the documented optional Kalshi snapshot ladders are now supported;
see `docs/M5O_LADDER_FIX.md`. Omitted sides remain partial/empty and economically
unusable. Original M5O processes retain their launch-time code; no hot reload or
restart occurred. Four stopped sports markets subsequently finalized. Preserve
their rejected evidence and gaps; this correction does not renew the deadline.

## M5P authorized market-data quality recovery — November 3

The operator explicitly requested `docs/M5P_MARKET_DATA_QUALITY_RECOVERY.md`.
Scope: immutable M5O forensics, collection instrumentation/repairs, and one new
15-minute read-only validation of two or three freshly open, deliberately active
pairs after tests and scope disclosure. The 50% valid-sample target is an initial
engineering goal; preserve two-second gates and measure wall-clock local-state
coverage separately. Do not weaken tests to attain it. Existing model namespaces,
settlement/fee/clock/collateral approvals, capital limits and expired runs remain
preserved. No full-day run, automatic renewal, funds, orders or M6. An optional
one-hour validation is only a separate proposal after initial targets pass.
See `docs/M5P_OPERATIONS.md`, `docs/M5P_RESULTS.md` and the fixed window in
`data/m5p/validation-20261103/config.json` before any further operational work.
The run stopped at November 3 16:34:51.923924 UTC. Both audits passed, with no
early worker stops, but stream samples passed only 19.41% and full-window local
state coverage was 19.26%. The 50% target remains unmet. The 118 Senate gross
samples are conditional research, not profitability or approval. No continuation
was prepared or authorized; preserve the fixed deadline and original evidence.

### M5P cadence/recovery follow-up — November 3

The operator subsequently requested actual update-cadence screening and reduced
Kalshi recovery gaps. This authorizes the focused M5P engineering follow-up in
`docs/M5P_CADENCE_RECOVERY.md`, including short bounded read-only validation in new
archives. Preserve all old deadlines/evidence and unchanged quality/approval gates.
The opt-in in-band snapshot policy must retain sequence/source-clock validation,
raw-first requests/responses, bounded fallback and deterministic offline replay.
Cadence screening uses wall time and sample coverage; an empty shortlist is valid.
No automatic longer run, renewed service, model change, funds, orders or M6.
The follow-up stopped at November 3 23:23:32.856342 UTC. Six worker audits passed,
with no early stops; in-band recovery reduced message timeouts 13 → 0 and all 67
requested snapshots returned. The five-minute screen selected Senate (82.09% wall)
and marginal House (53.18%), rejecting Fed (3.25%). See the result document and
`data/m5p/cadence-recovery/`. Shortlist validity is historical, not a standing
activity guarantee; held-out/sustained coverage remains open. No further run is
implied, and all old services remain off.

### M5P independent holdout — explicitly authorized November 3

The operator requested execution of the proposed new-collector validation. See
`docs/M5P_HOLDOUT_VALIDATION.md` and the preregistered
`data/m5p/holdout-20261103/plan.json`: refresh and screen the shortlist, freeze two
or three eligible pairs, then one new 900-second read-only holdout with unchanged
collector settings and 50% per-pair sample/wall targets plus 50% wall time in each
half. Keep failed pairs in the report. Do not extend fixed deadlines, hot-reload,
start services, infer approvals or launch an optional hour automatically.
The holdout stopped at **November 4 00:04:13.158062 UTC** (November 3 19:04:13 EST).
Both audits passed with no early stops or timeout failures; all 46 requested Kalshi
snapshots returned. Senate passed (82.15% wall / 81.56% samples); House failed
(49.94% samples and 47.51% second-half wall, despite 50.14% overall wall). The
cohort target remains unmet. Preserve the frozen scope/deadline and failed result;
no optional hour or renewal was prepared. Further activity is not implied.

### M5P stronger second-candidate screen — authorized November 4 UTC

The operator requested screening for a stronger second candidate. See
`docs/M5P_SECOND_CANDIDATE.md` and `data/m5p/second-candidate-20261104/plan.json`:
four proposed distinct election races, fresh definitions/depth, at most two
five-minute discovery cohorts and one five-minute confirmation for the best
qualifier with Senate reference. The stronger nomination requires 60% sample,
full-wall and each-half wall coverage without weakening the existing 50% target
or any two-second/approval gates. Retain exclusions and failures. No inference,
index/model writes, service renewal, 15-minute holdout, hour, funds or M6.
The screen ended at **November 4 01:10:22.063368 UTC**. Neither challenger met
the stronger rule: Michigan second-half wall 57.57%; Georgia Governor overall
wall 59.38% and second-half 57.82%. All three workers/audits passed, all 21
requested snapshots returned, and the original 50% screen passed. No confirmation
was launched. Local Kalshi pending barriers accumulated 67.12s for Michigan and
69.38s for Senate despite individual receipt-to-availability times below 90ms;
profile persistence/validation before attributing all losses to quiet venues.
No inference was requested. Preserve these failures and the fixed deadline;
no new capture or completion is implied.

### M5P persistence/validation profile — authorized November 4 UTC

The operator requested profiling while retaining integrity checks. See
`docs/M5P_PERSISTENCE_PROFILE.md` and `data/m5p/persistence-profile-20261104/`.
The bounded offline task is complete: 18 plain/profiled executions and three
CPU probes pass exact normalized parity; 574 tests pass. Source archives remain
unchanged. Commits account for 60–64% of serial-prefix capture wall time; validation
for 20–24%. No collector transaction/durability/gate change or live run occurred.
Combining final validation and normalized persistence into one atomic commit is
a proposed next optimization, requiring failure/reader-visibility tests and
same-source before/after measurements. No live coverage gain or renewal is implied.


### M5P atomic final commit — authorized November 4 UTC

The operator authorized testing one atomic final validation-status/normalized-book
commit. See `docs/M5P_ATOMIC_FINAL_COMMIT.md` and
`data/m5p/atomic-final-20261104/`. Offline acceptance passed: 581 tests, independent
reader/failure/process-death checks and 36 before/after executions with exact
six-table/intermediate-book parity. Final commits halve; median serial-prefix
plain times fall 5.29–13.25%. Raw and pending commits, WAL/FULL, all integrity and
approval gates remain intact. This is not measured live coverage improvement.
No capture, service renewal, expired-deadline change, model/index change, funds,
orders or M6 is authorized. Broader M5P quality acceptance remains open.
