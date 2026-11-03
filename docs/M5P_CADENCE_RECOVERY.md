# M5P follow-up — measured cadence and Kalshi recovery

The operator requested update-cadence screening and reduced Kalshi recovery gaps
on November 3, after reviewing M5P's failed 50% quality target. This is a bounded
M5P engineering follow-up. Historical runs and their fixed deadlines are preserved.
No model/index change, settlement approval, orders, funds or M6 is involved.

## Method and boundaries

`m5p_observe.py --kalshi-recovery-policy inband-snapshot` opts into an isolated
research path; the default remains `reconnect`. After five seconds without a
validated book, or 25 seconds since the last snapshot, the collector sends the
documented `update_subscription/get_snapshot` for its existing single-market
subscription. Requests are spaced at least five seconds apart, with one pending
snapshot and a five-second response timeout. Raw local commands are committed
before send; every response is archived before semantic validation. A snapshot
replaces both ladders and must pass existing market identity, sequence, clock,
source-time, price, quantity and metadata checks. Missing sides remain unusable.

Control acknowledgments require an archived matching request. Present control
sequence numbers must be contiguous; present send timestamps must not regress.
Acknowledgments and transport pongs never refresh a book. Errors, sequence gaps,
missing clocks or unknown response shapes still invalidate and reconnect, with
bounded backoff. This iteration reduces quiet/periodic recovery overhead; it
does not implement in-band recovery after detected sequence loss.

Connections rotate after 45 seconds or 1,000 frames, keeping the original metadata
below its unchanged 60-second age limit and retaining bounded archives. Planned
rotation omits the old extra one-second backoff. Metadata fetch and handshake
costs remain. The production book inspector does not consume experimental control
frames: they require the isolated quality replay. No database migration is needed.

`m5p_cadence.py` replays raw evidence before ranking the supplied candidates. It
reports observed depth changes, repeated source timestamps, update-gap median,
p95/max, and longest gap including startup and tail. It ranks by valid local-state
wall coverage, then sample coverage, then stable pair ID. Admission to a later
observation requires:

- At least 300 seconds, with the worker reaching the fixed deadline, no receiver
  errors or early endings, and successful raw/event/sample/interval replay.
- At least 50% passing samples and 50% valid wall time under unchanged two-second
  source/receipt/skew checks and existing metadata/grid/depth requirements.
- At least 50% wall coverage in **each half** of the window, plus five observed US
  depth changes. Bursts, repeated timestamps and restarts cannot stand in for this.

Selection only proposes further observation. It cannot approve contracts or start
another capture. An empty shortlist is a valid outcome. These are purposive
engineering thresholds, not exchange requirements or guarantees of future activity.

## Bounded execution scope

Three fresh source-bound DISCOVERY pairs: House Democratic control, Senate
Republican control, and Fed hold as a quiet control. There are no economics or
settlement decisions in this follow-up. Venue volume is context only; it does not
rank the screen. All three are checked open immediately before each window.

After the full suite, execute one 20-second in-band smoke, then concurrent
five-minute old/new policy observations using independent archives. At most six
pair workers, with one US/Kalshi stream per worker and approximately 2.4 US REST
requests/second combined. Existing message, connection, storage and clock guards
remain. No background service or automatic extension is installed. Independent
connections do not receive identical messages: comparisons are overlapping-window
observations, not exact counterfactual replay or a causal performance estimate.

```bash
.venv/bin/python scripts/m5p_select.py \
  --proposals data/m5p/cadence-recovery/proposals.json \
  --output data/m5p/cadence-recovery/selection-01
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m5p_observe.py run \
  --candidates data/m5p/cadence-recovery/selection-01/candidates.json \
  --output data/m5p/cadence-recovery/smoke-01 --seconds 20 \
  --kalshi-recovery-policy inband-snapshot
```

The two five-minute runs use new directories `baseline-01` and `screen-01`,
`--seconds 300`, and policies `reconnect` and `inband-snapshot` respectively.
Offline screening: `scripts/m5p_cadence.py --source RUN --output NEW_REPORT.json`.
Source documents and their exact receipts/hashes are in
[evidence/M5P_CADENCE_API_CHECKS.json](evidence/M5P_CADENCE_API_CHECKS.json).
Final measurements and acceptance status will be recorded below after execution.

## Measured results — both fixed windows finished

The baseline window ran **23:18:31.875997–23:23:31.875997 UTC** on November 3;
the in-band screen ran **23:18:32.856342–23:23:32.856342 UTC**. Every worker reached
its deadline, every child exited 0, and all six paired-worker audits passed.
Cleanup/replay completed at 23:23:43.216464 and 23:23:44.675114 respectively.
Collection eligibility did not extend past either deadline. All processes stopped.

**Senate and House pass this five-minute engineering screen. Fed hold is rejected.**
House is marginal: its sample rate is only 0.50 percentage points above the target.
This is selection-window evidence, not held-out or sustained 15-minute acceptance.
The old M5P result remains historically below target; no milestone is relabeled
complete and no optional hour, service or additional run was launched.

| Pair | Baseline passing samples | In-band passing samples | Baseline valid wall time | In-band valid wall time | In-band halves | Screen |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Senate Republican control | 232/298 = 77.85% | 249/298 = 83.56% | 78.81% | **82.09%** | 76.92% / 87.25% | Select |
| House Democratic control | 143/299 = 47.83% | 151/299 = 50.50% | 49.88% | **53.18%** | 51.72% / 54.64% | Select, marginal |
| Fed hold, quiet control | 2/299 = 0.67% | 11/299 = 3.68% | 0.63% | **3.25%** | 1.16% / 5.35% | Reject |

Every wall-time denominator is the complete 300 seconds, including startup,
validation, reconnect and shutdown gaps. Planned one-second sample denominators
are also 300 per pair; missing samples never disappear from wall time. Among the
two selected pairs, the screen passes 400/597 recorded samples and 405.804058 of
600 pair-seconds (67.63%). Including the deliberately quiet control reduces the
all-three wall percentage to 46.17%; the control is not hidden from the results.

The comparable-window improvement is approximately **3.30 percentage points of
wall time for House and 3.28 for Senate**. Most of the difference from the earlier
M5P result is consistent with the much busier observed feeds in this later window,
not a collector-only gain. Independent connections and the 0.98-second start
offset prevent treating even this comparison as an exact causal estimate.

| Kalshi measure | Baseline | In-band screen |
| --- | ---: | ---: |
| Connections, all three pairs | 32 | 21 |
| Message-timeout disconnects | 13 | 0 |
| Requested in-band snapshots / returned | 0 / 0 | 67 / 67 |
| House locally disconnected/pending seconds | 34.013869 | 19.150934 |
| Senate locally disconnected/pending seconds | 33.948489 | 24.199876 |
| Fed locally disconnected/pending seconds | 243.321044 | 3.420090 |
| Early worker stops / audit failures | 0 / 0 | 0 / 0 |

The unavailable-state seconds above use the existing `kalshi:DISCONNECTED` reason,
which includes local pending-validation barriers, and are not a claim of physical
network outage duration. New-policy connections only ended for their planned
metadata/frame rotation or final budget. Every requested snapshot returned; none
needed timeout fallback. No live `ok` control acknowledgments were observed.
Failure fallback and control-sequence handling remain covered by hypothetical
fault tests rather than claimed live observations.

Actual US update gaps explain the selection:

| Pair | Observed depth changes | Median gap | p95 gap | Maximum gap, including startup/tail |
| --- | ---: | ---: | ---: | ---: |
| Senate | 471 | 0.301 s | 2.014 s | 4.031 s |
| House | 271 | 0.401 s | 4.926 s | 10.476 s |
| Fed | 16 | 2.512 s | 152.045 s | 152.045 s |

A low median alone would have disguised the Fed's long quiet intervals. Its US
feed remains the binding limitation despite the large reduction in Kalshi gaps.
Source timestamps, receipt timestamps and observed depth changes retain distinct
meanings; US continuity remains UNKNOWN and pongs confer no freshness exemption.

## Evidence, verification and remaining limits

- [Screen and complete rankings](evidence/M5P_CADENCE_SCREEN.json),
  [baseline rankings](evidence/M5P_CADENCE_BASELINE.json), and
  [historical source-bound shortlist](evidence/M5P_CADENCE_SHORTLIST.json).
  Recheck open state, source definitions and cadence before later use; the shortlist
  is not a standing claim that these markets remain active.
- [Complete configs, results, clocks and audits](evidence/M5P_CADENCE_VALIDATION.json).
  Both five-minute archives were replayed again offline: **14,575 events,
  3,584 channel-samples, every coverage interval, 7,118 SQLite raw records
  (including 67 explicitly local command records and 12 preflight responses),
  and 1,607 US wire frames**. Original raw responses remain retained.
- [Pre-capture suite](evidence/M5P_CADENCE_TESTS_PRECAPTURE.txt): **553 tests passed**
  in 23.589 seconds. [Final exact test names and output](evidence/M5P_CADENCE_TESTS.txt):
  **564 tests passed** in 24.074 seconds with
  `.venv/bin/python -m unittest discover -s tests -v`. The 20-second three-pair
  live smoke, all worker replays, both offline ranking commands, CLI help and the
  explicitly hypothetical `predarb demo` / `predarb report` also passed.

Frozen launch source files match every hash in each run configuration. Post-capture
report review corrected the even-count gap median and excluded structurally rejected
books from update-cadence counts; proposal identity checks now precede requests.
No running worker was hot-reloaded, and the capture/quality policy did not change.

The bounded follow-up implemented and demonstrated reduced recovery gaps and a
measured shortlist. Remaining work is an independently chosen holdout window,
especially for marginal House coverage; broader market screening; reducing planned
metadata/frame-rotation overhead; and source-backed US continuity semantics. These
are explicit gaps, not reasons to weaken the two-second checks. All three pairs
remain **DISCOVERY / UNVERIFIED**, with no economic or settlement approval.
