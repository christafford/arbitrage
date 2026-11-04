# M5P — screening a stronger second candidate

The operator requested a stronger second candidate after House failed the
independent holdout. This is bounded screening using the unchanged collector,
not a new sustained validation or service renewal. All pairs remain DISCOVERY /
UNVERIFIED. The original House failure and every expired deadline remain preserved.

## Registered design

[Plan](evidence/M5P_SECOND_PLAN.json), saved before live selection or screening:
consider four distinct ordinary election-winner races, using bounded historical
FTS searches as hints, followed by fresh official venue definitions and two-sided
depth checks. No catalogue-wide coverage or AI-quality claim is made. Rejected
candidates remain in the report. Do not use county vote totals, victory margins,
combined outcomes or the opposite side of Senate control as a new independent pair.

The four challengers are Democratic outcomes in the Georgia, North Carolina and
Michigan US Senate races, and the Republican outcome in Georgia Governor. Senate
Republican control is the common reference, freshly checked before each run.
These are distinct events but can be politically correlated.

The existing 50% engineering gates are unchanged. For a **stronger nomination**,
require 60% passing recorded samples, 60% full-window valid wall time and 60% wall
time in **each half**, at least five observed US depth changes, no early receiver
stops/errors, fixed-deadline completion and successful replay. Rank qualifying
challengers by minimum half-window wall coverage, then full wall coverage, then
stable ID. A higher nomination threshold supplies headroom; it is not a venue rule
or statistical confidence bound.

The budget allows at most two parallel five-minute cohorts of three pairs, then
one separate five-minute confirmation for only the best qualifier plus Senate.
Do not replace pairs or extend a window after it starts. If no challenger meets
the stronger threshold, stop and report that outcome. A nomination remains a
screening result; no 15-minute holdout or one-hour continuation is authorized by
this plan. Full raw/event/sample/interval replay is mandatory.

## Source selection and exclusions

[Ten fresh official documents](evidence/M5P_SECOND_API_CHECKS.json) retain exact
raw bytes, schema sources, hashes and UTC receipts. Existing consumed fields and
adapter schemas are reused. [Fresh screened definitions](evidence/M5P_SECOND_CANDIDATES.json)
bind party, state, office and election identity without approving settlement.

| Challenger | Fresh preflight finding | Decision |
| --- | --- | --- |
| Georgia Senate Democratic | Kalshi `SENATEGA-26-D` status `determined` | Exclude before streaming |
| North Carolina Senate Democratic | US book open but `offers: []` | Exclude: no usable two-sided depth |
| Michigan Senate Democratic | Both venues open with two-sided displayed depth | Screen |
| Georgia Governor Republican | Both venues open with two-sided displayed depth | Screen |

Only one three-pair discovery cohort was necessary: Senate reference plus Michigan
and Georgia Governor. Original failed-selection archives/logs are retained. All
exact public responses, including the determined and partial-book exclusions,
are bundled in `data/m5p/second-candidate-20261104/preflight-fixtures.json` with
source URLs, schemas, receipts and hashes; they are genuine, not hypothetical.

The fresh US definitions now explicitly mention accelerated settlement by media
consensus. That differs from the older cached descriptions. Both venues' full
procedures remain unadjudicated; ordinary election winner versus swearing-in or
inauguration can still diverge. No resolution-language warning or approval gate
was removed. Updated risk notes accompany the freshly bound screen candidates.

## AI outage boundary

This task makes **zero inference requests**. Historical candidate search uses the
read-only local semantic sidecar's FTS index and explicit IDs, not the inference
server. No vectors are generated, merged or relabeled. The preserved namespace is
`8f1b745674ea82993cc5211498d606a86627ecedb6776637daeaf66e42611204`.
Venue collection, normalization, cadence measurement and offline replay run in
Python/SQLite independently. An AI outage blocks new embedding work; it does not
invalidate stored public evidence or stop these deterministic known-contract
screens. This is not a claim that AI adds or cannot add discovery value.

## Execution

The collector remains `inband-snapshot` with the existing two-second source,
receipt and skew gates, metadata/depth checks, raw-first barriers, bounded
snapshot requests and reconnect fallback. No code or production schema changes
are made. New archives are under `data/m5p/second-candidate-20261104/`.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m5p_observe.py run \
  --candidates data/m5p/second-candidate-20261104/screen-candidates.json \
  --output data/m5p/second-candidate-20261104/screen-01 --seconds 300 \
  --kalshi-recovery-policy inband-snapshot
```

## Results — no stronger challenger qualified

The fixed window was **November 4 01:05:22.063368–01:10:22.063368 UTC**
(November 3 20:05–20:10 EST). All three workers reached the deadline; the
supervisor finished shutdown/replay at 01:10:59.826964 UTC. No confirmation
window was launched because neither challenger met the registered stronger rule.

| Pair | Passing samples | Valid wall time | First-half wall | Second-half wall | Stronger rule |
| --- | ---: | ---: | ---: | ---: | --- |
| Senate Republican reference | 211/298 (70.81%) | 217.54/300s (72.51%) | 75.03% | 69.99% | Pass, reference only |
| Michigan Senate Democratic | 185/298 (62.08%) | 188.87/300s (62.96%) | 68.34% | 57.57% | Fail: second half |
| Georgia Governor Republican | 179/299 (59.87%) | 178.14/300s (59.38%) | 60.94% | 57.82% | Fail: samples, full wall, second half |

All three pass the existing 50% five-minute screening rule. That is distinct from
the preregistered 60% nomination and from independent sustained validation.
[Standard replay report](evidence/M5P_SECOND_SCREEN.json) retains the ordinary
50% decisions; [final evidence](evidence/M5P_SECOND_RESULTS.json) explicitly
applies the stronger rule. Michigan is a promising further-research candidate,
but this run does not nominate it or repair the failed House holdout.

The three replay audits passed: **16,562 raw archive hashes and 2,548 US frames**
verified, with event chains, recorded samples and interval coverage reconstructed.
Raw archive counts include explicitly labeled local snapshot commands, not just
venue responses. All **21/21** requested Kalshi snapshots returned; no receiver
failures, unexplained early worker stops or audit failures occurred. Forty-one
fresh selection responses across five archives also passed raw-hash verification,
including both failed preflights. The [29-response preflight fixture bundle](evidence/M5P_SECOND_PREFLIGHT_FIXTURES.json)
preserves exact public bodies with schemas, receipt times and hashes; the common
12-response cohort selection has its own local fixture. The configured 60 source
files and their preserved copies match the launch hashes. Clock checks before
and after capture report synchronized.

### Why coverage was lost

US observed depth changes were 1,307 for Senate, 636 for Michigan and 408 for
Georgia Governor. Local validated US book interarrival p95 was 0.80s, 1.73s and
2.79s respectively; maxima were 5.24s, 5.07s and 11.89s. These describe this short
window, not universal venue behavior or proven continuous exchange validity.

Michigan spent **67.12s** with `kalshi:PENDING`, while Senate spent **69.38s**
and Georgia Governor **16.83s**. The collector fails closed between receipt and
validation of each new Kalshi frame. [Archived receipt-to-availability timings](evidence/M5P_SECOND_LOCAL_LATENCY.json)
show median processing intervals of 12–14ms, p95 of 25–29ms and maxima below
90ms. Thousands of short barriers accumulate into material unavailable time;
these measurements do not establish a long per-frame processing backlog.

Georgia Governor instead had **92.17s** rejected for US source age, compared with
22.03s for Michigan and 9.79s for Senate. Rejection times overlap and must not be
added. Generic `DISCONNECTED` interval reasons also overlap pending barriers;
they are not independent evidence of physical socket outages.

A [short host sample](evidence/M5P_SECOND_HOST.json) during capture showed 8–14%
I/O wait with 70–80% CPU idle in its two one-second intervals. This supports
investigating local persistence/validation cost, but neither isolates a storage
cause nor establishes whole-run host utilization. No gates were relaxed to
compensate. The next engineering investigation should profile the raw archive,
SQLite commits and journal work per frame, preserving raw-first auditability and
the pending-state barrier. Simply choosing busier markets can increase this cost.

### Verification and remaining gaps

`.venv/bin/python -m unittest discover -s tests -v` executed **564 tests, all
passing in 24.625s**; [complete test names/output](evidence/M5P_SECOND_TESTS.txt).
The isolated `predarb demo` and `predarb report` smoke commands passed with
visibly hypothetical data. The live collector completed successfully, followed by
the independent `m5p_cadence.py` raw/event/sample/interval replay above. No product
code or tests changed in this operational screen.

No stronger second candidate was established among these four proposals. This
limited purposive sample does not establish venue-wide scarcity. No repeated
valid economic signal was established: these remain DISCOVERY pairs, with no
economic eligibility and zero recorded positive-gross samples. US continuity,
quiet-book validity, settlement/fee/mechanics review and sustained multi-pair
coverage remain open. No milestone completion, longer capture or service renewal
is implied.
