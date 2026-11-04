# M5P independent 15-minute collector validation

The operator explicitly authorized the proposed validation on November 3, 2026.
This executes the existing new collector without changing its behavior, model,
source/receipt/skew/metadata checks, settlement decisions or money safeguards.
All pairs remain DISCOVERY / UNVERIFIED. Prior run deadlines and evidence remain
preserved. A run finishing is not evidence that its acceptance targets passed.

## Registered scope and acceptance

[The plan](evidence/M5P_HOLDOUT_PLAN.json) was saved before the fresh screen or
holdout. Recheck the historical Senate and House control shortlist with current
metadata and displayed two-sided depth, then a separate five-minute cadence
screen. Freeze two or three eligible pairs before the new 900-second holdout.
No swaps, exclusions or settings changes are allowed during holdout. Preserve
all observations, including failures. The primary criteria are, per pair:

- At least 50% passing recorded samples and at least 50% valid local market-state
  wall time over the complete 900-second denominator.
- At least 50% valid wall time in each 450-second half.
- Zero unexplained worker stops, zero audit failures, and full raw/event/sample/
  interval replay. Explicitly report missing planned one-second sampling slots.

These are engineering thresholds, not venue requirements, market-performance
claims or proof of continuous US exchange validity. Quote source/receipt ages and
cross-venue skew remain capped at two seconds. Heartbeats/pongs cannot refresh
books. Gross or net profitability is not an acceptance criterion for this capture.

Configuration remains `inband-snapshot`: five-second quiet-feed snapshot requests,
25-second periodic snapshots, five-second response timeout, at least five seconds
between requests, and bounded reconnect fallback. Planned connection rotation
remains at 45 seconds or 1,000 frames to renew metadata and bound replay. The
implementation is the previously committed and tested code, not a new policy.

Eight current [official document captures](evidence/M5P_HOLDOUT_API_CHECKS.json)
are byte-identical to the cadence/recovery check. Public source responses are
archived before conversion, with the same adapter schemas and UTC receipt clocks.
Existing local credentials sign only the fixed market-data handshakes.

## Commands and evidence locations

All directories below are new and single-use; no expired run is restarted.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m5p_select.py \
  --proposals data/m5p/holdout-20261103/proposals.json \
  --output data/m5p/holdout-20261103/selection-01
.venv/bin/python scripts/m5p_observe.py run \
  --candidates data/m5p/holdout-20261103/selection-01/candidates.json \
  --output data/m5p/holdout-20261103/screen-01 --seconds 300 \
  --kalshi-recovery-policy inband-snapshot
.venv/bin/python scripts/m5p_cadence.py \
  --source data/m5p/holdout-20261103/screen-01 \
  --output docs/evidence/M5P_HOLDOUT_SCREEN.json
```

After eligible pairs are frozen in `frozen-candidates.json` and immediately
rechecked open, the separately authorized validation command is:

```bash
.venv/bin/python scripts/m5p_observe.py run \
  --candidates data/m5p/holdout-20261103/frozen-candidates.json \
  --output data/m5p/holdout-20261103/validation-01 --seconds 900 \
  --kalshi-recovery-policy inband-snapshot
```

The supervisor records start/deadline and source hashes before launching workers.
The plan does not move either deadline. Any optional one-hour validation will be
a separate concrete proposal only after these targets pass; it is not launched
or scheduled automatically. Final measurements will be recorded below after the
fixed window and offline audit finish.

## Fresh screen and frozen selection

The five-minute screen ran November 3 **23:43:00.563981–23:48:00.563981 UTC**.
Both workers reached their deadline, exited 0 and passed replay. Senate passed
83.61% of recorded samples and 81.42% wall time (halves 82.69% / 80.15%); House
passed 65.77% of samples and 65.83% wall time (halves 71.20% / 60.46%).
[Exact screen evidence](evidence/M5P_HOLDOUT_SCREEN.json).

Both pairs were freshly checked open with two-sided depth again in `selection-02`.
Their definition fingerprints matched the screened definitions. The
[frozen candidates](evidence/M5P_HOLDOUT_FROZEN_CANDIDATES.json) bind the screen and
registered-plan hashes and prohibit mid-run substitution. The holdout uses this
separate later window; screening observations never enter its acceptance counts.
[Exact fixed holdout configuration](evidence/M5P_HOLDOUT_CONFIG.json).

## Final result — Senate passed; House failed

**The independent two-pair validation did not meet all predeclared criteria.**
Senate passed; House missed the sample target and the second-half wall-time target.
Both workers reached their fixed deadline, exited 0 and passed complete replay.
No target or gate was weakened. No optional hour was prepared, started or scheduled.

The holdout ran **November 3 23:49:13.158062 through November 4
00:04:13.158062 UTC**—**6:49:13–7:04:13 p.m. EST on November 3**.
Supervisor cleanup and worker replay finished at 00:04:47.051754 UTC, without
extending sample or event eligibility past the original deadline. All processes
stopped; no service was activated. The source code was unchanged throughout.

| Frozen pair | Passing recorded samples | Valid wall seconds / 900 | Wall coverage | First / second half wall coverage | Acceptance |
| --- | ---: | ---: | ---: | --- | --- |
| Senate Republican control | 730/895 = **81.56%** | 739.352476 | **82.15%** | 83.70% / 80.60% | PASS |
| House Democratic control | 447/895 = **49.94%** | 451.291966 | **50.14%** | 52.77% / **47.51%** | FAIL |

Each pair recorded 895 of the planned 900 one-second samples; the five absent
samples per pair remain explicit. With the planned denominator, passing rates
are 81.11% for Senate and 49.67% for House. Wall coverage includes the entire
900 seconds, including startup, validation barriers, rotations and receiver gaps.
It is not a sample count multiplied by a nominal polling interval. House's narrow
overall wall-time pass does not override either failed criterion.

The separate screening window had 81.42% Senate and 65.83% House wall coverage.
Senate held up in the later window; House did not sustain the screen's coverage.
These purposive election pairs do not establish representative venue-wide quality
or future availability. “Independent” denotes a separate, frozen later measurement
window; it is not a claim of statistically independent market observations.

## Collector behavior and remaining coverage losses

| Holdout operational measure | Senate | House |
| --- | ---: | ---: |
| Worker status | DEADLINE_REACHED | DEADLINE_REACHED |
| Receiver errors / early receiver stops | 0 / 0 | 0 / 0 |
| Kalshi connections | 20 | 20 |
| Planned metadata/frame rotations | 19 | 19 |
| Message-timeout / snapshot-response-timeout failures | 0 / 0 | 0 / 0 |
| Requested / returned in-band snapshots | 20 / 20 | 26 / 26 |
| Audit failures | 0 | 0 |

No live control acknowledgments were observed. Actual snapshot responses retained
the required clock, source-time, sequence, price and quantity validation. No funds,
orders or automatic equivalence decisions were involved.

House's main coverage loss remains sparse or source-old observable US books,
with additional Kalshi freshness gaps. US update-gap p95 was 4.94 seconds for
House versus 1.82 seconds for Senate; maximum gaps were 18.23 and 10.54 seconds. The following full-window reason-seconds
can overlap and must not be summed as distinct downtime:

| Reason | Senate seconds | House seconds |
| --- | ---: | ---: |
| US source age outside two seconds | 100.309361 | 350.835171 |
| US receipt age outside two seconds | 92.063071 | 337.527063 |
| Source timestamp skew over two seconds | 80.855786 | 284.885359 |
| Kalshi source age outside two seconds | 3.541335 | 129.093624 |
| Kalshi pending validation | 54.440268 | 33.299158 |
| Kalshi planned rotation blocker | 6.788172 | 6.875117 |

Pending-validation time is an intentional raw-first barrier between receiving and
admitting a frame; it is not physical exchange downtime. The remaining planned
rotation and processing costs stay visible. A quiet socket or successful snapshot
request cannot substitute for fresh source data.

REST remained a weak comparison channel: Senate passed 8/895 samples and 0.65%
wall coverage; House passed 2/895 and 0.19%. The stream improvement does not justify
substituting HTTP response time for quote source time. US continuity remains
UNKNOWN. Host NTP checks passed before/after and all 30 checks per worker; final
reported host offset was −5.953 ms, not a measurement of exchange-clock offset.

## Verification and next decision

[Exact acceptance, cadence and reason breakdown](evidence/M5P_HOLDOUT_METRICS.json)
and [complete validation evidence](evidence/M5P_HOLDOUT_VALIDATION.json) preserve
configs, code hashes, clocks, results, source references, raw schema counts and
audits. Both completed holdout workers were replayed again independently: **20,197
events, 3,580 stream/REST channel-samples, every coverage interval, 9,421 SQLite
raw records including four preflight responses and 46 explicitly local command
records, and 2,549 US wire frames** verified. Both preceding screen audits also
passed; screening data are excluded from holdout acceptance.

The two fresh selection archives retain 16 exact public detail/book responses,
with hashes, schema versions, UTC receipts and representative sanitized JSON
fixtures under `data/m5p/holdout-20261103/selection-*/fixture.json`. All frozen
launch source files match their configuration hashes and the unchanged current
code. Original source archives and the production semantic index were not edited.

The exact command `.venv/bin/python -m unittest discover -s tests -v` executed
**564 tests**, all passing in **23.587 seconds**.
[Full names and output](evidence/M5P_HOLDOUT_TESTS.txt) are retained. CLI help,
explicitly hypothetical demo/report, fresh venue selection, both bounded captures
and their offline replay/cadence commands also passed. There were no implementation
changes requiring new code paths or test fixtures; this was operational validation
of the previously committed collector.

The next useful step is a **broader bounded cadence screen to find a second
candidate that can sustain coverage**, retaining Senate only if freshly open and
active. House should be treated as marginal, not promoted because its aggregate
wall time barely passed. The collector's snapshot recovery behaved reliably in
this window; another long capture of the same weak pair is not justified by these
results. Broader/sustained quality, source-backed US continuity, and all independent
settlement/fee/mechanics reviews remain open. No one-hour continuation is implied.
