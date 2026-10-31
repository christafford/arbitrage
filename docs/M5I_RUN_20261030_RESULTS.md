# M5I October 30–31 run — final audit

**The bounded run stopped; full backfill and matching-quality acceptance remain
incomplete.** Collection stopped at its October 31 **08:06:39 EDT / 12:06:39 UTC**
deadline. The semantic supervisor finished at 08:07:09 EDT after its 30-second
child-cleanup allowance. Both exited 0 and are now inactive and disabled.
No new run was started. [Exact audit evidence](evidence/M5I_RUN_20261030_FINAL.json).

**Follow-up:** [v3 proposition compatibility and error evaluation](M5I_COMPATIBILITY_RESULTS.md)
repair the four observed patterns below. Original run/queue measurements remain
historical; broader recognition and quality acceptance remain incomplete.

## Coverage at the deadline

| Venue | Eligible definitions | Indexed | Coverage | Unindexed backlog |
| --- | ---: | ---: | ---: | ---: |
| Kalshi | 128,560 | 11,072 | 8.61% | 117,488 |
| Polymarket US | 9,138 | 9,138 | 100% | 0 |
| Total | 137,698 | 20,210 | 14.68% | 117,488 |

These counts were recomputed read-only at the fixed deadline after shutdown.
All **521,322 archived heads** were synchronized (335,019 Kalshi, 186,303 US),
with zero unsynced heads. Metadata, eligible definitions and cached vectors are
separate denominators. Category/deadline breakdowns, including UNKNOWN, are in
linked evidence; administrative deadlines do not establish cash availability.

The existing namespace grew from **12,880 to 23,978 stored vectors**, a net
**11,098** increase: 32 startup validation vectors, 10,986 from completed worker
reports, and 80 committed by the interrupted final batch. Vectors for definitions
that closed or changed remain retained; they do not inflate eligible coverage.
The original sidecar and expired run configuration/checkpoint hashes are unchanged.
The exact `8f1b7456…11204` pin remains isolated; no vectors were merged or relabeled.

At the preceding run's shutdown, Kalshi was 5,680/117,298 and US 6,277/9,072.
The current catalogue is larger and definitions have changed/expired, so the
backlog rose from 114,413 to 117,488 despite successful indexing. These are two
separate time-based snapshots, not a fixed-corpus benchmark.

## Collection and runtime

| Round | Kalshi run / unique records | US run / unique records |
| --- | --- | --- |
| 1 | 36 / 170,791 | 37 / 90,515 |
| 2 | 38 / 178,732 | 39 / 84,702 |

All four traversals reached terminal pagination. Counts across rounds are not
summed as distinct markets. There were 116 bounded metadata-sync invocations.

All **51 completed inference batches returned READY**, using 892 HTTP requests
and reporting 7,408 Kalshi plus 3,578 US definitions. Their combined throughput
was **0.345 definitions/second** including transport/probes/index work; no AI
fallback or model-pin mismatch was reported. The final invocation did not emit a
completed report: the fixed deadline interrupted it, and its committed 80 vectors
are included only from the persistent index count. This was a bounded shutdown,
not an additional completed batch. No subsequent work was scheduled.

Completed command time: inference **8.85 hours**, retrieval **1.03 hours**, metadata
sync **0.89 hours**, explicit coverage **27.7 seconds**. The preceding run spent
3.60 hours in retrieval for 33 windows; this run completed 51 windows. Different
catalogue sizes/query mixes/cache conditions prevent a controlled speedup claim;
the [controlled 16% measurement](M5I_CORRECTIONS_20261030.md) remains separate.
Duplicate per-batch coverage scans are absent; coverage is included in retrieval.

## Retrieval and unresolved quality

The run executed **12,655 query visits** across 51 reports; visits can repeat.
One report reached the end of the eligible generic query ordering at 04:16:58 UTC.
The catalogue later refreshed, and the final window was incomplete, so this does
not establish complete traversal of the final catalogue. The final window had
239 saturated buckets out of 250 total query visits, with a 256-candidate cap.
All saved retrieval reports had zero vector validation failures. Approximate
candidate truncation and remaining Kalshi coverage still limit recall.

The final 100 distinct events comprise **54 deterministic sports identities and
46 keyword leads; none has vector similarity evidence**. During earlier windows,
22 unique pairs carried vector evidence: 21 had a conflict warning in their latest
saved occurrence and the remaining pair had score zero. These have not been
independently adjudicated. No incremental semantic-quality gain is established;
this audit does not measure production Recall@20/@100 or precision.
[Historical vector leads](evidence/M5I_RUN_20261030_VECTOR_CANDIDATES.json).

The final keyword queue still contains obvious proposition mismatches with empty
`known_contradictions`, including:

- GDP growth **0.1–0.5%** versus **above 2.2%**: the range was left unknown.
- **California** gas prices below $4 versus the **US national** average below $4.
- A Spotify most-streamed album versus a **Grammy Album of the Year winner**.
- **Keiko Fujimori leaving Peru's presidency** versus **Volodymyr Zelenskyy leaving
  Ukraine's presidency**, with different dates and announcement/effective rules.

[Exact archived texts and existing warnings](evidence/M5I_RUN_20261030_KEYWORD_REVIEW.json)
are preserved. The v2 fixes remain in place; they do not cover these broader
entity, geography, range and event-type gaps. An empty warning list is not approval.
Next priority is broader proposition compatibility and a labeled retrieval audit
that measures false positives and false negatives, before treating further
backfill as evidence of better matching. No new guard implementation or run was
started during this audit.

## Twenty freshly checked events for operator review

Fresh public captures confirmed availability and matching ordinary sports identity
for **20 distinct events**, archiving **60 responses** in the isolated
`data/m5i/run-20261030-resume/final/live-review.sqlite3`. Source archive/index were
opened read-only for the audit. Capture times and exact source hashes are in the
[live evidence](evidence/M5I_RUN_20261030_LIVE_REVIEW.json). Raw responses were captured between **2026-10-31T14:14:10.499714+00:00** and **2026-10-31T14:14:49.660789+00:00**.
Availability means at capture time, not an executable quote. The table selects the earliest scheduled
supported events from the final saved queue; no economic/liquidity ranking is claimed.

Every row was retrieved by **league, participants, scheduled rule date and selected
winner**. Every row remains **UNVERIFIED**. Common unresolved issues are exceptional
fair-price settlements, postponement/cancellation/forfeit handling, source revisions,
administrative cutoff and cash-availability differences. Books/liquidity are
unverified. No settlement equivalence, fees, collateral or trading gate was approved.

| # | Rule date | League / participants | Selected winner | Source definitions |
| ---: | --- | --- | --- | --- |
| 1 | 2026-10-31 | NBA / ATL–NOP | ATL | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31ATLNOP-ATL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-atl-no-2026-10-31) |
| 2 | 2026-10-31 | NBA / CHA–PHI | PHI | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31PHICHA-PHI) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-phi-cha-2026-10-31) |
| 3 | 2026-10-31 | NBA / CLE–MIL | CLE | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31CLEMIL-CLE) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-cle-mil-2026-10-31) |
| 4 | 2026-10-31 | NBA / HOU–OKC | OKC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31OKCHOU-OKC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-okc-hou-2026-10-31) |
| 5 | 2026-10-31 | NBA / MEM–SAC | SAC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31SACMEM-SAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-sac-mem-2026-10-31) |
| 6 | 2026-10-31 | NBA / MIN–SAS | MIN | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31MINSAS-MIN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-min-sa-2026-10-31) |
| 7 | 2026-10-31 | NBA / POR–UTA | POR | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31PORUTA-POR) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-por-uta-2026-10-31) |
| 8 | 2026-11-01 | NBA / BKN–IND | BKN | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26NOV01BKNIND-BKN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-bkn-ind-2026-11-01) |
| 9 | 2026-11-01 | NBA / BOS–ORL | BOS | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26NOV01BOSORL-BOS) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-bos-orl-2026-11-01) |
| 10 | 2026-11-01 | NBA / GSW–LAC | LAC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26NOV01LACGSW-LAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-lac-gs-2026-11-01) |
| 11 | 2026-11-01 | NBA / LAL–TOR | TOR | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26NOV01TORLAL-TOR) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-tor-lal-2026-11-01) |
| 12 | 2026-11-01 | NFL / ARI–DAL | ARI | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01ARIDAL-ARI) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-ari-dal-2026-11-01) |
| 13 | 2026-11-01 | NFL / ATL–TB | ATL | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01ATLTB-ATL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-atl-tb-2026-11-01) |
| 14 | 2026-11-01 | NFL / BAL–BUF | BAL | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01BALBUF-BAL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-bal-buf-2026-11-01) |
| 15 | 2026-11-01 | NFL / CIN–TEN | TEN | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01TENCIN-TEN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-ten-cin-2026-11-01) |
| 16 | 2026-11-01 | NFL / CLE–PIT | CLE | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01CLEPIT-CLE) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-cle-pit-2026-11-01) |
| 17 | 2026-11-01 | NFL / DEN–KC | KC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01KCDEN-KC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-kc-den-2026-11-01) |
| 18 | 2026-11-01 | NFL / DET–MIN | MIN | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01MINDET-MIN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-min-det-2026-11-01) |
| 19 | 2026-11-01 | NFL / IND–JAC | IND | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01INDJAC-IND) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-ind-jax-2026-11-01) |
| 20 | 2026-11-01 | NFL / LAC–LAR | LAC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01LACLAR-LAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nfl-lac-lar-2026-11-01) |

[Full saved queue and per-pair warnings](evidence/M5I_RUN_20261030_FINAL_QUEUE.json)
retain the original retrieval clock and provenance. The fresh capture validates
ordinary identity only. Existing assistant labels require independent adjudication.
Stop after M5I; no M6 or trading is authorized.


## Audit validation

No application code changed. Read-only deadline coverage and saved-report analysis,
60 fresh public response captures, preservation checks and service shutdown checks
were executed. `.venv/bin/python -m unittest discover -s tests -v` passed all
**397 tests in 17.893 seconds**; [exact output](evidence/M5I_RUN_20261030_POST_TESTS.txt).
`pip check` passed. No inference was requested during the audit, and no new
production recall/precision evaluation is claimed.
