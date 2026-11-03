# M5P — Market-data quality recovery results

Subsequent operator-authorized [cadence/recovery follow-up](M5P_CADENCE_RECOVERY.md)
adds a measured shortlist and bounded in-band snapshots. The results below retain
the original run and its acceptance status.

**The authorized analysis, implementation and 15-minute validation were executed.
The 50% data-quality engineering target was not met; M5P quality acceptance remains
open.** Tests were not weakened. Both validation workers finished at their fixed
deadline, with zero unexplained stops and zero validation-run audit failures.
No one-hour continuation or full-day capture was started or scheduled.

The new run observed **347/1,788 passing stream samples (19.41%)**, compared with
M5O's **385/116,593 (0.33%)**. Its valid local market-state coverage was
**346.689932 / 1,800 pair-seconds (19.26%)**. Different markets, time windows and
sampling cadences prevent interpreting this as a controlled performance gain.
Neither statistic is a market-profitability claim.

## Fixed validation and targets

Window: **November 3, 2026, 16:19:51.923924–16:34:51.923924 UTC**.
Cleanup and replay finished at 16:35:02.082174 UTC; collection/sample eligibility
did not extend the deadline. Archive: `data/m5p/validation-20261103/`.
Scope and commands were shown before capture. Public definitions and open state
were checked immediately before launch; all four instruments were open and had
two-sided displayed depth at selection. House and Senate are distinct chambers,
not duplicate thresholds. Kalshi reported approximately 3.0m and 4.7m contracts
of 24-hour activity during initial screening. US volume was absent and remains
UNKNOWN. Reported volume did not predict update cadence adequately.

| Engineering metric | M5O | M5P validation | Assessment |
| --- | --- | --- | --- |
| Passing samples | 385/116,593 = 0.33% | 347/1,788 = 19.41% | Below 50% target on both selected pairs |
| Early worker stops | 5/11, now explained | 0/2 | Zero unexplained stops |
| Worker/segment audit failures | 0/653 original audits | 0/2 paired-worker audits | Target met for validation |
| Raw integrity | 1,224,595 historical hashes rechecked | 3,442 SQLite raw responses, including four preflight responses; 387 US wire frames verified | Fully replayable retained evidence |
| Quote freshness | Frequently rejected | Source/receipt age, skew, expiry and lifecycle reasons measured | Two-second requirements unchanged |
| Gross signals | One Brooklyn sample | 118 Senate samples, 103 distinct source states | Recorded; not fills or verified net opportunities |

The first development smoke failed two journal-hash audits due to float/Decimal
serialization. Its evidence is preserved. The corrected second smoke passed both
audits before the 15-minute validation. These development failures are explicitly
separate from the zero-failure validation result.

## Wall-clock coverage, separate from sample counts

| Pair / US channel | Passing samples | Sample rate | Valid local-state seconds / 900 | Wall-clock coverage |
| --- | ---: | ---: | ---: | ---: |
| House Democratic control / stream | 109/895 | 12.18% | 103.095729 | 11.46% |
| Senate Republican control / stream | 238/893 | 26.65% | 243.594203 | 27.07% |
| House / REST comparison | 5/895 | 0.56% | 4.162453 | 0.46% |
| Senate / REST comparison | 0/893 | 0% | 0.099736 | 0.01% |

The planned one-second denominator is 1,800 pair-samples; 347/1,800 = **19.28%**.
The 12 absent sampling slots are not silently removed from wall time. The short
Senate REST passing interval fell between polling samples: zero passing samples
does not imply exactly zero observable passing time.

Coverage integrates the event journal from the common start to deadline, with
cuts at source/receipt/metadata expiry, market close, pending validation,
invalidation and disconnect. It includes startup, processing and receiver gaps.
It is not passing-sample count multiplied by a polling interval. Rejection-seconds
can overlap and are not additive downtime.

This is **local state passing the existing checks**, not proof of continuous
exchange validity. US sequence/gap detection remains UNKNOWN, and no heartbeat
refreshes a quiet book. M5O did not record every availability transition, so its
comparable wall-clock metric remains **UNKNOWN**. The original five-second
poll-completion sampling also differs from M5P's independent one-second sampler.

## What limits the new coverage

The US stream emitted **121 House books and 266 Senate books**, with 109 and 246
observed depth changes. Their receipt-time source-age medians were **0.104 s**
and **0.103 s**; p95 values were **0.154 s** and **0.191 s**. New books generally
arrived promptly, but long gaps left them stale between updates:

| Stream measure | House | Senate |
| --- | ---: | ---: |
| Median interarrival | 1.960 s | 1.606 s |
| p95 interarrival | 33.548 s | 12.955 s |
| Maximum interarrival | 78.238 s | 36.933 s |
| US source-age rejection time | 715.419 s | 581.830 s |
| Kalshi source-age rejection time | 255.494 s | 193.043 s |
| Kalshi timeout/backoff reason time | 213.854 s | 21.264 s |
| Kalshi periodic-resnapshot reason time | 25.885 s | 31.380 s |

Even giving every House frame a fresh, non-overlapping two-second validity window
would cap its coverage at **242/900 = 26.89%**, before any Kalshi, metadata or skew
failure. Thus this observed feed cadence cannot support the 50% target with the
unchanged requirements. This establishes sparse observable updates in this window;
it does not establish exchange-wide inactivity or rule out undetectable US drops.

Kalshi had **10 House / 9 Senate message timeouts**, plus **19 / 23 periodic
resnapshots**. The collectors recovered within the same fixed window; neither
worker stopped early. These are local policy/reconnect contributions, distinct
from US sparse updates. There were zero HTTP request failures and no invalid-price
book samples. All US REST book responses still advertised `public, max-age=30`.
The US streams showed protocol pong RTT observations around 36–47 ms at segment
ends, but no application heartbeat frames; pongs do not refresh book timestamps.

Host synchronization checks passed before, during and after the run. The final
host NTP report showed +831 µs offset and 2.426 ms jitter. These are local host
observations, not measurements of exchange matching-engine offset. Quote send,
transaction, receipt and local availability clocks remain distinct.

### Before/after source age and skew

The historical figures below are examples from the complete per-pair metrics,
not a matched-market experiment. All values are median / p95 seconds at samples.

| Scope | Kalshi source age | US source age | Source skew |
| --- | ---: | ---: | ---: |
| M5O Brooklyn | 0.939 / 11.114 | 17.899 / 31.666 | 15.619 / 30.336 |
| M5O Chicago | 2.526 / 30.407 | 19.529 / 39.462 | 14.210 / 33.062 |
| M5O Fed hold | 16.464 / 33.539 | 42.209 / 167.143 | 26.737 / 151.506 |
| M5P House stream | 0.589 / 28.251 | 10.478 / 56.149 | 13.079 / 55.698 |
| M5P Senate stream | 0.896 / 3.931 | 3.347 / 15.998 | 2.197 / 14.812 |

M5P US REST source-age medians were 30.403 s for House and 24.651 s for Senate.
Complete source/receipt age and both skew distributions retain their own nonmissing
denominators in [historical metrics](evidence/M5P_HISTORY_METRICS.json) and
[validation metrics](evidence/M5P_VALIDATION_METRICS.json).

## Historical recovery findings

All **1,224,595 M5O raw-response hashes** match. The **653 original segment audits**
remain PASS; this does not claim that all 653 expensive semantic replays were
newly rerun. Three Brooklyn samples were newly reconstructed using original
raw bytes and committed-reader frontiers, with exact agreement.

[The per-pair breakdown](M5P_REJECTIONS.md) and [exact CSV](evidence/M5P_REJECTIONS.csv)
separate primary attribution from simultaneous additional reasons. Of 116,593
observations, 116,208 were rejected. There were 1,355 processing-error samples;
their unassessed additional venue failures remain UNKNOWN. Primary counts reconcile
to all observations. Primary attribution is a declared reporting hierarchy, not
a claim that one reason is the sole cause.

The three largest separately addressable causes are:

1. **US cached/source-old REST books.** Source age exceeded the two-second gate in
   114,308 observations. All 116,377 captured book responses advertised a 30-second
   cache lifetime; 104,473 adjacent responses within segments were byte-identical.
   Typical HTTP response medians were only 67–81 ms, so fast responses did not
   establish fresh source data. Streaming removes this REST cache path but does
   not make quiet books current.
2. **Kalshi quiet-feed timeout/reconnect gaps.** 81,462 observations carried
   disconnected-state failures; 94,460 failed the source-age check. There were
   16,115 message timeouts and 2,432 periodic resnapshots. Maintaining an observable
   current snapshot without repeated connection teardown deserves a separate
   tested recovery design; no existing freshness gate was loosened here.
3. **Omitted-ladder parser failures and early worker endings.** All five final
   segments show the same failure chain, totaling 28 omitted-side rejected
   snapshots and 12 terminal consecutive errors per worker. Every worker stopped
   before its later reported trading close. The missing full-window observations
   cannot all be attributed to this bug—subsequent finalization, startup and audit
   gaps also matter. [Exact stop chronology](M5P_WORKER_STOPS.md).

The existing four-example ladder repair remains verified; M5P adds Toronto's fifth
genuine regression. Corrected partial books remain unusable, and all historical
REJECTED records are preserved. No expired market or service was restarted.

[The Brooklyn reconstruction](M5P_BROOKLYN.md) confirms $0.55 Kalshi NO plus
$0.44 US YES at the one passing sample. Its neighbors fail US source freshness.
The gross discrepancy is supported at that instant; persistence and net
profitability are not established.

## Repeated valid gross signals, if any

Senate produced **118 positive conditional samples**, representing **103 distinct
source-state combinations** and **52 sample clusters**. The first was at
16:20:02.382457 UTC and the last at 16:34:47.966664 UTC. The longest adjacent
positive-sample cluster spans **5.079393 seconds**; this is not continuously
verified opportunity duration. House and both REST comparison channels had none.

The largest quoted case used **505 matched units**, $373.70 Kalshi NO and $126.25
US YES, for **$499.95 pre-fee quote cost** and **$5.05 gross indicative gain** under
matching ordinary payouts. A hypothetical combined one-cent-per-unit fee would
consume that entire gain. Actual fee applicability, collateral, fills and cash
release remain UNKNOWN; repeated samples are never summed as realized profit.

Both election pairs remain **UNVERIFIED / CONDITIONAL**, with zero STRICT pairs.
Kalshi's early media-call and February 1 officeholder fallback differ from US
majority, independent-caucus, January 4 and chamber-organization rules. These can
produce different exceptional payouts. No human settlement decision was inferred.

## Verification and remaining work

The pre-capture full suite passed **531 tests**. The final command
`.venv/bin/python -m unittest discover -s tests -v` executed **541 tests**, all
passing in **23.630 seconds**. [Exact final names/output](evidence/M5P_TESTS.txt)
and [pre-capture output](evidence/M5P_TESTS_PRECAPTURE.txt) are archived.
Both completed worker archives were replayed again with the final code: **6,123
events, 3,576 channel-samples, every coverage interval, 3,438 per-worker SQLite
raw responses and 387 US frames** verified. Four additional preflight responses
were hash-checked. CLI help and the explicitly hypothetical demo/report smoke
also executed successfully. [Commands and evidence](evidence/M5P_VALIDATION.json).

Post-launch review added schema/deadline consistency checks, isolation of a REST
book-request failure from independently valid stream metadata, and stricter
verified-clock bookkeeping for invalid books. These paths have fault tests.
Running processes were not hot-reloaded; frozen launch code and hashes are retained.
No HTTP failures or invalid-book samples occurred in this validation, and the final
code reproduces both recorded results. The ordinary field/grid/freshness gates,
production schema, model namespaces and approval logic were not changed.

Prioritized remaining work:

1. **Select by measured update cadence, not reported volume alone.** A separately
   authorized next window should screen actual source update frequency and two-sided
   depth before choosing its fixed scope. Do not lower the two-second requirements
   or extrapolate this purposive election sample to all markets.
2. **Investigate Kalshi in-band snapshot recovery** using its documented snapshot
   command, retaining sequence/clock validation and source timestamps, instead of
   assuming quiet connections or transport pongs make books fresh. Implement and
   test that separately before another bounded capture.
3. **Resolve US continuity/quiet-state semantics with source evidence.** The checked
   documents do not justify a heartbeat/response-only freshness exemption. No such
   experimental policy was implemented. Undetected feed gaps and exchange-clock
   offset remain unknown.
4. **Independently review the repeated Senate signal's settlement, fees and
   mechanics** only as conditional research. Its repeated gross prices do not
   override the failed data-quality target or authorize live-money work.

The optional hour is not prepared because the initial coverage target failed.
All old M5I units remain disabled; no service, production index, credential,
funding ceiling or M6 boundary was changed. [Operations and replay](M5P_OPERATIONS.md).
