# M5M — Quote synchronization and strict settlement eligibility

**The actual 60-minute capture completed, with zero strict synchronized observations.**
The source-backed diagnosis and five review packets are delivered. No strict
settlement-compatible pair was established; human settlement, fee and mechanics
review remains pending, so live economic calculations remain blocked. No funds,
orders, model changes or approval renewals occurred.

## Scope and preservation

M5M concentrates on source/receive clocks, transport continuity and exceptional
settlement. The Qwen3-Embedding-8B Q6_K model, pooling, batch 16, production sidecar
and exact namespace remain unchanged. No inference or full reindex was launched.
All old M5I runs, M5L captures and expired approvals remain preserved. The new
research writes only isolated `data/m5m/` archives; production safety gates remain.

## Why M5L produced zero synchronized comparisons

[Historical diagnosis](evidence/M5M_M5L_DIAGNOSIS.json) reuses the original archived
assessment clocks. These are event-by-event comparisons, distinct from the older
soak report's five ten-second samples per game:

| M5L fixture | Comparisons | Both books individually usable | Receipt skew ≤2s | Source skew ≤2s | Both skew gates plus usable books |
| --- | ---: | ---: | ---: | ---: | ---: |
| NBA Atlanta–New Orleans | 30 | 30 | 17 | 0 | 0 |
| NFL Arizona–Dallas | 13 | 3 | 7 | 0 | 0 |

Every historical comparison failed source skew. Some passed receipt skew; faster
HTTP alone therefore cannot explain or solve all failures. The closest usable
NBA comparison had source/receipt skew 4.530251/2.166873 seconds; NFL had
37.344561/1.342027 seconds. M5L did not record monotonic receive or request-start
clocks, so queueing and RTT cannot be reconstructed retroactively.

The existing Kalshi adapter uses message `sending_ts_ms`, while US uses
`transactTime`. These are different timestamp types. The US schema does not give
`transactTime` a verified send-time/continuity meaning. A current successful HTTP
response does not prove that its underlying order book is current. No timestamp
was relabeled, clock-adjusted or replaced with HTTP Date.

The existing coordinator also polls US metadata and book synchronously while
Kalshi application receives wait. A five-second delay is scheduled **after** the
US poll completes, and metadata/book requests are paced a second apart. Kalshi
reconnects after five seconds without a data message, while its documented
protocol pings occur every ten seconds. Repeated quiet-stream failures increase
reconnect backoff up to thirty seconds. M5M instruments these effects without
altering the production liveness or skew gates.

## Actual hour capture

The selected technical fixture was `KXNFLGAME-26NOV01ARIDAL-ARI` /
`aec-nfl-ari-dal-2026-11-01`, freshly verified open on both venues. The Atlanta
smoke had already closed and is preserved as rejected evidence. Sports remains
residual-risk research, never a strict settlement candidate.

Actual start: **2026-11-01 03:58:58.120659 UTC**. Fixed deadline:
**04:58:58.120659 UTC**. The final heartbeat was **04:58:58.807682 UTC**, after
shutdown and backup: 3,600.687 seconds from start, with the requested 3,600-second
capture budget completed. Twelve segments stopped normally; no run was renewed.
All stream generations are closed. These are historical observations, not current
quotes. [Complete audit and timing distributions](evidence/M5M_CAPTURE.json).

| Measurement | Actual result |
| --- | ---: |
| Raw observations, hashes checked / VALID | 1,683 / 1,683 |
| US polls completed / failed | 578 / 0 |
| US books individually usable at receipt | 538 / 578 |
| Kalshi snapshots / deltas / usable normalized books | 129 / 140 / 269 |
| Connections / pong acknowledgments observed | 129 / 129 |
| Connection endings: data-message timeout / budget | 127 / 2 |
| Audited sequence or market-clock errors | 0 |
| Diagnostic samples / both books individually usable | 2,890 / 617 |
| Samples passing source skew / receipt skew | 110 / 416 |
| Samples passing both skew checks / strict observation policy | **0 / 0** |
| Experimental response-only passes | 108 / 2,890 (3.74%), never economically eligible |
| Raw-byte historical comparison replays / discrepancies | 104 / 0 |
| Transport-to-raw association errors | 0 |

The coordinator's separate ten-second sampling reported 348 samples, 71 with both
books usable and zero passing both skews. Its denominator differs from the
approximately one-second diagnostic sampling above. Diagnostic sample gaps had
median 1.014 seconds, p95 2.121 and maximum 2.391 seconds; these samples do not
establish continuous opportunity duration. All received data frames, HTTP bodies
and normalized depth changes are separately archived.

| Rejection in the 2,890 diagnostic samples | Count |
| --- | ---: |
| Source timestamp skew >2 seconds | 2,775 |
| Receipt timestamp skew >2 seconds | 2,469 |
| Kalshi five-second data liveness not demonstrated | 2,233 |
| Kalshi generation disconnected | 2,127 |
| US source timestamp older than 60 seconds | 228 |
| New Kalshi metadata awaiting a fresh book | 36 |
| Missing/invalid book; unknown skew clocks | 5 each |

Rejections overlap; their counts must not be summed as independent failures.
A quiet TCP/WebSocket connection can respond to a ping while no order-book update
arrives. The unchanged adapter then disconnects after five seconds and applies
backoff. Median generation lifecycle was 6.414 seconds, and median gap between
generations was **30.172 seconds**. Observed pong bounds were median 42 ms, p95
1.105 seconds. This demonstrates transport responsiveness at those observations,
not uninterrupted quote validity throughout a disconnected interval.

### Separate clocks and processing intervals

| Measured interval | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| US request start to complete body receipt | 76 ms | 119 ms | 163 ms |
| Kalshi metadata request to complete body | 142 ms | 162 ms | 175 ms |
| US archival/validation after receipt | 10 ms | 21 ms | 48 ms |
| Kalshi metadata archival/validation after receipt | 13 ms | 20 ms | 35 ms |
| US book request-start interval | 6.183 s | 6.552 s | 6.655 s |
| Kalshi source send to application receipt | 28 ms | 699 ms | 1.137 s |
| Kalshi delta event to source send, 140 deltas | 6 ms | 10 ms | 55 ms |
| Kalshi delta event to application receipt | 28 ms | 680 ms | 820 ms |
| US transaction timestamp to application receipt | **27.263 s** | **64.275 s** | **100.428 s** |
| Comparison assessment wall time | 10 ms | 25 ms | 53 ms |

HTTP includes DNS/TLS/server/network work; it is not pure network RTT. The US
metadata and book calls also include inter-request pacing: the measured pacing
maximum was 918 ms, and complete two-request poll duration reached 1.166 seconds.
The five-second post-completion delay produced the observed six-second cadence.
Body transfer itself was below 1.04 ms, and archival/validation was small relative
to transaction ages and reconnect gaps. SQLite is not the dominant observed
synchronization bottleneck in this run.

Kalshi messages received within 0.5 seconds after a US call completed had p95 send
to application delay **1.111 seconds**, versus **65 ms** for the other messages.
This association is consistent with the synchronous HTTP/pacing loop delaying
application receives. It is not a randomized latency experiment. Application
receive time includes library queueing and is not kernel packet arrival.

All 578 US book responses advertised `public, max-age=30`. An Age header was
present on 489, with median 17 seconds, p95 28 and maximum 29. These headers and
source ages are a material obstacle to a two-second observation requirement;
faster local inference or SQLite cannot make cached depth current.

Local NTP synchronization was confirmed before and after. The actual timesync
reports gave offsets **+2.360 ms / +16.006 ms**, root distances **32.805 ms /
28.022 ms**, and delays **80.681 ms / 49.563 ms**. Local wall-versus-monotonic
elapsed variation at samples was approximately −26.7 to +1.4 microseconds; this
measures consistency of local clocks, not independent absolute accuracy. No wall
clock jump stopped the run. **Remote matching-engine clock synchronization and
offsets remain UNKNOWN.** HTTP Date's coarse wall time, cache behavior and network
uncertainty do not justify a source-clock correction.

There were 140 observed Kalshi depth changes and 129 initial/resnapshot states.
The actual preceding change time is unknown after each reset. US had 86 observed
depth changes, 491 repeated depths and one initial snapshot. Of its 577 transitions,
478 repeated both depth and source time, while **13 advanced source time without
changing depth**. Thus transaction-time changes are not identical to depth-change
events. No source-time regressions were observed in this sample.

At diagnostic sample times, time since the last **observed** depth change had
median/max 11.630/37.438 seconds for Kalshi and 19.896/122.012 seconds for US;
preceding change time was unknown in 1,991/20 samples respectively. These include
rejected/disconnected samples, and US changes are only bounded by polling. They
are not claims of uninterrupted resting liquidity or exact remote last-change
ages. The raw delta event clocks and local monotonic receipts remain available
for narrower replay.

Raw archive, telemetry, clock probes and two verified backups are retained in
`data/m5m/nfl-hour/`. The capture code snapshot is under `code/`. The audit checks
all raw hashes and reconstructs 104 systematic samples through the existing book
validator; no recorded comparison discrepancy occurred. Current diagnostic
reporting additionally derives pacing/body-transfer metrics from the same timing
records, without modifying capture evidence.

## Cache sensitivity and freshness interpretation

[Sixteen-request experiment](evidence/M5M_CACHE_PROBE.json) alternated default and
`Cache-Control: no-cache` request order across eight pairs, using the same official
US book endpoint. Each pair returned identical depth and source timestamps. The
median source age was 52.806705 seconds for default requests and 52.8099455 seconds
for no-cache. Both modes returned `public, max-age=30`; observed Age values reached
28 seconds. The result gives no measured benefit for changing the production
request header. It does not isolate every cache/backend layer or establish that
no order-book changes happened between responses.

The separate experimental `recent-response-sensitivity/m5m-v1` metric omits source
skew and US `STALE_SOURCE` alone, but requires both receipts within two seconds
and preserves other rejections. Its output always retains economic eligibility
false and US continuous validity UNVERIFIED. It is a sensitivity measurement,
not a justified replacement freshness gate. A response-only pass cannot overcome
cached-book or missing-continuity evidence.

Repeated depth is explicitly distinguished from verified continuous validity.
The first snapshot is left-censored: the actual preceding change time is unknown.
Kalshi generation changes reset the observation interval. Repeated US snapshots
only show the same depth at observed times; the source may change and change back
between them. Kalshi deltas retain event time, send time, sequence, exchange clock
and application receipt separately. A successful pong demonstrates transport
responsiveness, not the freshness of an unsequenced US snapshot.

## Five objective non-sports review packets

[Review guide](M5M_REVIEW_GUIDE.md) and [source-backed summary](evidence/M5M_REVIEW_PACKETS.json).
All ten markets reported open in the fresh November 1 captures. Five scoped pairs
span **two economic event families**, not five independently discovered events.

| Pair | Ordinary proposition | Assistant strict screen | Human decision |
| --- | --- | --- | --- |
| [CPI >0.0%](m5m/cpi-zero.md) | October 2026 seasonally adjusted US CPI-U month-on-month | Revision, fallback and discretionary-settlement mismatch | Pending |
| [CPI >0.2%](m5m/cpi-two.md) | Same statistic, different threshold | Same exception family | Pending |
| [CPI >0.5%](m5m/cpi-five.md) | Same statistic, different threshold | Same exception family | Pending |
| [Gas <$3.20](m5m/gas-low.md) | AAA national regular gasoline, any qualifying observation | March issuance versus September 9 start; revision exceptions | Pending |
| [Gas >$4.60](m5m/gas-high.md) | AAA national regular gasoline, any qualifying observation | Issuance window differs; exact issuance boundary and exceptions unverified | Pending |

CPI's ordinary threshold alignment does not cover corrections before Kalshi
expiration, incompatible missing-data calculations, shutdown extensions or
independent fair-price discretion. The US product describes initial-release
settlement; Kalshi's contract uses an expiration value. Gas has a direct observation
window difference, so it is not merely a legal-language concern. The packets
include original definitions, official product PDFs, exact date roles, source
hierarchies, revisions, exceptions, supported sides, cash/fee questions and blank
source-bound registry forms. No assistant comparison became a human approval.

The sports pairs remain **residual-risk research and excluded from strict arbitrage**.
For same-team Kalshi NO plus US YES with independently chosen fair prices, combined
payout is `1 − fK + fUS`; it need not equal $1. The known cancellation/forfeit,
shortened-game and revision differences are retained from M5L.

## Economic gate and capital commitments

No candidate has completed human settlement, fee and mechanics review. Therefore
live bid/ask economics was not run at any budget. Source collection is not a fill
simulation, and no displayed quantity was reported as a realized or guaranteed fill.

| Combined commitment | Gross/net edge | Feasible matched quantity | Per-venue capital / release | Observable opportunity duration | Numeric unmatched-leg exposure |
| ---: | --- | --- | --- | --- | --- |
| $5 | UNKNOWN / BLOCKED | UNKNOWN | UNKNOWN | Not evaluated | UNKNOWN |
| $25 | UNKNOWN / BLOCKED | UNKNOWN | UNKNOWN | Not evaluated | UNKNOWN |
| $100 | UNKNOWN / BLOCKED | UNKNOWN | UNKNOWN | Not evaluated | UNKNOWN |
| $500 | UNKNOWN / BLOCKED | UNKNOWN | UNKNOWN | Not evaluated | UNKNOWN |

Public fee captures produced ten **NEEDS_OPERATOR_REVIEW** packets, not installed
fee profiles. CPI Kalshi series reported quadratic-with-maker-fees and gas series
quadratic, all multiplier 1 with no event override/upcoming change in the captured
responses; US reported 0.0695. Account scope, rounding precision, extras, settlement
fees and the effective review window remain unapproved. The July 7 Kalshi schedule
was read through the browser after direct download returned 429; no new local
full-PDF hash is claimed. No cash-release date is inferred from cutoff, expected
expiration or US endDate.

## Verification and remaining acceptance

`python -m unittest discover -s tests -v` in the repository virtual environment
passed **454 tests in 20.825 seconds**. [Exact names/output](evidence/M5M_TESTS.txt).
Tests cover the experimental/strict separation, exact skew boundary, stale/missing
source times, invalid/partial books, disconnects, repeated depth and generation
reset, monotonic/request association, cooldown/errors, source-hash tampering,
freshness of documents/definitions and refusal of unfinished capture acceptance.
Existing economics, registry, fee, mechanics and semantic tests remain included.
The actual closed NBA smoke and open NFL smoke are preserved separately.

The hour and its raw/replay audit are complete. [Preservation and smoke evidence](evidence/M5M_VALIDATION.json)
records unchanged production database size/mtime and run-file hashes, disabled /
inactive M5I services, and the exact validation commands. This is not a new
all-content hash audit of the production databases. Human review remains pending;
no strict settlement-compatible pair or executable opportunity was established.
M5M's conditional economics acceptance remains blocked, and M4/M5's longer
research-run acceptance is not satisfied. No M6 is authorized.

## Recommended next milestone

The most important **engineering** blocker is a source-verified, timely US book
feed, followed by a Kalshi continuity policy that distinguishes a quiet market
from a dead connection. The most important **economic** blocker remains explicit
complementarity under exceptional settlement; all five reviewed candidates failed
the assistant's strict screen. Neither blocker calls for a model change.

Recommended **M5N: read-only streaming provenance and exceptional-settlement
qualification**. Establish documented US market-data access, timestamp/cache
semantics and reconnect behavior; decouple network receiving from paced metadata
polling using bounded queues and a single archival writer. Test any new quiet-book
policy only as a separately versioned experiment with ping/sequence/snapshot
watermarks, and retain the current gate until evidence and review justify change.
In parallel, find a contract family with matching observation windows, revision
rules and explicit fallback payouts, or obtain authoritative clarification. Have a
human complete settlement, fee and mechanics review before another economic
capture. Do not build orders or deploy a reranker/reindex as a substitute.
