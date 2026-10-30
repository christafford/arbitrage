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
  eligible definitions remained unindexed at shutdown; additional keyword
  proposition mismatches and retrieval overhead remain open. The 20 freshly
  checked sports candidates are UNVERIFIED; no restart or M6 is implied.
