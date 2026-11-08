# M5Q — Economic Signal Validation

Read AGENTS.md, docs/M5P_RESULTS.md, docs/M5P_HOLDOUT_VALIDATION.md, docs/M5P_ATOMIC_FINAL_COMMIT.md, docs/M5P_ATOMIC_LIVE_VALIDATION.md, and the existing economics, market-data-quality, and settlement-review implementations.

M5P has demonstrated that strict, two-second-valid observations are achievable for selected active markets. Atomic SQLite finalization has passed offline integrity and performance tests.

We now need to determine whether those observations reveal genuine economic opportunities.

Do not implement live trading, modify the production embedding model, weaken safety gates, or undertake unrelated infrastructure optimization.

## Phase A — Offline economic reconstruction

Using existing immutable M5O/M5P observation archives:

1. Identify every observation passing the existing strict market-data checks.
2. Reconstruct both executable trading directions where supported by the current mechanics model.
3. Calculate gross edge, available depth and hypothetical capital requirements.
4. Preserve pair classifications: STRICT, CONDITIONAL and DISCOVERY.
5. Never report unapproved contracts as guaranteed arbitrage.
6. Identify positive gross observations and group consecutive observations into opportunity episodes using source-state identities and actual observation gaps.
7. Avoid counting repeated samples of the same unchanged order-book state as independent opportunities.
8. Produce an operator-readable ranking by available gross edge, liquidity, observation duration and settlement uncertainty.
9. Where historical fee applicability is unknown, explicitly mark net profitability UNKNOWN.

## Phase B — One-pair live observation

Select one currently open, active pair with strong recent data quality and supported trading-side mechanics.

Use the existing five-minute screening and independent holdout evidence as selection guidance, but do not require two simultaneous qualifying pairs.

Perform fresh instrument, depth, status and settlement-definition checks before each authorized observation.

Run a bounded 15-minute read-only capture with unchanged strict source/receipt/skew gates.

Preserve raw-first storage, WAL/FULL, atomic finalization, provenance and replay integrity.

Report both sample coverage and valid wall-clock coverage.

Do not automatically extend the capture.

## Phase C — Economic measurements

For the selected pair, evaluate $5, $25, $100 and $500 combined-capital scenarios.

Calculate:

- Actual displayed executable prices and quantities.
- Gross spreads.
- Fees using independently reviewed fee profiles, or UNKNOWN.
- Required collateral and buying power.
- Maximum matched trade quantity.
- Indicative net return where determinable.
- Observation duration and source-state validity.
- Exposure under incomplete or unmatched fills.
- Time until expected settlement and capital release.

Distinguish market quotes from executable fills. No actual execution is authorized.

## Phase D — Venue continuity investigation

Investigate current official Polymarket US streaming documentation for sequence, liveness, recovery, snapshots and quote-state guarantees.

Determine whether unchanged resting books can be treated as continuously validated under a documented protocol.

Implement diagnostic instrumentation if justified, but retain the existing strict two-second gate.

Any alternative freshness model must be a separate non-actionable research policy and must not alter historical strict results.

## Phase E — Results

Create docs/M5Q_RESULTS.md with:

1. Complete offline economic reconstruction.
2. Ranked potential opportunities.
3. Fifteen-minute live observation results.
4. Fee-adjusted economics where supported.
5. Differences between observed depth and hypothetical fills.
6. Source-backed settlement risks.
7. Data-quality and continuity findings.
8. Recommendation on whether further arbitrage research is economically justified.

Run all tests and verify replay integrity.

If no positive, reproducible economic opportunities are found, report this explicitly.

Do not place orders, spend funds, approve contracts automatically, or proceed to M6.
