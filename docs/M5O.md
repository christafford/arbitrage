# M5O — Continuous Cross-Market Economic Research

Read AGENTS.md, the M5M and M5N results, the latest source-bound settlement reviews, and the existing economic research implementation.

Our goal is to determine whether cross-exchange pricing discrepancies are frequent and large enough to justify further investment in this strategy.

Do not implement live trading or authorize any order placement.

## 1. Research classification

Maintain three separate classes:

- STRICT: All material payout scenarios, fees, trade mechanics, and required approvals have been verified.
- CONDITIONAL: Normal settlement outcomes are compatible, but exceptional outcomes or other risks remain.
- DISCOVERY: Related markets whose settlement relationships have not been established.

Only STRICT observations may be reported as eligible settlement arbitrage. CONDITIONAL results must explicitly disclose residual risks. DISCOVERY signals must not be presented as arbitrage opportunities.

## 2. Candidate selection

Select 10–20 diverse currently open same-event pairs from the existing discovery index.

Prefer near-term events, measurable liquidity, and complete market definitions.

Do not discard unresolved Fed or sports pairs; use them for research where appropriate.

Avoid filling the sample with multiple threshold variations of one event.

## 3. Read-only observation

Run a bounded 24-hour observation using public market-data interfaces.

Capture and persist:
- Both venues' timestamped order books and source provenance.
- Actual executable bids, asks, and available depth.
- Local reception and exchange timestamps.
- Feed continuity, polling latency, and quote freshness.
- Both potential hedge directions, where their mechanics are modeled.
- Fee-adjusted indicative edge and capital requirements.
- Observation duration and rejection reasons.

Keep strict freshness and market-data quality rules intact. Additional diagnostic freshness models must be separately labeled and must not authorize economics.

## 4. Conditional economics

Evaluate opportunities at $5, $25, $100, and $500 combined exposure.

Distinguish executable displayed depth from assumed fills.

Calculate:
- Indicative gross edge.
- Fee-adjusted edge when supported by reviewed fees.
- Capital required per venue.
- Maximum feasible matched quantity.
- Estimated settlement delay.
- Potential loss under known exceptional settlement scenarios.
- Number and duration of positive conditional opportunities.

Where exact fee or collateral rules are unknown, report bounds or UNKNOWN rather than inventing a number.

## 5. AI discovery contribution

Track whether each observed pair originated from deterministic matching or semantic AI retrieval.

Measure whether AI-only candidates produced additional credible economic opportunities.

Do not modify the current embedding model or reindex the entire catalogue.

## 6. Results

Create docs/M5O_RESULTS.md including:

- Valid cross-market observation coverage.
- Number of strict, conditional, and discovery-only pairs.
- Positive indicative discrepancies and their durations.
- Executable depth at each capital level.
- Known settlement and execution risks.
- Sensitivity to fees and quote staleness.
- Incremental value from semantic retrieval.
- Most important blockers to real profitability.
- Recommended next milestone.

Run tests, archive evidence, and preserve existing risk protections.

If no meaningful positive opportunities exist, report that directly.

Do not place orders, spend deposited funds, or automatically approve unresolved settlement reviews.

