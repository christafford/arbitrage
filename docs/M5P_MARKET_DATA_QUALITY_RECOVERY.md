# M5P — Market Data Quality Recovery

Read AGENTS.md, docs/M5O_RESULTS.md, docs/M5O_OPERATIONS.md, docs/M5O_LADDER_FIX.md, and all supporting M5O evidence.

M5O collected 116,593 samples but only 385 passed all data-quality checks. Five workers stopped early. One Brooklyn observation had a roughly 1.01% gross indicative edge, without verified persistence or net profitability.

Our immediate priority is restoring reliable cross-venue observation coverage.

Do not implement live trading, change the embedding model, or conduct another full-day capture.

## Phase A — Offline evidence analysis

Using the immutable M5O archives:

1. Reconstruct exact rejection counts by pair, venue, and reason.
2. Separate primary blocking reasons from additional simultaneous failures.
3. Explain the five early worker stops, including the contribution of omitted Kalshi ladders and market finalization.
4. Verify the completed Kalshi ladder correction against archived examples.
5. Reconstruct the single positive Brooklyn observation from original raw market messages.
6. Show the preceding and following book states, quote timestamps, source integrity, actual price levels, and available quantities.
7. Determine whether the Brooklyn signal is supported by valid, contemporaneous market states.
8. Identify the three largest independently addressable causes of lost coverage.

Never modify the historical archives or retroactively upgrade rejected observations.

If the actual raw archives are unavailable, report this limitation and request their exact locations rather than fabricating a forensic breakdown.

## Phase B — Collection quality

Investigate:

- Polymarket US REST snapshot caching and response freshness.
- HTTP response timing and source timestamps.
- Polymarket US streaming feasibility and continuity semantics.
- Kalshi WebSocket sequence integrity and reconnect behavior.
- Distinguishing legitimately empty order books from malformed responses.
- Quiet but continuously validated books versus disconnected stale books.
- Exchange-time and local-clock synchronization.

Implement instrumentation that separately tracks:

1. Last order-book mutation time.
2. Last verified snapshot time.
3. Last authenticated and validated stream activity.
4. Last loss of continuity.
5. Local receipt time.
6. Source timestamp.
7. Request/response interval for REST calls.

Preserve the existing two-second strict quality requirements.

If a state-continuity-based freshness policy is warranted, implement it only as a separate experimental research policy, with explicit limitations and evidence. Do not allow that policy to authorize trading or qualify unresolved settlement contracts as strict arbitrage.

## Phase C — Bounded validation

After repairs and passing tests:

1. Select two or three currently active and liquid markets.
2. Confirm the chosen instruments are still open immediately before capture.
3. Run a newly authorized 15-minute read-only observation, after showing the intended scope and commands to the operator.
4. Compare valid observation coverage, error rates, quote age, and cross-venue skew with M5O using unchanged strict criteria.
5. If the initial capture meets documented coverage targets, prepare a separate optional one-hour validation.
6. Preserve exact source data, replay evidence, and rejection reasons.

Do not automatically launch or renew long-running services.

## Phase D — Deliverables

Create:

- docs/M5P_RESULTS.md
- A per-pair rejection breakdown.
- A root-cause analysis of the five worker stops.
- A Brooklyn observation reconstruction.
- Before/after strict-quality metrics.
- Experimental freshness-policy comparisons, if implemented.
- Specific remaining blockers and a prioritized recommendation.

Run all tests and archive their output.

Success is demonstrating reliable observable market states, not producing profitable-looking signals.

No real-money orders, automated pair approvals, or changes to existing capital safeguards.

