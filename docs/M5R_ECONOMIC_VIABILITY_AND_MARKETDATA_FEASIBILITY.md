# M5R — Economic Viability and Market-Data Feasibility

Read AGENTS.md, docs/M5Q_RESULTS.md, docs/M5Q_CONTINUITY.md, docs/M5Q_OPERATIONS.md, docs/evidence/M5Q_ECONOMICS.json, and all existing fee, collateral, and settlement-review documentation.

M5Q established 196 gross-positive operational observations, with repeated historical Senate price discrepancies, but no verified profitable net arbitrage.

The objective is to determine whether this strategy can reasonably become profitable before investing in more infrastructure.

No real-money trading is authorized.

## A — Historical fee-adjusted economics

1. Identify the strongest historical gross-positive series, especially November 3 Senate control.
2. Retrieve and archive authoritative historical fee schedules, effective dates, series-specific coefficients, and relevant fee exceptions.
3. Calculate actual fees where applicability is independently established.
4. Where historical fees cannot be confirmed, calculate explicit break-even fee bounds rather than inventing a result.
5. Report net profit sensitivity at $5, $25, $100, $500 and $3,000 capital levels.
6. Consider fee rounding, fill fragmentation, available depth, and per-venue capital limits.
7. Preserve unresolved settlement and execution risks. Never label an observation net-profitable unless the fees are established.

## B — Market-data feasibility

Using existing M5Q raw archives:

1. Decompose freshness failures into Kalshi source age, Polymarket US source age, cross-venue skew, receipt latency, metadata validity, and continuity losses.
2. Identify the primary cause of lost valid wall-clock coverage for each tested pair.
3. Investigate whether the current documented Polymarket US WebSocket or gRPC interfaces provide any stronger market-state continuity guarantees.
4. Do not infer quote validity from transport heartbeats.
5. Test any proposed freshness changes in isolated offline diagnostic mode only.
6. Preserve current strict two-second results and eligibility rules.
7. Determine whether better event selection or changes to data collection can realistically improve observation quality.
8. Avoid another lengthy capture until the technical findings support a specific test.

## C — Capital efficiency

Using historical and current verified data:

1. Model actual split capital requirements for both exchanges.
2. Estimate maximum matched quantities at realistic capital allocations.
3. Distinguish gross spread, net edge, and potential one-leg downside.
4. Estimate capital lockup where source-backed settlement dates are known.
5. Do not treat administrative end dates as guaranteed cash-release times.
6. Assess whether $3,000 could be efficiently deployed given observed depth and opportunity duration.
7. Do not extrapolate repeated quote samples into independent profitable trade cycles.

## D — Candidate selection strategy

Investigate how to prioritize contracts that combine:

- Compatible ordinary outcomes.
- Minimal exceptional-settlement differences.
- Recent verified depth and trading activity.
- High observed fresh-book coverage.
- Short expected capital lockup.
- Reasonable fee-adjusted spreads.

Compare deterministic and AI-discovered candidates, but do not change the production embedding model or initiate broad reindexing.

## E — Decision report

Create docs/M5R_RESULTS.md containing:

1. Historical fee-adjusted economic findings or explicit unknowns.
2. Break-even fee thresholds.
3. Primary causes of quote-quality failures.
4. Assessment of alternative market-data interfaces.
5. Realistic $3,000 deployment constraints.
6. The three strongest candidate event classes for further research.
7. A recommendation to continue, pivot, or pause development, justified by measured evidence.

Run the test suite, preserve archived data, and document all assumptions.

Do not place trades, renew old run authorizations, automatically approve contracts, or implement live execution.
