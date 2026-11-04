# M5P — live validation after atomic finalization

The operator explicitly authorized all proposed steps: fresh eligibility checks,
one five-minute screen, and one independent 15-minute holdout only if two pairs
qualify. [The preregistered plan](evidence/M5P_ATOMIC_LIVE_PLAN.json) was saved
before venue requests. No previous run or deadline is renewed. Collector code is
commit `d00de43`, retaining raw-first archival, separate pending-provenance commits,
WAL/FULL, the atomic final transaction and all existing integrity/approval gates.

The screen requires at least 60% passing recorded samples, 60% valid full-window
wall time and 60% wall time in each half, at least five US depth changes, no
receiver errors/early stops, fixed-deadline completion and successful replay.
Qualifiers rank by minimum half-window wall coverage, then full wall coverage,
then stable ID. Freeze the best two and recheck their exact definitions/open state.
If fewer than two qualify, stop without a holdout. A holdout requires 50% samples,
full-wall coverage and wall coverage in each half for **both** frozen pairs.
Missing planned samples remain visible. No repeats, substitutions or extensions.

Settings remain `inband-snapshot`, with two-second source/receipt/skew gates,
existing metadata/grids, snapshot request/reconnect budgets and fixed generation
rotations. US sequence continuity remains UNKNOWN. All pairs are DISCOVERY /
UNVERIFIED; no economic eligibility, equivalence decision or profitability claim.

## Fresh scope

All four historical election hints are excluded: Senate Republican control,
Michigan Senate Democratic, Georgia Governor Republican and House Democratic
are Kalshi finalized / US resolved in fresh November 4 responses. Exact bytes,
schemas, hashes and UTC receipts remain in
`data/m5p/atomic-live-20261104/eligibility.sqlite3` and
`eligibility-fixture.json`. These failures are retained, not silently replaced in
an already-started window.

A bounded fallback uses read-only historical-index hints and fresh public NBA
metadata. One US 100-market response to a moneyline-filtered query contained crypto
markets, so its filter was not treated as reliable coverage. One scoped Kalshi
response contains 66 NBA markets. The three distinct November 4 events with the
highest summed Kalshi 24-hour volume across their two outcome markets supplied
candidate hints: Philadelphia–Detroit, Atlanta–Washington and Milwaukee–Boston.
Volume is not an update-cadence pass. Seven proposed pairs total were considered;
no venue-wide traversal or inference occurred.

Fresh official detail/book requests confirm open state, supported grids, two-sided
depth and the same league, participants, selected team and rule date. US slugs
were naming hints until confirmed by official responses and the existing strict
sports identity extractor. Settlement procedures remain independently discretionary
and unadjudicated; these sports pairs are excluded from strict arbitrage.
`selection-01/fixture.json` preserves all twelve exact public detail/book bodies.

[Ten fresh official source captures](evidence/M5P_ATOMIC_LIVE_API_CHECKS.json) and
[two catalogue documents](evidence/M5P_ATOMIC_LIVE_CATALOGUE_SOURCES.json) retain raw
hashes and UTC receipts. Nine of the ten original documents are byte-identical to
the prior check; Kalshi Get Market changes only the published version 3.35.0 →
3.36.0. Consumed fields/local adapter contracts stay unchanged. Public catalogue
filters are documented but are never assumed to guarantee returned scope.

## Execution

New isolated root: `data/m5p/atomic-live-20261104/`. Existing credentials sign only
fixed market-data handshakes. No account/order endpoints, inference or model/index
writes, services, funds, or automatic approvals are involved.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m5p_select.py \
  --proposals data/m5p/atomic-live-20261104/proposals-sports.json \
  --output data/m5p/atomic-live-20261104/selection-01
.venv/bin/python scripts/m5p_observe.py run \
  --candidates data/m5p/atomic-live-20261104/selection-01/candidates.json \
  --output data/m5p/atomic-live-20261104/screen-02 --seconds 300 \
  --kalshi-recovery-policy inband-snapshot
```

The screen supervisor saves its fixed UTC deadline and source hashes before
starting workers. This is operational validation of existing code, with no new
collector path. Final findings below record shutdown and replay.

## Final outcome — one qualifier; holdout not launched

**The required two-pair screen did not pass.** Philadelphia–Detroit qualified;
Atlanta–Washington and Milwaukee–Boston failed. The agreed stop rule therefore
prevented the 15-minute holdout. No frozen two-pair holdout, replacement screen,
longer capture or service renewal was prepared or launched.

The first setup (`screen-01`) stopped on a five-second US Milwaukee metadata HTTP
body timeout after five successful preflight responses. It created neither a
window configuration/deadline nor a worker. Its archive/log remain preserved.
A [recorded bounded setup retry](../data/m5p/atomic-live-20261104/preflight-retry-decision.json)
rechecked the same candidates/code/settings in `screen-02`; this was the only
observation window. No failed screen outcome or existing deadline was reset.

The actual screen ran **November 4, 23:04:14.866288–23:09:14.866288 UTC**
(**18:04:14–18:09:14 EST**). All three workers reached that fixed deadline and
exited 0. Supervisor cleanup/replay finished at **23:09:22.745553 UTC**; cleanup
and late raw receipts did not extend sample/event eligibility. Launch source
hashes remained unchanged.

| Pair / selected YES team | Passing samples | Full-window wall coverage | First / second half wall | 60% screen |
| --- | ---: | ---: | ---: | --- |
| Philadelphia–Detroit / Philadelphia | 204/299 = **68.23%** | **66.54%** | **67.30% / 65.78%** | PASS |
| Atlanta–Washington / Atlanta | 122/299 = **40.80%** | **38.66%** | **46.84% / 30.47%** | FAIL |
| Milwaukee–Boston / Milwaukee | 116/299 = **38.80%** | **38.19%** | **50.86% / 25.52%** | FAIL |

Each pair missed one of the 300 planned one-second sample slots. Using planned
rather than recorded denominators gives 68.00%, 40.67% and 38.67%, respectively;
none of the decisions changes. Wall denominators include the full 300 seconds
and both 150-second halves. This was a purposive three-event screen, not
representative market coverage or a standing activity guarantee.

[Final audited results](evidence/M5P_ATOMIC_LIVE_RESULTS.json) include all failed
criteria and nested US segment failures. The earlier
[screen/latency calculation](evidence/M5P_ATOMIC_LIVE_SCREEN_RESULTS.json) is retained;
the final report explicitly also gates non-complete US segments. This additional
failure accounting does not change the one-qualifier result. Both reports retain
the standard 50% cadence decisions separately from the registered 60% screen.

## Integrity, recovery and remaining gaps

All **three independent replay audits passed**, verifying **4,108 journal events**,
**1,794 stream/REST channel-samples**, every wall-time interval, **1,811 SQLite raw
records** and **1,057 US frames**. A further **33 successful public raw responses**
in eligibility/catalogue/selection/preflight archives passed hash and SQLite
integrity checks; the timed-out body was not fabricated as an archived response.
[Preflight audit](evidence/M5P_ATOMIC_LIVE_PREFLIGHT_AUDIT.json).

There were zero worker-level exceptions or early receiver stops. Kalshi used seven
connections per pair and returned **all 35 requested in-band snapshots** (7, 12,
16). It recorded no message timeout, snapshot-response timeout or other capture
failure. Six planned metadata rotations per pair remain included in coverage.

Milwaukee's first US connection ended with **`ConnectionClosedError` /
`CAPTURE_ERROR`** and recovered in a second bounded segment. The reconnect loss
is preserved (**2.652203 seconds** under that reason); it is an additional screen
failure, not erased by worker exit 0 or successful replay. Philadelphia and Atlanta
completed one US segment each. Philadelphia and Atlanta also had local
`METADATA_UNAVAILABLE` loss events, included in their coverage; these do not prove
physical socket outages. [Segment and clock audit](evidence/M5P_ATOMIC_LIVE_OPERATIONAL_AUDIT.json).

All before/after and 30 periodic worker clock checks reported synchronization.
This is host synchronization evidence, not measured exchange-clock alignment.
The six historical M5I services remain disabled with none loaded; no service was
started. Seventeen protected historical configuration/status files retain their
hashes. Production model/index identity, gates and expired runs remain unchanged.

### Latency and unavailable wall time

| Measurement | Philadelphia–Detroit | Atlanta–Washington | Milwaukee–Boston |
| --- | ---: | ---: | ---: |
| Kalshi admitted books | 463 | 345 | 589 |
| Receipt → availability median / p95 | 16.14 / 27.87 ms | 15.11 / 26.81 ms | 13.52 / 25.92 ms |
| Receipt → availability maximum | 59.48 ms | 47.82 ms | 65.00 ms |
| Kalshi pending-barrier wall time | 3.531854s | 2.671381s | 4.452197s |
| Kalshi source age outside two seconds | 17.949750s | 84.652078s | 82.094491s |
| US source age outside two seconds | 79.018692s | 133.069317s | 146.214331s |
| Source skew outside two seconds | 48.439391s | 86.105904s | 92.914379s |

Reason-seconds overlap and must not be summed into distinct downtime. Pending
barriers here account for roughly 0.9–1.5% of each window; source-age/skew rejection
was much larger. This does not justify attributing all historical losses to venues
or relaxing the gates. The old election run had different markets, activity and
frame counts, so its larger cumulative pending totals are not a controlled
before/after live comparison.

US validated-book availability gaps reached 5.58s, 7.97s and 9.22s, respectively.
Observed depth changes numbered 254, 305 and 185. Many updates or substantial
volume do not ensure simultaneous two-second-valid cross-venue quotes. US sequence
continuity and quiet-book validity remain UNKNOWN.

### Same-source offline commit-cost check

After the capture and its shutdown, a dedicated offline process replayed each
first connection's first 64 frames (Atlanta had only 57 available; no later
connection was substituted). Three repetitions alternated original/atomic writer
order. The baseline `record_frame` is hash-bound to the pre-optimization source;
all other code and WAL/FULL settings are shared. Network is forbidden inside the
profiler. This measures local replay/commit costs, **not live per-commit latency**.

All **18 instrumented executions passed**, with **1,110 replayed frames**, **1,092
normalized books** and **1,128 raw records** across executions. Every intermediate
book matched its actual source, both implementations had identical normalized
digests, and the source archive hashes stayed unchanged.

| Prefix | Median original capture | Median atomic capture | Observed instrumented reduction |
| --- | ---: | ---: | ---: |
| Philadelphia–Detroit (64 frames) | 1.353s | 1.119s | 17.26% |
| Atlanta–Washington (57 frames) | 1.235s | 1.056s | 14.48% |
| Milwaukee–Boston (64 frames) | 1.428s | 1.225s | 14.24% |

Final commits halve in each comparison. Timing includes instrumentation,
filesystem/checkpoint/scheduling effects, with three repetitions per version and
small serial prefixes. It cannot establish a causal live coverage gain or sustained
throughput. [Full cost runs and summary](evidence/M5P_ATOMIC_LIVE_OFFLINE_COSTS.json).
The isolated operational analysis/profile scripts and their frozen inputs are
retained under `data/m5p/atomic-live-20261104/`.

## Verification and remaining decision

Actually executed:

- `.venv/bin/python -m unittest discover -s tests -v`: **581 tests passed in
  25.461s** before launch. [Every test and output](evidence/M5P_ATOMIC_LIVE_TESTS.txt).
- `scripts/m5p_observe.py --help`, `predarb demo` and `predarb report` in a new
  isolated database: passed, with visibly hypothetical demo output.
  [Smoke output](evidence/M5P_ATOMIC_LIVE_SMOKE.txt).
- Fresh source selection and identity checks: passed for the three sports pairs;
  all four closed election exclusions retained. No inference used.
- One failed preflight-only setup, followed by the sole 300-second observation:
  all workers exited 0 at the fixed deadline; three automatic and three separate
  replay audits passed. The final analysis repeated the same deterministic audit
  when adding explicit nested-US-segment failure accounting.
- Eighteen offline captured-prefix cost comparisons: all passed as detailed above.
- Source/configuration hash comparisons and `git diff --check`: passed.

No production Python code or collector settings changed in this operational task.
The new source fixtures preserve actual public bytes/provenance; no test result or
venue response is invented. One stronger candidate is established **only for this
historical screen**. The second qualifier and independent two-pair holdout remain
unmet, along with sustained quality, US continuity, and all independent
settlement/fee/mechanics review. No new capture or automatic continuation is implied.
