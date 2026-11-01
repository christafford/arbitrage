# M5N independent 15-minute stream comparison — November 1, 2026

**504 of 900 recorded samples (56.0%) passed the timestamp/depth overlap
diagnostic.** The US feed delivered timely NFL updates, but quiet intervals and
reconnect gaps prevented continuous freshness. This is not executable arbitrage
or proof of US sequence continuity. The source-bound Fed review remains pending.

## Run and evidence

The fixed observation window was **17:10:27.476–17:25:27.476 UTC**. Both receivers
stopped; supervisor cleanup finished at **17:25:27.640 UTC**, after 900.164 seconds.
All **900 expected one-second samples** were recorded. Actual spacing was
1.00017–1.00872 seconds, median 1.00024; no missing intervals were filled in.

The selected transport fixture was Kalshi `KXNFLGAME-26NOV01ARIDAL-ARI` against
US `aec-nfl-ari-dal-2026-11-01`. A second US subscription observed the separate
quiet market `rdc-usfed-fomc-2026-12-09-nochng`; its quotes were never combined
with the NFL Kalshi book. Fresh public metadata confirmed open statuses before
launch. Same-event transport selection does not approve settlement equivalence.

Independent child processes used separate archives. The supervisor recorded
clock/sample/segment identity without network polling in the receivers' paths.
Three US segments completed normally, lasting approximately 300, 300 and 298
seconds; startup and between-segment gaps count against coverage. Kalshi exited
130 after the supervisor's scheduled SIGTERM, with its generation closed cleanly.
No service was restarted, deadline renewed or receiver left running.

[Full validation summary](evidence/M5N_OVERLAP_VALIDATION.json) records hashes,
sample denominators, rejections and clocks. Original captures are in
`data/m5n/overlap-15min/`. The complete 900-row historical audit is
`data/m5n/overlap-15min-audit.json`, hash-bound by the summary.

## Observations

| Measurement | Result |
| --- | ---: |
| Timestamp/depth overlap samples | 504 / 900 (56.0%) |
| Rejected samples | 396 / 900 |
| US public book frames, all hash-verified and replayed | 698 |
| Kalshi raw responses, all hash-verified | 1,363 |
| Kalshi normalized books | 1,303 |
| Kalshi generations | 30 |
| Kalshi scheduled resnapshots / message timeouts / final stop | 23 / 6 / 1 |
| Source skew, median / maximum among 896 paired samples | 0.937 / 7.941 s |
| Receive skew, median / maximum among 896 paired samples | 0.931 / 7.862 s |

US NFL supplied **671 books**, all passing the per-message timestamp/depth check.
Their source age at application receipt was **47.8–1,401.7 ms**, median **112.2 ms**.
Within generations, 419 observations changed displayed depth and 249 repeated it;
the three initial snapshots have no preceding depth comparison.

The Fed market supplied **27 books**. Its three initial snapshots were older than
two seconds; the following 24 updates passed their receive-time checks. Its overall
median source age was 132.9 ms, maximum 122.693 seconds. Fresh occasional updates
do not establish that an intervening quiet snapshot remains current.

US library ping/pong RTT at the end of each segment was 45.7, 44.1 and 31.7 ms.
No application heartbeat frames were observed. Local NTP synchronization was
reported before and after; the service reported +16.696 ms offset at both checks.
This is local clock evidence, not a measurement or correction of venue clock error.

## Why samples failed

Reasons overlap; these counts must not be summed into a rejection total:

| Rejection | Samples |
| --- | ---: |
| US source age beyond two seconds | 295 |
| US application receipt older than two seconds | 267 |
| Cross-venue source skew beyond two seconds | 213 |
| Cross-venue receipt skew beyond two seconds | 205 |
| Kalshi source age beyond two seconds | 128 |
| Kalshi receipt older than two seconds | 127 |
| Kalshi disconnected generation | 48 |
| Kalshi message liveness not demonstrated | 18 |
| US book missing at startup/generation changes | 4 |

The full report also retains missing/skew-unknown, US disconnect and newer-Kalshi-
metadata barriers. Historical Kalshi replay had zero replay errors. All 698 US
frames passed hash/decision replay, with no rejected privacy/schema frames.

The main distinction is **fast arriving updates versus aging between updates**:
every NFL US message was timely when received, while 295 later sample instants
had a US source clock older than two seconds. Independent receive loops establish
nonzero overlap in this window, but this is not a controlled before/after latency
benchmark against M5M's earlier, differently sampled REST window.

## Boundaries and next decision

This diagnostic requires each source/receipt age and both cross-venue skews within
two seconds, existing Kalshi validation and US displayed-depth validation. It does
not validate US instrument tick/lot metadata or prove continuous delivery. US
continuity remains UNKNOWN; economic eligibility is always false. A passing-sample
percentage is not continuously verified time, fill probability or profit.

[Checked official stream documentation](evidence/M5N_OVERLAP_API_CHECKS.json) does
not establish a consumed sequence counter or heartbeat watermark that revalidates
quiet books. Keep the existing gates. A documented answer about initial snapshots,
`transactTime`, missed-update detection and quiet-book validity is needed before
proposing another freshness policy. No venue inquiry has been sent.

The [Fed-hold review packet](M5N_FED_HOLD_REVIEW.md) now contains four freshly
captured sources, a conditional-payout matrix and ten blank source-bound review
items. Its [validation](evidence/M5N_FED_HOLD_REVIEW_VALIDATION.json) confirms the
definition rule text is unchanged from the original screen. Cancellation versus
rescheduling, no-meeting fallback, revisions and independent review still prevent
strict classification. Fees, mechanics and reusable cash timing remain unapproved.
The live archive contains zero pairs, fee profiles, research sessions or paper
intents. No economics or order workflow was introduced.

## Verification

`.venv/bin/python -m unittest discover -s tests -v` passed **485 tests in 20.385
seconds**, including 13 comparison tests. [Exact output](evidence/M5N_OVERLAP_TESTS.txt).
Tests include a genuine 10-second replay fixture and hypothetical deadline,
clock, stale/future/partial/invalid data, reconnect/generation, authentication,
retry-budget, forced-cleanup and tampered/missing-evidence cases.

Executed smoke checks: capture/audit `--help`, the actual ten-second independent
capture, its offline audit (8/10 overlap samples), the actual 900-second run and
full offline audit, `pip check`, and source/hash/blank-review validation. The
capture's recorded code hashes still match the implementation. See
[operations and exit-code semantics](M5N_COMPARISON_OPERATIONS.md).

M5N's bounded comparison is complete. Broader feed guarantees, complete settlement
review and executable economics remain open; the milestone is not complete.
