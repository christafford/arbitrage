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
