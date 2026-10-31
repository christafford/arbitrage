# M5I — Production-scale semantic discovery results

**Implementation and bounded validation are complete; production backfill and broad quality acceptance remain partial.** All candidates are `UNVERIFIED`. No real contract, fee, collateral review or trading permission was approved. No order, deposit, credential or public inference endpoint was added. Work stops at M5I.

**Operational follow-up:** the operator subsequently authorized a bounded 24-hour
collection/backfill run on October 28. It stopped on October 29; see the separate
[post-run findings](M5I_RUN_20261028_RESULTS.md) for coverage, inference failures
and newly identified contradiction-detection gaps. The
measurements below remain the original M5I implementation snapshot.

**October 30 follow-up:** the [separate-namespace run audit](M5I_RUN_20261029_RESULTS.md)
records 114,413 eligible definitions still unindexed at shutdown. Subsequent
[keyword mismatch repairs and profiling](M5I_CORRECTIONS_20261030.md) demote five
known false pairs and reduce a bounded 250-query replay from 54.2 to 45.5 seconds
with identical retrieval output. This is a performance/regression result, not a
new semantic-quality claim. Both run services remain disabled.

## Measured coverage and performance

The source archive already contained terminal catalogue walks: Kalshi run 22 captured **151,380 unique instruments across 757 pages**, finishing 2026-10-28 00:04 UTC; US run 23 captured **80,066 unique instruments across 402 pages**, finishing 00:18 UTC (three duplicates). M5I reused that evidence instead of treating the earlier 20-page prefix as representative. The source archive stayed at schema 8 and was opened read-only by workers. Schema 9 is used for new archives and adds resumable page checkpoints.

All **339,137 archived instrument heads**, including older/unavailable entries, were synchronized into the persistent sidecar. This is metadata coverage, not vector coverage. At 2026-10-28T02:17:16.530926+00:00:

| Venue | Archived heads synchronized | Eligible | Indexed | Unindexed backlog | Eligible coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Kalshi | 209,437 | 121,065 | 576 | 120,489 | 0.48% |
| Polymarket US | 129,700 | 9,027 | 560 | 8,467 | 6.20% |

The 512-per-venue total-coverage cap is removed from production. Completed vectors persist across invocations, and unchanged public text reuses its model namespace. The measured corrected worker pass added **560 Kalshi + 544 US definitions** in **606.92 seconds**, using **72 HTTP attempts**: **1.819 completed inputs/second**, including transport/probing. An earlier 32-vector batch accounts for the final 576/560 totals. This is end-to-end throughput, not isolated GPU latency. The requested 600-second budget finished its in-flight bounded batch before stopping.

The private service identified `qwen3-embedding-8b`, **4,096 dimensions**, identity `6ad290cf06017f5a5aba88e4f878e7b3320b73c8ac1d8018d376aab00d64cb16`. No server configuration or public exposure changed.

The final 250-query retrieval window took **36.61 seconds**, with Linux `/proc/self/status` reporting **34,256 KiB (33.45 MiB) peak resident memory**. It returned **82 distinct events**: 52 sports identity, 26 keyword, four embedding-assisted leads. There were **73 saturated approximate bucket probes at the query level**, zero vector validation failures, and `window_complete=false`. Both query traversal and vector coverage remain partial. The final join plan starts from bounded vector buckets; a regression prevents a venue-wide metadata scan in this lookup.

[Coverage by venue, category and administrative settlement-deadline horizon](evidence/M5I_COVERAGE.json) includes UNKNOWN values instead of inferred categories or cash-release dates. [Run evidence](evidence/M5I_VALIDATION.json) records counts, timing, model identity and source hashes.

## Genuine-definition evaluation

The [committed dataset](../tests/fixtures/m5i-genuine-evaluation.json) contains **49 genuine archived definitions**, **18 positive ordinary-proposition labels** and **20 explicit hard negatives**. It covers NBA/NFL same-event selections, inverse outcomes, CPI thresholds, monthly versus annual measures, absolute Fed-rate thresholds versus rounded change buckets, unrelated subjects, and different exceptional settlement rules. Every excerpt retains its public URL, receipt time, adapter schema, parent response hash and excerpt hash. Labels were prepared by the assistant for retrieval evaluation; they are not operator decisions.

| Measurement | Previous deterministic implementation | M5I with actual Qwen vectors |
| --- | ---: | ---: |
| Recall@20 | 18/18 (100%) | 18/18 (100%) |
| Recall@100 | 18/18 (100%) | 18/18 (100%) |
| Precision among returned candidates | 18/74 (24.32%) | 18/18 (100%) |
| Missed positive categories | None in this corpus | None in this corpus |
| Distinct labeled reviewable events | 11 | 11 |
| New labeled reviewable events | — | **0** |

The live evaluation embedded 49 genuine inputs in **29.75 seconds** (1.647 inputs/second), six requests, zero cache hits. The final retrieval implementation was replayed against those archived actual vectors at the preserved evaluation clock without another inference call. [Full per-query results](evidence/M5I_EVALUATION.json) retain model and provenance.

The same precision improvement also occurred with inference disabled: explicit selection/threshold handling and event diversity explain the demonstrated gain. **This does not prove incremental model recall or venue-wide precision.** The corpus is small, purposive, not held out or independently adjudicated; its candidate pool is much smaller than 100 per query. These Recall@20/@100 values are consequently weak evidence of production-scale recall.

The production window has **39 pair IDs absent from the saved 50-row discovery snapshot**: nine sports identities, 26 keyword leads and four semantic leads. These are unapproved leads from different queue limits/windows, not an apples-to-apples embedding gain. The 30 generic leads have not been labeled reviewable. The controlled real corpus establishes **zero additional events** beyond deterministic retrieval.

## Operator review: 20 distinct live candidate events

Fresh, bounded public metadata captures confirmed 30 available same-identity candidates, archiving **90 raw responses** in `data/m5i/live-review.sqlite3`. The following 20 also appear in the persistent-index shortlist. After the session resumed, all 20 were recaptured again at **2026-10-28T12:50:50.231919+00:00 through 2026-10-28T12:51:28.226674+00:00**, confirming availability and identity with **60 additional raw responses** in `data/m5i/live-review-final.sqlite3`. [Final recapture provenance](evidence/M5I_LIVE_CAPTURE_FINAL.json) is preserved separately from the initial 30-event capture. Availability means available **at the recorded capture time**, not a current executable quote. [Exact IDs, per-pair receipt clocks, warnings and source observation references](evidence/M5I_TOP20.json) and [all capture provenance](evidence/M5I_LIVE_CAPTURE.json) are retained. No books or economics were inferred.

Every row was retrieved by exact **league + participants + scheduled rule date + selected winner**. The candidate is for review of ordinary event identity only. For every row: **F** = independent fair-price exceptional settlement is not established complementary; **P** = postponement, cancellation and forfeit applicability needs review; **R** = source/revision rules are unverified; **C** = administrative cutoff/cash-availability differences remain unapproved. These are unresolved differences or uncertainties, never presumed matching payouts. Charlotte–Detroit additionally has the [detailed prior review](CHARLOTTE_DETROIT_REVIEW.md).

| # | Scheduled rule date / event | Selected winner | Official definitions | Retrieval reason | Unresolved issues |
| ---: | --- | --- | --- | --- | --- |
| 1 | 2026-10-28 NBA Charlotte Hornets–Detroit Pistons | Charlotte Hornets | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28CHADET-CHA) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-cha-det-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 2 | 2026-10-28 NBA Denver Nuggets–New Orleans Pelicans | Denver Nuggets | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28DENNOP-DEN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-den-no-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 3 | 2026-10-28 NBA Golden State Warriors–Minnesota Timberwolves | Golden State Warriors | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28GSWMIN-GSW) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-gs-min-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 4 | 2026-10-28 NBA Houston Rockets–Milwaukee Bucks | Houston Rockets | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28HOUMIL-HOU) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-hou-mil-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 5 | 2026-10-28 NBA Los Angeles Clippers–Los Angeles Lakers | Los Angeles Lakers | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28LALLAC-LAL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-lal-lac-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 6 | 2026-10-28 NBA Atlanta Hawks–Miami Heat | Miami Heat | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28MIAATL-MIA) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-mia-atl-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 7 | 2026-10-28 NBA Chicago Bulls–New York Knicks | New York Knicks | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28NYKCHI-NYK) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-ny-chi-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 8 | 2026-10-28 NBA Orlando Magic–Toronto Raptors | Orlando Magic | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28ORLTOR-ORL) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-orl-tor-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 9 | 2026-10-28 NBA San Antonio Spurs–Utah Jazz | San Antonio Spurs | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28SASUTA-SAS) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-sa-uta-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 10 | 2026-10-28 NBA Cleveland Cavaliers–Washington Wizards | Washington Wizards | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT28WASCLE-WAS) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-was-cle-2026-10-28) | Exact teams/date/selection | F, P, R, C |
| 11 | 2026-10-29 NBA Atlanta Hawks–Cleveland Cavaliers | Cleveland Cavaliers | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT29CLEATL-CLE) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-cle-atl-2026-10-29) | Exact teams/date/selection | F, P, R, C |
| 12 | 2026-10-29 NBA Memphis Grizzlies–Portland Trail Blazers | Memphis Grizzlies | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT29MEMPOR-MEM) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-mem-por-2026-10-29) | Exact teams/date/selection | F, P, R, C |
| 13 | 2026-10-29 NBA New Orleans Pelicans–Sacramento Kings | Sacramento Kings | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT29SACNOP-SAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-sac-no-2026-10-29) | Exact teams/date/selection | F, P, R, C |
| 14 | 2026-10-30 NBA Charlotte Hornets–Washington Wizards | Charlotte Hornets | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30CHAWAS-CHA) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-cha-was-2026-10-30) | Exact teams/date/selection | F, P, R, C |
| 15 | 2026-10-30 NBA Boston Celtics–Chicago Bulls | Chicago Bulls | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30CHIBOS-CHI) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-chi-bos-2026-10-30) | Exact teams/date/selection | F, P, R, C |
| 16 | 2026-10-30 NBA Denver Nuggets–Phoenix Suns | Denver Nuggets | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30DENPHX-DEN) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-den-pho-2026-10-30) | Exact teams/date/selection | F, P, R, C |
| 17 | 2026-10-30 NBA Brooklyn Nets–Detroit Pistons | Detroit Pistons | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30DETBKN-DET) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-det-bkn-2026-10-30) | Exact teams/date/selection | F, P, R, C |
| 18 | 2026-10-30 NBA Indiana Pacers–Miami Heat | Indiana Pacers | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30INDMIA-IND) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-ind-mia-2026-10-30) | Exact teams/date/selection | F, P, R, C |
| 19 | 2026-10-30 NBA Los Angeles Clippers–Minnesota Timberwolves | Los Angeles Clippers | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30LACMIN-LAC) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-lac-min-2026-10-30) | Exact teams/date/selection | F, P, R, C |
| 20 | 2026-10-30 NBA New York Knicks–Philadelphia 76ers | New York Knicks | [Kalshi](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT30NYKPHI-NYK) · [US](https://gateway.polymarket.us/v1/market/slug/aec-nba-ny-phi-2026-10-30) | Exact teams/date/selection | F, P, R, C |

All 20 remain **UNVERIFIED**. US synthetic NO remains unsupported by the cash-funded-long evaluator. No fresh cross-venue book comparison, applicable fee approval or complementary exceptional payout has been established by this shortlist.

## Validation and remaining gaps

`python -m unittest discover -s tests -v` was run in the repository virtual environment; [the full test log](evidence/M5I_TESTS.txt) names every executed test. **367 tests passed** in the final full run; the log records the exact names and results. Tests cover >512 incremental coverage, advancing inference clocks, interruption within an uncommitted catalogue page, resumability, partial inference failure, changed descriptions, unchanged-vector reuse, model upgrades, stale catalogues, invalid/stale/partial liquidity, corruption, event diversity, source-writer independence, busy-worker deterministic fallback, preservation of the established queue during initial backfill, genuine fixture replay and sidecar backup integrity.

[CLI smoke evidence](evidence/M5I_SMOKE.json) records demo/report, offline and cached-catalogue refresh, queue, sidecar coverage/retrieval, help, and two successive live page-bounded walks for each venue. The four walk invocations intentionally exited **2/PARTIAL** and resumed the same per-venue runs; no full new traversal is claimed. Existing terminal full traversals above supply the broad catalogue evidence.

[Deployment checks](evidence/M5I_DEPENDENCIES.json): Python 3.13.5, SQLite 3.46.1 with FTS5; `pip check` passed. systemd unit verification passed with `/opt/predarb` substituted by the actual checkout for executable validation. No new third-party dependency is required. Units were **not installed or activated**; deployment paths/account and the ongoing schedule still need provisioning.

Remaining gaps: finish the **128,956-vector backlog** at the measured snapshot; finish query traversal; measure approximate recall under a populated index and saturated buckets; independently label a broader set of real non-sports events; establish incremental reviewable semantic yield. Missing Kalshi categories remain UNKNOWN. Offset paging is not an atomic venue census. Raw evidence retention still requires disk monitoring and backups. The partial backfill and lack of demonstrated new semantic events prevent claiming completed broad production-quality acceptance.

[Operating commands, resource budgets, restart behavior and failure modes](M5I_OPERATIONS.md). M4/M5 sustained-run acceptance and all human review gates remain unchanged.


## October 29 separate-namespace recovery

The operator authorized a separate namespace after the restored server failed the
original exact probe pin. A new sidecar preserves the previous vectors intact.
The [12-hour run record](M5I_RUN_20261029.md) documents a successful 32-definition
startup batch, incomplete metadata coverage and a fixed October 30 deadline.
These are startup measurements, not completed backfill or new retrieval-quality
results. The prior run and evaluation evidence above retain their original scope.


## October 30 completed-run audit

The separate-namespace run stopped at its deadline. It stored 12,880 vectors and
indexed 5,680/117,298 eligible Kalshi definitions and 6,277/9,072 eligible US
definitions at shutdown; 114,413 remained unindexed. Two full refresh rounds per
venue completed. Further keyword proposition mismatches and substantial retrieval
overhead remain; incremental semantic yield is unproven. The
[final audit includes 20 freshly checked distinct candidate events](M5I_RUN_20261029_RESULTS.md),
source links, retrieval reasons and settlement-review warnings. All remain
UNVERIFIED. Expired services are disabled; no further run is active.


The [October 30–31 continuation audit](M5I_RUN_20261030_RESULTS.md) records
23,978 stored vectors, 100% US / 8.61% Kalshi eligible coverage, and 117,488
definitions still unindexed. Both services are stopped/disabled. The final queue
has 54 sports identities and 46 keyword leads with no vector-supported finalist;
broader proposition mismatches and independently adjudicated quality remain open.
