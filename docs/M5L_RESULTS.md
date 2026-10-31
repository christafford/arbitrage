# M5L — Economic research and AI throughput benchmark

**No eligible executable arbitrage was established. M5L acceptance remains partial.**
The benchmark, optional priority scheduler, genuine-definition comparison and two
sports evidence cases are implemented and exercised. Independent adjudication is
pending at the operator's request. Inference-host telemetry is unavailable, and
settlement, fee/account review and quote synchronization still block economics.
Nothing in this report authorizes funds, orders, approval renewal or another run.

All measurements below are October 31, 2026 UTC snapshots. The production source,
both existing semantic indices, expired run configurations/status files and exact
model pin were preserved. All six M5I units remain disabled. [Preservation checks](evidence/M5L_VALIDATION.json)
compare size/mtime for databases and SHA-256 for run files; this is not a new
full-database integrity or all-content hash audit. Existing historical evidence
and backups remain intact. No production model setting was changed.

## A. Measured inference pipeline

The direct benchmark sent the **same 64 distinct genuine archived descriptions**
in batches of 8, 16, 32 and 64, three complete passes per successful setting.
The dataset is a purposive mixture of sports, economics, politics, culture and
other development cases, **not a representative catalogue sample**. Sixty entries
come from the compatibility corpus; four older definitions are throughput-only.
No source receipt was renewed. Inputs use the existing public-text allowlist.

Each method/batch has its own SQLite archive. The instruction variant applies
`Instruct: …\nQuery: …` to US queries only; Kalshi document texts are unchanged,
following the [Qwen model card](https://huggingface.co/Qwen/Qwen3-Embedding-8B).
The exact instruction, corpus hashes, raw response IDs, HTTP timings, client CPU
samples, namespaces and errors are in [benchmark evidence](evidence/M5L_BENCHMARK.json).
Every namespace records the exact probe fingerprint and text method. None is
merged into production.

| Descriptions/request | Existing text, median descriptions/s | Query instruction, median descriptions/s | Interpretation |
| ---: | ---: | ---: | --- |
| 8 | 1.604 | 1.190 | Existing 4 MiB client limit |
| 16 | 2.265 | 1.026 | Existing 4 MiB client limit |
| 32 | 2.927 | 1.320 | Existing 4 MiB client limit |
| 64 | rejected | rejected | HTTP 200, but response exceeded 4 MiB; not a GPU failure |
| 64, separate 16 MiB diagnostic | 3.247 | 3.119 | Measured successfully; **not production-compatible** |

The separately bounded diagnostic archived complete responses of **5,633,176**
and **5,631,819 bytes**. The original truncated responses remain rejected and
preserved. Production's response guard is unchanged.
[Large-batch results](evidence/M5L_LARGE_BATCH_DIAGNOSTIC.json).
The batch values above count descriptions, not llama.cpp token batch/microbatch
parameters. Fixed-order trials, warm prompt reuse and large timing variation limit
causal comparisons: the existing batch-32 passes took 18.22, 43.30 and 21.86 seconds.
These figures do not prove an instruction's intrinsic speed penalty or a stable
full-backfill rate.

A separate run exercised the actual persistent worker, including probes, raw
archival, decoding, cache, packed vectors, checksums and bucket commits, on the
same **60 current eligible definitions**, with new empty indices each time:

| Configured batch | Completed definitions | Wall seconds | HTTP seconds | Non-HTTP seconds | Definitions/s |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 60 | 60.733 | 58.600 | 2.132 | 0.988 |
| 16 | 60 | 34.665 | 32.639 | 2.026 | 1.731 |
| 32 | 60 | 43.538 | 41.365 | 2.173 | 1.378 |
| 64 | 60 | 40.161 | 38.191 | 1.971 | 1.494 |

There were 33 Kalshi and 27 US inputs. Venue-separated batches mean the last row
**never sent 64 descriptions in one request**; it does not contradict the direct
64-input response-size failure. These are single trials, not sustained estimates.
The overnight production run's **0.345 definitions/s** remains the better measured
long-run baseline, but its changing corpus and worker limits differ from this test.

HTTP includes TLS/network, server queuing, inference and body transfer. It consumed
**94–97%** of worker wall time. Non-HTTP time includes SQLite, serialization,
validation, scheduling and throttling; it is not a pure SQLite measurement. Model
probes took approximately 2.1–4.7 seconds in direct tests and are separately logged.
Existing-text HTTP request medians were 3.862/4.968/10.907 seconds for 8/16/32;
time-to-headers medians were 1.305/2.270/3.768 seconds. In the 64-input diagnostic,
headers arrived in about 7–8 seconds while complete receipt took 16–25 seconds.
Post-header transfer is substantial, but streaming/server behavior prevents calling
that interval pure network delay. No reliable GPU/network split was measured.
Ten later health GETs had **0.371-second median** latency; subtracting that from
embedding latency would not isolate inference. [Diagnostics](evidence/M5L_DIAGNOSTICS.json).

Client CPU averaged approximately 0.60–0.68 seconds per 64-input direct pass.
The benchmark process reported **578,032 KiB peak RSS** (~564 MiB), exceeding the
old 256 MiB worker service cap: this diagnostic harness was not a service-cap
acceptance test. It retained full vector exports for quality comparison. Later
client-host diagnostics showed about 13.6 GiB MemAvailable and nonzero existing
swap use; `/proc/pressure/memory` is unavailable. Those later observations do not
establish benchmark-time memory pressure. Inference-host CPU, VRAM consumption,
actual current offloaded layers and GPU-only time are **UNKNOWN**.

Private `/props` confirms `qwen3-embedding-8b`, Q6_K, build `b10705-3f5abc5`, one
slot and context 2048. `/metrics` returned 501 and props reports metrics disabled.
SSH with strict checking still fails because no verified ED25519 host key is known.
No host verification was bypassed. The earlier operator trace of Vulkan/RTX 3080,
37/37 layers and 6366 MiB projected use is **historical evidence**, not a current
VRAM measurement. Probes still vary with request history; the bounded exact
`8f1b745674ea82993cc5211498d606a86627ecedb6776637daeaf66e42611204` gate passed
without tolerance or relabeling.

**Production recommendation:** retain the existing model, identity, runtime,
16-description batch and concurrency 1. Batch 16 won the persistent trial; batch
32 is worth a controlled interleaved test, not an immediate default change.
Do not enable 64 under the current response limit. A future larger-response change
needs bounded memory validation first. Do not change GPU layers, microbatch,
threads or quantization based on missing host measurements. Host-side performance
logs and a verified telemetry connection are prerequisites for that tuning.

## B. Economic-priority backfill

`predarb.backfill` and `scripts/m5l_backfill.py` build a **separate derived scheduler**.
It favors currently eligible, supported definitions with a recognized near-term
event date, positive documented 24-hour volume and fresh positive two-sided depth.
Missing/zero/invalid activity and missing/stale/partial liquidity remain explicit.
Volume is reported trading activity, not executable liquidity. Supported discovery
mechanics do not imply account or settlement approval.

Three priority selections alternate with one rotating stable-hash backfill selection,
per venue. Successful vector commits advance the saved slot/cursor; failed batches
leave it unchanged. Existing vectors, changed definitions, stale source heads and
wrong namespaces are rechecked before selection. Expired liquidity/event-date
bonuses are demoted at selection. Fair progress assumes successful inference and
eligible work; a failed service is not counted as completed backfill. Original
raw responses and older vectors are retained.

`index-work --scheduler-db PATH --expected-identity PIN` is an optional integration;
the default M5I scheduler is unchanged. No production scheduled batch ran. The
actual plan is `data/m5l/scheduler.sqlite3`; [plan and coverage](evidence/M5L_BACKFILL.json)
were evaluated at **19:35:47.073722 UTC**:

| Venue | Eligible | Indexed in existing pin | Backlog |
| --- | ---: | ---: | ---: |
| Kalshi | 128,489 | 11,068 | 117,421 |
| Polymarket US | 9,138 | 9,138 | 0 |
| Total | 137,627 | 20,206 | 117,421 |

Differences from the shutdown count of 117,488 reflect advancing eligibility time,
not new production vectors. The archive still has 521,322 synchronized metadata
heads and 23,978 stored vectors, including ineligible historical definitions.
Catalogue, metadata, eligible vector coverage and quality denominators stay separate.

| Eligible grouping | Indexed | Backlog |
| --- | ---: | ---: |
| Category UNKNOWN | 11,054 | 117,327 |
| Recognized sports | 150 | 94 |
| All other reported categories | 9,002 | 0 |
| Positive reported 24-hour volume | 833 | 13,402 |
| Zero reported 24-hour volume | 10,235 | 104,019 |
| Activity UNKNOWN | 9,138 | 0 |
| Liquidity MISSING in source archive | 20,206 | 117,421 |
| Administrative deadline 0–7 days | 932 | 3,417 |
| Administrative deadline 8–30 days | 3,324 | 13,998 |
| Administrative deadline 31–90 days | 7,390 | 24,028 |
| Administrative deadline over 90 days | 8,560 | 75,978 |

Rows are overlapping breakdowns, not additive populations. Full venue/category/
activity/liquidity/horizon intersections are in the JSON. Fresh books captured in
the separate sports archives do not silently improve the production-source
liquidity denominator. Reported generic categories are preserved; a ticker prefix
is not used to invent a category. Only recognized sports rule dates supply event
dates in this planner; generic event dates can remain UNKNOWN. Market cutoff,
administrative settlement deadline and expected capital release are separate fields.
**Expected capital release is UNKNOWN for every definition.**

At the overnight 0.345/s rate, the unchanged 117,421 backlog alone would take about
94.5 worker-hours. This is arithmetic on a frozen backlog, **not a completion ETA**:
new markets, stale definitions, service availability and retrieval compete for time.
The plan's first 16 Kalshi choices contain near-term NBA/NFL activity and four fair
slots; they are research priorities, not 16 economically eligible contracts.

## C. Two live sports research cases

Both ordinary event identities were already found deterministically. Fresh detail
captures confirmed open supported instruments, not settlement equivalence:

- NBA: [Atlanta at New Orleans, October 31](https://external-api.kalshi.com/trade-api/v2/markets/KXNBAGAME-26OCT31ATLNOP-ATL)
  and [Polymarket US long Atlanta](https://gateway.polymarket.us/v1/market/slug/aec-nba-atl-no-2026-10-31).
- NFL: [Arizona at Dallas, November 1](https://external-api.kalshi.com/trade-api/v2/markets/KXNFLGAME-26NOV01ARIDAL-ARI)
  and [Polymarket US long Arizona](https://gateway.polymarket.us/v1/market/slug/aec-nfl-ari-dal-2026-11-01).

Bounded 45-second clocked captures ran at **19:34:42–19:35:28** and
**19:36:04–19:36:50 UTC**. NBA recorded two snapshots, 21 deltas and recovery after
one message timeout. NFL recorded three snapshots, five deltas, two message
timeouts and one connection/processing failure. Each connection begins a new
snapshot/sequence generation; gaps are not merged. Current `clocked` schema passed;
expired `sequence-v1` was never used. US snapshots are independently replaced,
not treated as a sequenced feed. All raw frames, assessments and backups remain in
`data/m5l/{nba,nfl}-capture/`. [Economic evidence](evidence/M5L_ECONOMICS.json) includes
all comparisons and full depth; [sanitized genuine fixture](../tests/fixtures/m5l-public-live.json)
contains exact public REST bytes and privacy-screened WS frames with hashes.

No recorded observation met both the source- and receipt-skew limits. The closest
individually usable observations had source/receipt skews of **4.530/2.167 seconds**
(NBA) and **37.345/1.342 seconds** (NFL). Saved polling samples and per-book replay
have different sampling clocks; neither produced an eligible comparison.
Stopped streams are disconnected at current time. These are historical quotes.

| Case | Kalshi NO ask / displayed size | US YES ask / displayed size | Indicative sum per unit, before fees |
| --- | --- | --- | ---: |
| Atlanta | $0.3800 / 9,470.67 | $0.6200 / 30,085.2700 | $1.0000 |
| Arizona | $0.7500 / 440,113.50 | $0.2575 / 727,675.1400 | $1.0075 |

The last column is arithmetic on **unsynchronized displayed quotes**, not an
executable edge or fill guarantee. Even ordinary-game payout of $1 offers no gross
profit at those levels before positive taker fees. Large displayed sizes do not
establish priority in the queue, atomic fills, settlement compatibility or cash
availability. No opportunity was counted merely because teams/date matched.

The supported route for review is buying cash-funded Kalshi NO and US YES on the
same selected winner. Purchase costs plus applicable fees must be funded on both
venues; no collateral offset or proceeds reuse is credited. The reverse route
requires US short YES. [US collateral rules](https://docs.polymarket.us/market-structure/collateral-and-margin)
require the full $1 payout collateral for a short; net buying-power reduction is
not the collateral requirement. That route remains unsupported.

Current public fee captures for both games found Kalshi quadratic-with-maker-fees,
multiplier 1, no event override and no upcoming changes in the captured responses;
US reported the standard 0.0695 coefficient. Four [unapproved fee packets](evidence/M5L_FEE_REVIEWS.json)
retain raw source hashes and blank account/effective-time reviews. The official
[Kalshi fee schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf) was checked
through the web tool (effective July 7); direct PDF download returned 429, so no
new local full-PDF hash is claimed. The [current US schedule](https://docs.polymarket.us/fees)
and Kalshi rounding/series documents were archived. Current advertised rules are
not operator-approved account applicability; no fee profile was imported.

### Settlement scenarios and capital timing

This is an assistant comparison, not a legal-equivalence decision. Full public
contracts and [source capture manifest](evidence/M5L_SETTLEMENT_SOURCES.json) are
preserved, including NBA/NFL terms and the US Rulebook.

| Scenario | Comparison and unresolved economic consequence |
| --- | --- |
| Ordinary selected-team win/loss | Both identify the same winner and include overtime. K NO + US YES ordinarily pays 0+1 or 1+0 per unit. Same-event identity alone is insufficient. |
| NFL tie | Both captured market descriptions specify 0.50; that ordinary tie case can sum to $1. It does not establish every exceptional outcome. |
| Delay/postponement | Both market descriptions specify a two-day/48-hour window. US general FAQ also discusses expiration; exact contract precedence and boundary interpretation need human review. |
| Cancellation/no official result | Each venue can select its own fair-market settlement. For K NO + US YES, payout is `1 − fK + fUS`; no evidence establishes `fK = fUS`. Do not substitute 0.50. Residual settlement risk remains. |
| Shortened/suspended game | Kalshi NBA terms distinguish completed segments and full-game 48-minute/official-result conditions. NFL terms use a 55-minute/official-result condition. US relies on official thresholds, contract terms and expiry. Matching treatment is unestablished. |
| Pre-game forfeit | Kalshi terms prescribe fair-price treatment; US general FAQ treats the awarded participant as winner. Applicability/precedence needs clarification. |
| Venue/home-away change, disqualification | Kalshi has explicit conditions; no complete cross-venue payout mapping was approved. |
| Corrections/protests/replay | Kalshi's first-result/revision-before-expiry framework and US review/replay provisions have not been established equivalent. |
| Venue failure, one-leg fill or outage | No simultaneous fill assumption converts these into strict arbitrage; actual execution was not attempted or simulated as realized profit. |

The [NBA terms](https://assets.kalshi.com/contract_terms/BASKETBALLGAMEWIN.pdf),
[NFL terms](https://assets.kalshi.com/contract_terms/FOOTBALLGAMEWIN.pdf) and
[US sports FAQ](https://docs.polymarket.us/faqs/sports-faqs) support these review
questions. No warning or settlement gate was removed.

| Date role | Atlanta | Arizona |
| --- | --- | --- |
| US scheduled start | October 31 23:00 UTC | November 1 18:00 UTC |
| Kalshi occurrence field (not substituted for start) | November 1 02:00 UTC | November 1 21:00 UTC |
| Kalshi cutoff / latest expiration | November 2 23:00 UTC | November 3 18:00 UTC |
| US `endDate` administrative proxy | November 14 23:00 UTC | November 15 23:00 UTC |
| Actual expected reusable cash | UNKNOWN | UNKNOWN |

| Combined capital commitment | NBA net return / feasible fill | NFL net return / feasible fill |
| ---: | --- | --- |
| $5 | UNKNOWN / UNVERIFIED | UNKNOWN / UNVERIFIED |
| $25 | UNKNOWN / UNVERIFIED | UNKNOWN / UNVERIFIED |
| $100 | UNKNOWN / UNVERIFIED | UNKNOWN / UNVERIFIED |
| $500 | UNKNOWN / UNVERIFIED | UNKNOWN / UNVERIFIED |

These are explicit blocked calculations, **not zero-profit estimates**. Neither
pair passes fresh comparable books, settlement scenarios, current fee applicability,
account mechanics and capital-release gates. Producing numeric net returns would
require bypassing those gates or inventing terms. Strict-arbitrage candidates: **0**;
approved settlement-compatible candidates: **0**. Same-event positions with unresolved
exceptional payouts remain residual-risk research candidates only.

## D. Discovery usefulness and review

On the identical 60-definition, 42-pair genuine development corpus, the existing
method and query instruction used actual archived vectors. Inference raw hashes,
model namespace, input-text hashes and exported vectors were revalidated before
insertion into isolated evaluation indices. No new inference was needed for replay.
Assessment clock: **19:41:22.542350 UTC**. Unlisted pairs stay UNLABELED.
[Full per-pair results](evidence/M5L_EVALUATION.json).

| Measure | Deterministic indexed | Existing embeddings | Task-instructed queries |
| --- | ---: | ---: | ---: |
| Recall@20 and @100 | 18/19 | 18/19 | 18/19 |
| Raw labeled precision among returned pairs | 18/25 (72.0%) | 18/26 (69.2%) | 18/25 (72.0%) |
| Unlabeled returned pairs excluded from precision | 2 | 1 | 2 |
| Unflagged labeled precision | 8/8 | 8/8 | 8/8 |
| Distinct labeled ordinary events | 10 | 10 | 10 |
| Additional labeled distinct events vs deterministic | — | **0** | **0** |

These are assistant labels on a purposive development corpus, not independent
production estimates. Warnings remain on ordinary-event controls. The retained
187.5-day administrative-horizon exclusion still misses the departure pair; a
reranker cannot recover a candidate removed before ranking. No bucket saturation
occurred in this tiny corpus, which does not measure production approximate recall.

A separate identical-clock, **250-query production-window** ablation returned 84
rows deterministically in 25.106 seconds and 85 with semantic assistance in 50.335
seconds. The latter had **125 saturated queries**, cap 256, zero vector validation
failures and an incomplete traversal. Seven semantic-only pairs and six displaced
baseline pairs explain the net increase of one. Candidate counts are not new events.
[Actual window, differences and 23-pair review sample](evidence/M5L_PRODUCTION_COMPARE.json).

Assistant inspection of all seven semantic-only pairs found mismatched tenor,
threshold/time, election proposition, selected movie/artist, or polling statistic:
10Y/5Y Treasury lows; Rhode Island conditional Republican ranking/Democrat margin;
Bitcoin $75,750 bucket/$150k crossing; Corpse Bride/Primate; Zach Bryan/Alex Warren;
10Y auction 4.95%/daily yield 4.85%; VoteHub generic ballot/FL-22 election margin.
These are not established additional same-event outcomes. Independent adjudication
remains pending; the sample does not support a venue-wide false-positive rate.

The [42-pair development review packet](evidence/M5L_REVIEW_PACKET.json) contains
retrieved and missed cases, full source excerpts, provenance and blank independent
labels. The production sample selects up to ten stable-hash pairs from each
intersection/difference stratum (10 both, seven semantic-only, six deterministic-only).
It is reproducible and stratified, **not a representative venue-wide probability
sample**. The operator requested preparation with adjudication left pending.
No assistant label is a registry approval.

A reranker might reduce review noise, but no measured benefit justifies deploying
one yet. It cannot fix missing Kalshi vectors, capped prefilters or excluded
horizons. A separate instruction model could extract proposition facets for a
blinded held-out comparison, but must never approve equivalence. Query instructions
alone demonstrated no incremental event yield here. Keep deterministic discovery
available through AI outages and preserve model/text namespaces.

## E. Decision, verification and remaining acceptance

**The most important economic blocker is complementary settlement under exceptional
outcomes**, followed by fresh cross-venue quote synchronization and human fee/account
review. Embedding throughput is not currently the limiting factor in proving a
positive, executable research edge. The current [readiness report](evidence/M5L_READINESS.json)
is BLOCKED; no approval was renewed.

Recommended next milestone: **M5M — zero-money settlement and synchronized-book
validation**. First have the operator adjudicate a complete exceptional-payout map
and fee/mechanics sources for one candidate, recording a rejection if the map
fails. Then capture a bounded hour with current clocked Kalshi data and US quotes,
measure the proportion passing both two-second skew checks, and run the existing
gated evaluator at $5/$25/$100/$500 only on passing evidence. If all sports pairs
retain independent fair-price risk, select a different contract class with explicit
complementary exceptional rules rather than labeling the sports trade strict
arbitrage. This is a recommendation, not authorization to launch that run or M6.

Executed validation: `python -m unittest discover -s tests -v` in `.venv` passed
**426 tests in 19.880 seconds**; [exact test names/output](evidence/M5L_TESTS.txt). New M5L tests cover
scheduler priority/fair slots, restart acknowledgments, source/namespace preservation,
failed/uncommitted vectors, stale/changed definitions, missing/invalid activity,
partial/unknown liquidity, genuine source hashes/clocks, invalid prices/missing
book fields, capital rejections and benchmark method isolation. Live smokes include
all benchmark variants, the 16 MiB diagnostic, two bounded clocked captures, four
fee captures, scheduler planning, identical-window production retrieval and
readiness. `pip check` passed. [Operating/replay commands](M5L_OPERATIONS.md).

Open acceptance items are explicit: current GPU/offload/VRAM/CPU telemetry and
GPU-only timing; interleaved sustained throughput under production resource caps;
independent representative adjudication; full Kalshi vector/query coverage;
settlement/account/fee acceptance; fresh comparable economic observations and
numerical returns at the four commitments. Neither M5L nor M4/M5's sustained
research acceptance is marked complete. No orders, deposits, trading credentials,
new service activation or real-money execution were added.
