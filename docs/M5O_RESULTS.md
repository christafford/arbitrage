# M5O — Continuous cross-market economic research

**Status: RUNNING. Capture status is separate from research acceptance.**

Fixed window: 2026-11-01T19:43:05.523526+00:00 through 2026-11-02T19:43:05.523526+00:00.
Report generated: 2026-11-01T19:44:09.072888+00:00. No orders, funds or approvals.

The run uses independent Kalshi clocked-stream receivers and public US REST full snapshots. US source/receipt ages and both cross-venue skews must be within two seconds; existing metadata, price/quantity grid, sequence and market-state checks also apply. Cached/quiet books remain rejected. US WebSocket continuity is not promoted into eligibility.

| Pair | Class / origin | Worker state | Samples | Valid data | Conditional gross samples |
| --- | --- | --- | ---: | ---: | ---: |
| nba-brooklyn | CONDITIONAL / DETERMINISTIC | RUNNING | 13 | 0 | 0 |
| nba-boston | CONDITIONAL / DETERMINISTIC | RUNNING | 13 | 0 | 0 |
| nba-toronto | CONDITIONAL / DETERMINISTIC | RUNNING | 13 | 0 | 0 |
| nfl-arizona | CONDITIONAL / DETERMINISTIC | RUNNING | 12 | 0 | 0 |
| nfl-baltimore | CONDITIONAL / DETERMINISTIC | RUNNING | 12 | 0 | 0 |
| nfl-chicago | CONDITIONAL / DETERMINISTIC | RUNNING | 13 | 0 | 0 |
| fed-hold | CONDITIONAL / DETERMINISTIC | RUNNING | 12 | 0 | 0 |
| payrolls | CONDITIONAL / DETERMINISTIC | RUNNING | 12 | 0 | 0 |
| unemployment | CONDITIONAL / DETERMINISTIC | RUNNING | 12 | 0 | 0 |
| cpi | CONDITIONAL / DETERMINISTIC | RUNNING | 12 | 0 | 0 |
| gas-high | DISCOVERY / DETERMINISTIC | RUNNING | 12 | 0 | 0 |

Observed pair samples: **136** / **190080** planned over the full window; valid data samples: **0**. Startup, poll errors, processing/audit gaps and early worker endings remain in the planned denominator. These sample counts are not continuously verified market time.

Segment audits: 0 passed, 0 failed. Running segments are pending. Failed-audit observations cannot support final economic findings.

STRICT pairs: **0**. Conditional and discovery labels are assistant research assessments; operator adjudication remains pending. Definitions changing during the run downgrade the affected observation to DISCOVERY. Discovery signals have no arbitrage calculation.

| Pair / quote budget | Positive gross samples | Sample clusters | Cluster span (s) | Max gross edge ($) | Max displayed quantity under budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| nba-brooklyn / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-brooklyn / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-brooklyn / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-brooklyn / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-boston / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-boston / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-boston / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-boston / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-toronto / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-toronto / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-toronto / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nba-toronto / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-arizona / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-arizona / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-arizona / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-arizona / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-baltimore / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-baltimore / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-baltimore / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-baltimore / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-chicago / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-chicago / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-chicago / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| nfl-chicago / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| fed-hold / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| fed-hold / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| fed-hold / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| fed-hold / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| payrolls / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| payrolls / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| payrolls / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| payrolls / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| unemployment / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| unemployment / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| unemployment / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| unemployment / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| cpi / $100 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| cpi / $25 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| cpi / $5 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
| cpi / $500 | 0 | 0 | 0.000 | UNKNOWN | UNKNOWN |
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
