# M5I October 29–30 run — final audit

**The bounded run finished successfully; full backfill and matching-quality
acceptance remain incomplete.** Both services stopped at the fixed **October 30,
07:20:39 EDT / 11:20:39 UTC** deadline, exited 0, and are now disabled. The
semantic service finished stopping 0.266 seconds after the deadline. No new
background run was started. Original namespaces and the original run configuration
remain preserved; no vectors were merged or relabeled.

## Coverage at shutdown

| Venue | Eligible definitions | Indexed | Coverage | Unindexed backlog |
| --- | ---: | ---: | ---: | ---: |
| Kalshi | 117,298 | 5,680 | 4.84% | 111,618 |
| Polymarket US | 9,072 | 6,277 | 69.19% | 2,795 |
| Total | 126,370 | 11,957 | 9.46% | 114,413 |

All **457,661 archived instrument heads** were synchronized: 292,199 Kalshi and
165,462 US, with zero unsynced heads. These include expired/unavailable contracts
and are not the eligible-vector denominator. The new namespace contains **12,880
stored vectors**, including the 32-definition startup batch and definitions no
longer eligible. The old index retains its 31,249 pinned and 1,456 alternate
vectors separately; their counts are not added to new-namespace coverage.

At the later 08:34 EDT audit, 42 Kalshi definitions had closed: 5,678/117,256
remained eligible/indexed, with backlog 111,578. US figures were unchanged.
The [complete audit evidence](evidence/M5I_RUN_20261029_FINAL.json) preserves both
clocks and venue/category/administrative-horizon breakdowns. UNKNOWN categories
remain unknown; administrative deadlines do not establish cash-release dates.

## Collection, inference and runtime

Two complete catalogue rounds per venue reached terminal pagination:

| Round | Kalshi run / unique definitions | US run / unique definitions |
| --- | --- | --- |
| 1 | 32 / 167,478 | 33 / 81,754 |
| 2 | 34 / 163,688 | 35 / 79,464 |

The final traversals completed at 06:38 UTC (Kalshi) and 06:27 UTC (US). Counts
across rounds must not be summed as distinct markets. An actual Kalshi transport
retry recovered; both collection rounds completed.

There were **34 completed inference reports: 33 READY and one FALLBACK**. They
record 6,560 Kalshi and 6,288 US completions, 948 HTTP attempts and 20,811.48 worker
seconds: **0.617 definitions/worker-second**, including probes and local processing.
The separate 32-definition startup pass is excluded from that throughput. These
are operational measurements, not isolated GPU speed or a complete-backfill ETA.
All completed reports used the authorized `8f1b7456…` pin; none reported a pin
mismatch. The one `SERVICE_UNREACHABLE` fallback retained 160 completed definitions,
backed off, and was followed by a successful 224-definition batch. The last archived
inference response at 11:19:20 UTC was HTTP 200 and valid.

The last retrieval invocation was interrupted at the fixed deadline. Its supervisor
logged a timeout/retry and then stopped successfully; no retry extended the run.
The last completed queue remains ranked at **10:56 UTC**. A normal deadline
interruption is not a completed retrieval window.

Measured completed-command time in the semantic service was approximately:

| Work | Time |
| --- | ---: |
| Inference commands | 5.78 hours |
| Retrieval commands | 3.60 hours |
| Metadata synchronization | 1.40 hours |
| Coverage reports | 0.42 hours |

Collection ran independently (1.29 command-hours). These times identify substantial
local retrieval/synchronization overhead; they do not isolate CPU from storage or
prove a GPU bottleneck. At audit, source/new index/old index occupied approximately
19.44/5.63/9.89 GiB respectively, with about 806.84 GiB free; backups are additional.
No new full-archive integrity scan or backup verification is claimed.

## Retrieval quality remains a blocker

The 33 completed retrieval reports executed **8,250 queries**, not necessarily
8,250 distinct events. None completed the generic traversal. The last bounded
window reported 125 saturated approximate probes and zero vector-validation
failures. Recall at full production scale is still unmeasured.

The [last 100-event queue](evidence/M5I_RUN_20261029_FINAL_QUEUE.json) contains
**64 sports-identity and 36 keyword suggestions**. None has vector retrieval
support in that final queue. At audit, current source/freshness revalidation
retained 89 of these candidates (64 sports, 25 keyword). No controlled new
baseline comparison or independent label adjudication ran, so **no additional
reviewable event yield attributable to embeddings is established**.

Inspection of archived definitions found additional keyword mismatches whose
saved and revalidated `known_contradictions` lists were empty:

| Pair | Observed difference |
| --- | --- |
| North Carolina State Senate / US Senate election | State legislative chamber control versus electing a US Senator |
| Musk next CEO of X / out as Tesla CEO | Different companies and appointment versus departure propositions |
| “Die With A Smile” Spotify USA ranking | #2 versus #1 |
| December Fed hike / no change | Hike outcome versus unchanged target-rate upper bound; Kalshi primary wording also omits an inequality present in its title |

Exact public definitions, source versions, receipts and links are included in the
audit evidence. These are assistant review observations, not independent quality
labels or legal determinations. The earlier four regression fixes remain tested,
but do not cover these further proposition patterns. An empty warning list must
never be treated as equivalence. These pairs are excluded from the shortlist below.

## Twenty distinct freshly checked candidate events

Public US metadata was recaptured at **08:35:25–08:36:03 EDT on October 30**, using
60 archived responses in a new isolated review database. Both venue instruments
were available and their ordinary sports identities matched for all 20 events.
[Fresh source receipts, hashes, raw archive references and complete candidate reasons](evidence/M5I_RUN_20261029_LIVE_REVIEW.json).

Each row was retrieved by the deterministic **exact NBA league, full-game winner,
participants, scheduled rule date and selected team** match. Equal identity scores
were ordered by upcoming rule date and event key. These are review candidates,
not new discoveries credited to the embedding model. No fresh books were captured;
liquidity remains unknown. Dates below are the matcher's scheduled rule dates.

For **every row**, the known warning is different administrative cutoffs. Material
settlement equivalence is **UNVERIFIED**: postponement windows, forfeit/source
revision rules and exceptional fair-price payouts require operator comparison.
Occurrence timestamps and scheduled starts are not interchangeable. US synthetic
NO remains unsupported, and account mechanics/fees/collateral are not approved.
No explicit material contradiction was detected in these sports rows; that is not
proof there is none. The links expose each venue's exact selected definition.

| # | Rule date | NBA event | Selected winner | Definitions | Retrieval / known warning |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-30 | BKN vs DET | DET | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30DETBKN-DET) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-det-bkn-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 2 | 2026-10-30 | BOS vs CHI | CHI | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30CHIBOS-CHI) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-chi-bos-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 3 | 2026-10-30 | CHA vs WAS | CHA | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30CHAWAS-CHA) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-cha-was-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 4 | 2026-10-30 | DAL vs HOU | HOU | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30HOUDAL-HOU) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-hou-dal-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 5 | 2026-10-30 | DEN vs PHX | DEN | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30DENPHX-DEN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-den-pho-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 6 | 2026-10-30 | GSW vs LAL | LAL | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30LALGSW-LAL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-lal-gs-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 7 | 2026-10-30 | IND vs MIA | IND | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30INDMIA-IND) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-ind-mia-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 8 | 2026-10-30 | LAC vs MIN | LAC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30LACMIN-LAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-lac-min-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 9 | 2026-10-30 | NYK vs PHI | NYK | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30NYKPHI-NYK) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-ny-phi-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 10 | 2026-10-30 | ORL vs TOR | ORL | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30ORLTOR-ORL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-orl-tor-2026-10-30) | Exact sports identity; cutoffs differ; settlement review required |
| 11 | 2026-10-31 | ATL vs NOP | ATL | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31ATLNOP-ATL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-atl-no-2026-10-31) | Exact sports identity; cutoffs differ; settlement review required |
| 12 | 2026-10-31 | CHA vs PHI | PHI | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31PHICHA-PHI) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-phi-cha-2026-10-31) | Exact sports identity; cutoffs differ; settlement review required |
| 13 | 2026-10-31 | CLE vs MIL | CLE | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31CLEMIL-CLE) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-cle-mil-2026-10-31) | Exact sports identity; cutoffs differ; settlement review required |
| 14 | 2026-10-31 | HOU vs OKC | OKC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31OKCHOU-OKC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-okc-hou-2026-10-31) | Exact sports identity; cutoffs differ; settlement review required |
| 15 | 2026-10-31 | MEM vs SAC | SAC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31SACMEM-SAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-sac-mem-2026-10-31) | Exact sports identity; cutoffs differ; settlement review required |
| 16 | 2026-10-31 | MIN vs SAS | MIN | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31MINSAS-MIN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-min-sa-2026-10-31) | Exact sports identity; cutoffs differ; settlement review required |
| 17 | 2026-10-31 | POR vs UTA | POR | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31PORUTA-POR) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-por-uta-2026-10-31) | Exact sports identity; cutoffs differ; settlement review required |
| 18 | 2026-11-01 | BKN vs IND | BKN | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26NOV01BKNIND-BKN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-bkn-ind-2026-11-01) | Exact sports identity; cutoffs differ; settlement review required |
| 19 | 2026-11-01 | BOS vs ORL | BOS | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26NOV01BOSORL-BOS) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-bos-orl-2026-11-01) | Exact sports identity; cutoffs differ; settlement review required |
| 20 | 2026-11-01 | GSW vs LAC | LAC | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26NOV01LACGSW-LAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-lac-gs-2026-11-01) | Exact sports identity; cutoffs differ; settlement review required |

## Verification and next work

`python -m unittest discover -s tests -v` executed **387 tests**, all passed in
**17.204 seconds**; [exact output](evidence/M5I_RUN_20261029_POST_TESTS.txt). The
read-only coverage/queue audit and actual 20-event public metadata capture passed.
No production source/index was written during the audit; only the isolated live
review archive received new public evidence. Expired units were disabled.

The next useful work is to repair the newly observed proposition mismatches and
profile the 3.60 hours of retrieval overhead before scheduling a larger backfill.
Remaining 114,413 eligible vectors at shutdown, complete query traversal, production
recall, independently adjudicated precision and incremental semantic event yield
remain open. No M6, trading, funds or automatic contract approval was introduced.
