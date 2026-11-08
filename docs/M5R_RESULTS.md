# M5R — Economic viability and market-data feasibility

Executed November 8, 2026 UTC. **Recommendation: pause broad arbitrage infrastructure
development; retain a narrow, offline contract-and-fee research path.** The best
repeated historical spread does not cover the published taker-formula sensitivity.
Measured local processing costs do not explain the coverage shortfall. No verified
net arbitrage, executable allocation, or profitable trade cycle has been established.

M5R's offline decision-report scope is complete. This does **not** complete M5P/M5Q
quality acceptance, independent settlement/fee/mechanics review, or authorize M6.
There was no new quote capture, inference, credential use, service start, order,
funding operation, registry approval, or production gate change.

## Historical fees and economic findings

[Machine-readable calculations](evidence/M5R_ECONOMICS.json) cover all **196** accepted
operational gross-positive M5Q observations, retaining their original classes and
provenance. Five development positives remain outside this population. The five
representative best-$500 states have full depth walks at $5, $25, $100, $500 and
$3,000, flexible/equal/75:25 funding, and a separate $150 reserve scenario. Best-$500
selection is disclosed; it is not assumed optimal at $3,000 across all observations.

[Raw official-source manifest and fee review](evidence/M5R_API_CHECKS.json) separate
contemporaneous metadata, earlier schedule captures, and retrospective retrieval:

- The official [Kalshi schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf)
  states July 7, 2026 effectiveness, a general taker coefficient of `0.07 × multiplier`,
  and no exchange settlement fee. The November 8 HTTP download returned **429**;
  its error body is retained. The existing operator-supplied PDF, SHA256
  `c326a69f596a11e8f8be2620402d39a8d4823920c21cc97c93a114d862699601`, is copied
  unchanged; its original retrieval time remains unknown. The official browser
  reader still displayed the July 7 schedule. No successful new PDF download is claimed.
- Sixteen fresh public Kalshi responses cover `CONTROLS`, `KXNBAGAME`,
  `GOVPARTYGA`, and `KXAAAGASMAX`: series, event, historical series changes and
  event changes. Each reports multiplier **1**, supported quadratic fees, no
  current event override, and empty change arrays with completed event pagination.
  Empty history and current metadata do not independently establish the operator's
  historical account/FCM charges, waivers, or membership precision. Original market
  responses contain no fee waiver field; absence is not an independently reviewed waiver decision.
- The US schedule captured **November 1 03:59:54.202641 UTC** advertises standard
  `0.0695` and an October 19 effective date. It still carries an already-dated
  October 28 combo notice. Each of the five representative historical US market
  definitions independently contains `feeCoefficient: 0.0695`. These are single
  contracts, not table-tennis or combos. Account overrides and extras remain unreviewed.
- The [current US fee page](https://docs.polymarket.us/fees.md), archived November 8,
  announces November 6 13:00 ET taker tiers `0.095/0.085/0.075/0.0695`, onboarding
  exceptions and order-insertion-time coefficient assignment. It still calls these
  “upcoming” alongside the older table. **Do not reuse historical 0.0695 as a
  verified current account rate.** No production fee profile was changed or approved.
  The separate [prospective sensitivity](evidence/M5R_PROSPECTIVE_FEES.json) applies
  those coefficients to historical prices only.

Actual historical fees, account applicability and actual net profit therefore remain
**UNKNOWN**. Calculations below explicitly assume cash-long taker fills, Kalshi
multiplier 1, US coefficient 0.0695, zero settlement/account extras, no volume
discounts, and a $1 ordinary combined payout. They are **hypothetical sensitivities**.
Published exceptions, maker rebates and negotiated tiers are not credited.

### November 3 Senate control

At `2026-11-03T16:20:02.382457+00:00`, archived Kalshi NO **$0.74** plus US YES
**$0.25** costs $0.99 per matched unit. The fee break-even ceiling is **$0.01 per
unit**, shared by both venues and all other costs. Before rounding, assumed fees
are $0.013468 Kalshi plus $0.01303125 US: **$0.02649925 per unit**. Even Kalshi's
assumed fee alone exceeds this spread. An unrounded combined reduction exceeding
62% would be needed merely to reach zero, before slippage or leg risk.

| Quote-only budget | Matched units | Kalshi / US purchase cost | Gross spread | Hypothetical fees, one fill per level | Hypothetical net |
| ---: | ---: | ---: | ---: | ---: | ---: |
| $5 | 5 | $3.70 / $1.25 | $0.05 | $0.1374 | **−$0.0874** |
| $25 | 25 | $18.50 / $6.25 | $0.25 | $0.6667 | **−$0.4167** |
| $100 | 101 | $74.74 / $25.25 | $1.01 | $2.6803 | **−$1.6703** |
| $500 | 505 | $373.70 / $126.25 | $5.05 | $13.3814 | **−$8.3314** |
| $3,000 | 3,030 | $2,242.20 / $757.50 | $30.30 | $80.2881 | **−$49.9881** |

These quantities maximize gross spread within **purchase-only** capital; fees can
exceed the stated budget. Direct-member Kalshi precision is assumed in this table.
The evidence also calculates non-direct cent precision, one-contract partitions,
minimum-lot no-rebate fee bounds, and quantities funded including those bounds.
Kalshi's [rounding accumulator](https://docs.kalshi.com/getting_started/fee_rounding)
and the US per-fill half-even cumulative cap are retained. One-contract fragmentation
changes the $3,000 scenario to **−$40.8081**, still negative. The conservative
no-rebate bound is a funding stress case, especially for non-direct fractional
fills; it is not a predicted commission. This is not an exhaustive optimization
over every possible fill partition.

The November 6 coefficients, applied hypothetically to this same 3,030-unit state,
produce per-level net **−$49.9881 / −$53.1181 / −$58.7981 / −$64.4781** for
`0.0695 / 0.075 / 0.085 / 0.095`. None is an actual current account quote.

### Other positive evidence

| Population | Observations | $3,000 gross-optimal quantity range | Hypothetical per-level net range |
| --- | ---: | ---: | ---: |
| Original Senate, CONDITIONAL | 118 | 1,173–3,030 | −$49.9881 to −$19.3670 |
| Later Senate, DISCOVERY | 69 | 100–3,003 | −$47.2863 to −$1.4717 |
| Georgia governor, DISCOVERY | 5 | 667 | −$6.1480 |
| Brooklyn–Indiana, CONDITIONAL | 1 | 3,030.30 | −$74.0870 |
| Gas above $4.60, DISCOVERY | 3 | 8.01–8.02 | −$0.1251 to −$0.0465 |

All **196/196** are negative under this declared scenario; this is not proof about
every fee tier, partition or future market. Georgia's best $3,000 gross opportunity
uses only $660.33 before the next marginal depth is unattractive. Gas uses $7.8584
at its best state. Gas's $0.1616 fee allowance is about 2.015 cents/unit; fractional
fee rounding could change a hypothetical result, but its **known observation-window
mismatch already defeats the hedge**. Georgia's officeholder/election-winner mismatch
also remains. Later Senate's best-$500 state permits only **$0.001/unit** combined
fees; Brooklyn permits $0.01/unit and has only one passing positive point.

## Market-data feasibility

All three M5Q workers were reconstructed from raw bytes again: **2,257 events,
1,794 channel samples, 1,282 SQLite raw responses and 375 US frames**. Every audit
passed. The fixed November 8 window remains **06:23:55.859543–06:28:55.859543 UTC**.
Strict two-second coverage matches the original result exactly.

| Pair | Strict valid wall time | Kalshi source-age failures | US source-age failures | Cross-venue skew failures | Receipt-age failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lakers–Detroit | 123.802199s / **41.2674%** | 89.052993s | 131.433074s | 121.063861s | 169.009402s |
| Cincinnati–Atlanta | 111.218708s / **37.0729%** | 100.444164s | 124.337199s | 104.415918s | 176.197638s |
| Las Vegas–San Francisco | 30.468174s / **10.1561%** | 146.157415s | 221.534183s | 203.361403s | 253.047253s |

Columns overlap; receipt age is pooled across both venues. They must **not** be
added. Exclusive failure-combination bins in the evidence reconcile to exactly
300 seconds per pair including valid time. Partitioning failed time by source-age
membership gives US-only / Kalshi-only / both / neither respectively:

- Lakers: **83.606287 / 41.226206 / 47.826787 / 3.538521 seconds**.
- Cincinnati: **81.084556 / 57.191521 / 43.252643 / 7.252572 seconds**.
- Las Vegas: **110.901303 / 35.524535 / 110.632880 / 12.473108 seconds**.

“US-only” here means only the US **source-age** condition is failed; receipt/skew
conditions can fail at the same time. The leading venue-specific limitation in all
three is insufficiently frequent fresh US timestamps, with Kalshi gaps and their
overlap also substantial. This attributes rejection conditions, not unobservable
exchange causes: quiet books, gateway publication behavior and missing continuity
guarantees cannot be fully separated from these captures.

| Pair | US increasing-source-gap p95 / max | US source-to-receipt p95 | Kalshi source-to-receipt p95 | Kalshi receipt-to-availability p95 |
| --- | ---: | ---: | ---: | ---: |
| Lakers | 6.620240s / 15.214274s | 181.774ms | 101.162ms | 27.696ms |
| Cincinnati | 5.821762s / 6.082079s | 159.378ms | 97.381ms | 26.901ms |
| Las Vegas | 23.752285s / 64.869719s | 165.383ms | 38.458ms | 28.095ms |

These are event-weighted observations of reconstructed books, not packet latency
SLAs. US local availability p95 is 4.617–7.094ms. Two admitted US book events were
already older than two seconds on receipt (one Cincinnati, one Las Vegas); no
Kalshi admission was. Most loss accumulates **between** fresh observations rather
than during local processing. Kalshi increasing-source-gap p95 is about 5.07s,
including the configured recovery behavior; it is not solely a venue activity measure.

Startup/missing-state overlap was 1.108021 / 6.185219 / 21.181146 seconds. Metadata
failure contributed 2.882022 overlapping seconds only in Las Vegas. Local barriers
and disconnect states overlapped 5.714682 / 5.516046 / 4.272933 seconds. In the
isolated category-removal diagnostic, ignoring **all** those barrier codes while
retaining the other failures adds just **2.430500 / 2.000068 / 0.227082 seconds**,
or **0.8102 / 0.6667 / 0.0757 percentage points**. This is an arithmetic ceiling
for removing the recorded blockers, not a simulated faster collector or permission
to bypass validation. It cannot reach the existing 50% target, let alone 60% headroom.
No age threshold or heartbeat-refresh policy was proposed or changed.

### US WebSocket and gRPC review

The [retail markets stream](https://docs.polymarket.us/api-reference/websocket/markets)
still exposes book snapshots and timestamps without a consumed market sequence,
replay cursor, or no-change validity watermark. A transport heartbeat does not
refresh either book clock. Continuous exchange validity remains **UNKNOWN**, even
inside locally valid two-second intervals.

The [gRPC market-data service](https://docs.polymarket.us/streaming-endpoints/market-data-stream)
documents initial snapshots and ongoing updates, dynamic subscriptions, and
`read:marketdata` Auth0 access. The official linked proto ZIP was successfully
archived and inspected without generating or executing code. Its
`slow_consumer_skip_to_head=false` default disconnects a slow consumer instead of
dropping missed messages: a useful, stronger **specific** safeguard. However,
`MarketDataUpdate` has no sequence/checksum/replay token and `Heartbeat` is empty.
[Reconnect guidance](https://docs.polymarket.us/streaming-endpoints/streaming-best-practices)
says to take a new market snapshot; execution-stream resume tokens do not apply
to market data. No documented quiet-book watermark or proven cadence improvement
was found. Published scale descriptions also mix decimal-place and divisor wording;
a future adapter needs independently verified instrument scales and fixtures.
No gRPC connection or new credential acquisition was attempted.

Better **time-local event selection** is plausible: earlier Senate holdout coverage
was 82.15%, and a November 4 NBA screen reached 66.54% for one pair. Those historical
results do not transfer to these overnight November 8 contracts. Faster validation
is not supported as the main remedy here. A gRPC implementation or another lengthy
capture has no demonstrated economic justification at present.

## $3,000 capital efficiency and execution risk

| Original Senate allocation assumption | Gross-optimal units before fees | Purchase cash used | Gross | Units funded with direct-member conservative fee bound |
| --- | ---: | ---: | ---: | ---: |
| Flexible ex-ante split | 3,030 | $2,999.70 | $30.30 | 2,932 |
| $1,500 each venue | 2,027 | $2,006.73 | $20.27 | 1,973 |
| $2,250 Kalshi / $750 US | 3,000 | $2,970.00 | $30.00 | 2,851 |
| Flexible split, $150 untouched reserve | 2,878 | $2,849.22 | $28.78 | 2,785 |

Flexible means both amounts were funded **before** the opportunity. It assumes no
instant transfer, cross-venue netting, collateral offset or proceeds reuse. The
2,932-unit conservative case needs **$2,228.32 Kalshi and $771.21 US**, $2,999.53
total including its fee bounds, and has a **−$67.53** hypothetical lower-bound net.
Unknown account extras and required reserve can reduce admissible quantity further.
No account balance, deposit, actual buying power or trading approval was inferred.

At the representative 3,030-unit quote, one unmatched leg can lose **$2,242.20**
or **$757.50**, plus fees. Unequal fills leave `abs(q_k − q_us)` units unhedged.
Exceptional inconsistent payouts can lose both purchase costs. The direction is
Kalshi long NO plus US long YES; synthetic US NO/short routes remain unsupported.

The source-bound Senate **expected expiration** was February 1, 2027 at 15:00 UTC,
about **89.94 days** after the observation. It is not a cash-release guarantee.
Brooklyn's expected expiration was about **2.22 hours** later; Georgia's about
**71.58 days**, gas's about **59.51 days**. US `endDate` is administrative. Combined
settlement and reusable cash dates remain unknown, so no turnover or annualized
return is calculated. Even a fee-free $30.30 gross spread on nearly $3,000 is only
about 1.01% for that single conditional commitment.

The original Senate's 118 positives comprise 103 distinct depth/source states and
52 sample clusters; the longest sampled span is 5.079393s. At the representative
sample the next clock expiry is only 1.616812s away. Neither fact establishes
continuous executable duration. Across those 118 states, gross-optimal $3,000
quantity ranges from 1,173 to 3,030. Repeated observations cannot be multiplied into
profitable cycles or simultaneous independent capacity.

## Candidate strategy and decision

No reviewed class currently satisfies all the economic, settlement and data-quality
requirements. The strongest **research** classes, in order of review priority, are:

| Class | Why retain for research | What blocks progression |
| --- | --- | --- |
| Scheduled, objective macro-release thresholds | Exact statistic, period, units and threshold can be matched deterministically; scheduled release can shorten event exposure | [CPI packet](m5m/cpi-two.md) has correction and no-publication fallback conflicts; no verified net spread or sustained coverage |
| Scheduled central-bank decision outcomes | One decision and explicit rate boundary can be compared; concentrated event time | [Fed hold packet](M5N_FED_HOLD_REVIEW.md) has postponement/cancellation/source ambiguities; earlier quiet-feed coverage was poor; cash release unknown |
| Short-dated single-game winners | Deterministic league/team/date identity, observable depth and prior isolated coverage successes | Sports discretionary exceptional settlement remains residual-risk-only; the Brooklyn one-cent spread fails fees; current three-pair screen failed |

Senate is the best **historical measurement benchmark**, not the best next capital
deployment: fees exceed spread and its source expiration implies long exposure.
Georgia officeholder and gas window mismatches are exclusions, not discovery wins.
None of the three classes is approved strict arbitrage; sports stays excluded from it.

Selection should first require explicit ordinary proposition identity and reviewable
exceptional payouts, then source-backed release timing and conservative fee-adjusted
depth under separate venue caps. Only candidates surviving those checks merit a
fresh cadence screen and independent holdout. Recent volume is a nomination hint,
not evidence of two-second coverage; missing inputs are UNKNOWN and cannot be
converted into a favorable ranking score. All real approvals remain source-bound
human decisions.

Existing AI comparisons supply no reason to expand inference now. The
[M5O ablation](evidence/M5O_AI_ABLATION.json) returned 32 deterministic and 32
semantic-union candidates from a bounded 100-query window; two semantic-only
ranked rows had proposition/date conflicts and yielded no AI-only selected pair.
[M5L's 250-query comparison](M5L_RESULTS.md) returned 84 versus 85 rows, with seven
semantic-only differences, 125 saturated queries and no independently established
additional event yield. [M5I's small development corpus](M5I_COMPATIBILITY_RESULTS.md)
favored deterministic raw recall 19/19 versus indexed 18/19. Assistant labels and
bounded samples do not establish general model quality. Keep deterministic research
available; do not change production namespaces, models or reindexing budgets.

**Pause** collector/AI expansion and live-execution development. Continue only
targeted offline rule/fee review if desired. A later capture proposal should name
a compatible short-horizon contract, an independently supported fee cushion after
depth and reserves, and a specific measured data question. A future gRPC probe
would need documented access and protocol/scale validation first; its existence
alone cannot justify relaxed freshness. No further run is prepared or implied.

## Verification and remaining unknowns

`python -m unittest discover -s tests -v` executed in `.venv`: **609 tests passed**,
including 16 new M5R tests. [Full log](evidence/M5R_TESTS.txt). New genuine fixtures
retain historical Senate quote provenance and 26 exact public fee/metadata responses.
Hypothetical tests exercise missing/stale/partial data, invalid price/lot inputs,
cash caps, rounding/fragmentation, unknown histories and pagination, heartbeat
expiry, local barriers, latency separation and genuine raw replay parity.

The offline command re-audits the three original workers and verifies **4,423
source/evidence/code files unchanged**. [Operations and reproduction](M5R_OPERATIONS.md)
describe the failed development attempt and successful runs without relabeling them.
The repeated analysis has exact economics/attribution parity;
[final verification](evidence/M5R_VERIFICATION.json) also records 46 verified source
files and the final code/artifact hashes.
Production economics, collection, approval gates and all expired deadlines are intact.

Open: actual historical/current account fees and exceptions; exceptional settlement
equivalence; cash availability; fills and leg execution; a qualifying sustained
current cohort; US continuous-state guarantees; independent label adjudication;
and any viable positive net opportunity. M5R's decision does not resolve those gaps.
