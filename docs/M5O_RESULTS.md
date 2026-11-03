# M5O — Continuous cross-market economic research

**Status: DEADLINE_REACHED. Capture status is separate from research acceptance.**

Fixed window: 2026-11-01T19:43:05.523526+00:00 through 2026-11-02T19:43:05.523526+00:00.
Report generated: 2026-11-02T19:43:08.617728+00:00. No orders, funds or approvals.

The run uses independent Kalshi clocked-stream receivers and public US REST full snapshots. US source/receipt ages and both cross-venue skews must be within two seconds; existing metadata, price/quantity grid, sequence and market-state checks also apply. Cached/quiet books remain rejected. US WebSocket continuity is not promoted into eligibility.

| Pair | Class / origin | Worker state | Samples | Valid data | Conditional gross samples |
| --- | --- | --- | ---: | ---: | ---: |
| nba-brooklyn | CONDITIONAL / DETERMINISTIC | CONSECUTIVE_FAILURE_LIMIT | 3326 | 44 | 44 |
| nba-boston | CONDITIONAL / DETERMINISTIC | CONSECUTIVE_FAILURE_LIMIT | 2092 | 33 | 33 |
| nba-toronto | CONDITIONAL / DETERMINISTIC | CONSECUTIVE_FAILURE_LIMIT | 5952 | 51 | 51 |
| nfl-arizona | CONDITIONAL / DETERMINISTIC | CONSECUTIVE_FAILURE_LIMIT | 1217 | 49 | 49 |
| nfl-baltimore | CONDITIONAL / DETERMINISTIC | CONSECUTIVE_FAILURE_LIMIT | 750 | 5 | 5 |
| nfl-chicago | CONDITIONAL / DETERMINISTIC | DEADLINE_REACHED | 17132 | 137 | 137 |
| fed-hold | CONDITIONAL / DETERMINISTIC | DEADLINE_REACHED | 17218 | 6 | 6 |
| payrolls | CONDITIONAL / DETERMINISTIC | DEADLINE_REACHED | 17231 | 7 | 7 |
| unemployment | CONDITIONAL / DETERMINISTIC | DEADLINE_REACHED | 17232 | 9 | 9 |
| cpi | CONDITIONAL / DETERMINISTIC | DEADLINE_REACHED | 17224 | 23 | 23 |
| gas-high | DISCOVERY / DETERMINISTIC | DEADLINE_REACHED | 17219 | 21 | 0 |

Observed pair samples: **116593** / **190080** planned over the full window; valid data samples: **385**. Startup, poll errors, processing/audit gaps and early worker endings remain in the planned denominator. These sample counts are not continuously verified market time.

Segment audits: 653 passed, 0 failed. Running segments are pending. Failed-audit observations cannot support final economic findings.

STRICT pairs: **0**. Conditional and discovery labels are assistant research assessments; operator adjudication remains pending. Definitions changing during the run downgrade the affected observation to DISCOVERY. Discovery signals have no arbitrage calculation.

| Pair / quote budget | Positive gross samples | Sample clusters | Cluster span (s) | Max gross edge ($) | Max displayed quantity under budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| nba-brooklyn / $100 | 1 | 1 | 0.000 | 1.010100 | 101.01 |
| nba-brooklyn / $25 | 1 | 1 | 0.000 | 0.252500 | 25.25 |
| nba-brooklyn / $5 | 1 | 1 | 0.000 | 0.050500 | 5.05 |
| nba-brooklyn / $500 | 1 | 1 | 0.000 | 5.050500 | 505.05 |
| nba-boston / $100 | 0 | 0 | 0.000 | 0.000000 | 100.00 |
| nba-boston / $25 | 0 | 0 | 0.000 | 0.000000 | 25.00 |
| nba-boston / $5 | 0 | 0 | 0.000 | 0.000000 | 5.00 |
| nba-boston / $500 | 0 | 0 | 0.000 | 0.000000 | 500.00 |
| nba-toronto / $100 | 0 | 0 | 0.000 | 0.000000 | 100.00 |
| nba-toronto / $25 | 0 | 0 | 0.000 | 0.000000 | 25.00 |
| nba-toronto / $5 | 0 | 0 | 0.000 | 0.000000 | 5.00 |
| nba-toronto / $500 | 0 | 0 | 0.000 | 0.000000 | 500.00 |
| nfl-arizona / $100 | 0 | 0 | 0.000 | -0.249375 | 99.75 |
| nfl-arizona / $25 | 0 | 0 | 0.000 | -0.062325 | 24.93 |
| nfl-arizona / $5 | 0 | 0 | 0.000 | -0.012450 | 4.98 |
| nfl-arizona / $500 | 0 | 0 | 0.000 | -1.246875 | 498.75 |
| nfl-baltimore / $100 | 0 | 0 | 0.000 | -0.497500 | 99.50 |
| nfl-baltimore / $25 | 0 | 0 | 0.000 | -0.124350 | 24.87 |
| nfl-baltimore / $5 | 0 | 0 | 0.000 | -0.024850 | 4.97 |
| nfl-baltimore / $500 | 0 | 0 | 0.000 | -2.487550 | 497.51 |
| nfl-chicago / $100 | 0 | 0 | 0.000 | 0.000000 | 100.00 |
| nfl-chicago / $25 | 0 | 0 | 0.000 | 0.000000 | 25.00 |
| nfl-chicago / $5 | 0 | 0 | 0.000 | 0.000000 | 5.00 |
| nfl-chicago / $500 | 0 | 0 | 0.000 | 0.000000 | 500.00 |
| fed-hold / $100 | 0 | 0 | 0.000 | -0.990000 | 99.00 |
| fed-hold / $25 | 0 | 0 | 0.000 | -0.247500 | 24.75 |
| fed-hold / $5 | 0 | 0 | 0.000 | -0.049500 | 4.95 |
| fed-hold / $500 | 0 | 0 | 0.000 | -4.950400 | 495.04 |
| payrolls / $100 | 0 | 0 | 0.000 | -1.960600 | 98.03 |
| payrolls / $25 | 0 | 0 | 0.000 | -0.490000 | 24.50 |
| payrolls / $5 | 0 | 0 | 0.000 | -0.098000 | 4.90 |
| payrolls / $500 | 0 | 0 | 0.000 | -14.08930000 | 485.91 |
| unemployment / $100 | 0 | 0 | 0.000 | -1.31360000 | 98.68 |
| unemployment / $25 | 0 | 0 | 0.000 | -0.247500 | 24.75 |
| unemployment / $5 | 0 | 0 | 0.000 | -0.049500 | 4.95 |
| unemployment / $500 | 0 | 0 | 0.000 | -70.56670000 | 429.43 |
| cpi / $100 | 0 | 0 | 0.000 | -2.067900 | 97.93 |
| cpi / $25 | 0 | 0 | 0.000 | -0.441000 | 24.55 |
| cpi / $5 | 0 | 0 | 0.000 | -0.049500 | 4.95 |
| cpi / $500 | 0 | 0 | 0.000 | -21.30570000 | 478.69 |
| gas-high / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| gas-high / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| gas-high / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| gas-high / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |

Budgets above are combined **quote costs before unknown fees/collateral**. Depth is displayed, not a fill guarantee. The evaluated cash-long direction is Kalshi NO + US YES; reverse US synthetic NO remains unsupported. Gross outcomes assume matching ordinary settlement. Net fee-adjusted returns, all-in capital, cash release and settlement delay remain UNKNOWN. Per-venue quote funding, exceptional zero-payout loss and explicitly hypothetical 1/2/5-cent combined fee sensitivities are in each observations.jsonl row.

Clusters group consecutive positive five-second samples with gaps at most seven seconds; their spans are **not continuously verified opportunity durations**. Rejections, gaps and segment changes break clusters. Zero positive samples with no valid comparisons cannot establish absence of opportunities. Fee sensitivity never creates an approved fee profile.

Risks: independent sports discretionary payouts; Fed cancellation/rescheduling and rate-range interpretation; labor/CPI revisions and fallback dates; gas observation-window mismatch; non-atomic fills, uncertain account costs/collateral and cash-release timing. All can erase gross discrepancies; selected legs can conditionally both pay zero. See candidate source reviews.

AI contribution: 0 AI-only pairs in this purposive sample. With no AI-only selected pairs, incremental semantic economic value is NOT ESTIMABLE; this is not evidence that AI has no value. See the source-bound historical ablation in config.json and docs/evidence/M5O_AI_ABLATION.json. Its additional ranked pairs carried proposition/date conflicts and were excluded. This measures bounded ranking changes, not representative recall or current-market AI yield. The index/model were not modified or reindexed.

Blockers: US caching/source freshness, quiet Kalshi reconnect gaps, unresolved exceptional payouts, unreviewed fees and collateral, and unknown actual fills. Recommended next step: complete and audit this fixed window, then prioritize any persistent gross discrepancy for source-bound fee/mechanics/settlement review. No M6 or trading authorization.

Evidence: `config.json`, `report.json`, per-pair status, per-segment raw SQLite archives, HTTP/WS timing journals, `observations.jsonl`, clock checks and offline `audit.json` files. Full raw bytes precede normalization. See docs/M5O_OPERATIONS.md for commands and limits.
