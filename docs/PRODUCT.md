# Product specification

## Objective

Discover, record, and evaluate potential *fully hedged* binary-event opportunities between U.S.-accessible prediction exchanges, initially **Kalshi** and **Polymarket US** (distinct from international polymarket.com). Learn whether opportunities are real, sufficiently liquid, short-lived, and worthwhile after fees, before connecting funds.

## Intended phases

1. Read-only market catalogues and raw feeds.
2. Human-reviewed pair registry with exact settlement rule evidence.
3. Full depth-normalized quotes and synchronized timestamps.
4. Depth- and fees-aware scan, deterministic simulation, 30-day reporting.
5. Separately approved micro-scale trading prototype **only after** detailed risk/security review.

## Acceptance for research MVP

- Poll both US venues and preserve raw responses, provider timestamp if present, retrieval timestamp, endpoint and source IDs.
- Normalize binary contract model; collect official resolution texts/links and relevant deadlines.
- Compare only explicitly approved equivalent event pairs. Never fuzzy-match and trade automatically.
- Compute feasible hedge size from both ask ladders, accounting for minimum increments, fees, and a slippage/staleness reserve.
- Rank opportunities by **net expected contractual settlement gain**, capital locked, and duration; archive rejected candidates with reason.
- Provide reproducible 30-day simulation with uncertainty: hypothetical fills are **not** historical verified fills.
- Continue after intermittent API failures, within configured resource and rate budgets, and alert on data gaps.

## Out of scope for MVP

Trading, authentication/signing, withdrawals/deposits, margin, automated tax filing, multicountry availability, speculative directional positions, market-making, news prediction, and guaranteed return projections.

## Success metric

Not annualized hypothetical ROI. Track number of verified pairs, percent of observations with simultaneous fresh quotes, executable *after-fee* edge and size, quote longevity, estimated working-capital days, and scenarios for one-leg failure. If the 30-day data does not support a durable net edge, stop before live trading.
