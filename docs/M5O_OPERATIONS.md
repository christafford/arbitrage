# M5O — bounded continuous research operation

The operator authorized [M5O](M5O.md): one 24-hour read-only observation and
conditional price research. Production approved economics and all existing
settlement/fee/clock/collateral gates remain unchanged. No orders, funds, new
credentials, automatic approvals or expired-run renewals are permitted.

## Selection

`scripts/m5o_select.py` reads the existing sidecar without writing, verifies the
production model pin and refreshes 22 public definitions before selection. Sports
must match league, participants, rule date and selected team. Macro proposition
text must match the earlier source-bound review. One threshold per macro event
avoids counting variations as diversity. The 11 pairs cover three NBA games,
three NFL games, Fed hold, payrolls, unemployment, CPI and gasoline.

Ten are CONDITIONAL ordinary-outcome research assessments. Gasoline is DISCOVERY
because observation windows differ. None is STRICT or operator approved. An
ordinary-definition fingerprint change downgrades subsequent samples to DISCOVERY.
Unknown schema, prices, quantities and quality fail closed.

All selected pairs have deterministic identity/keyword/index lookup provenance.
A separate historical 100-query, 64-candidate ablation returned 32 deterministic
and 32 union finalists. Two additional ranked pairs carried proposition/date
conflicts and were excluded. With no AI-only selected pair, incremental economic
value is not estimable. This is a bounded ranking comparison, not representative
recall or current catalogue coverage. No inference, model change, reindex or
production checkpoint advancement occurred.

## Observation and conditional calculations

Each pair runs in its own process. A Kalshi clocked receiver writes one SQLite
archive while the main thread polls public US REST detail/full-book endpoints
into another. HTTP pacing cannot directly block the socket loop; Python processing
can still affect application latency. Original receipts and timings are archived.

US WebSocket sequence continuity remains UNKNOWN. This run uses the existing
validated REST full-snapshot path, without pretending that it solves M5M's caching
problem. Source and receipt ages and both cross-venue skews must be within two
seconds. Existing metadata age (60 seconds), price/lot grid, market state, Kalshi
sequence/generation and liveness checks also apply. Every US poll refreshes metadata.
Cached/quiet snapshots stay rejected. There is no response-only economics fallback.

Target cadence is five seconds per pair, with two paced US GETs per poll: about
4.4 requests/second for 11 pairs, below the checked 25/s shared-IP limit. Starts
are staggered; each client allows at most one request/second, three-second timeout
and one attempt. Retry-After cooldown persists; twelve consecutive errors stop a
worker. Kalshi's existing reconnect/backoff and 30-second resnapshot policy remain.
Only the existing protected Kalshi key signs its fixed market-data handshake.

The separate Decimal evaluator models Kalshi cash-long NO + US cash-long YES.
Reverse US synthetic NO remains blocked by unmodeled collateral mechanics.
$5/$25/$100/$500 are combined **pre-fee quote budgets**, not verified all-in
funding limits. Depth walks report available matched quantity, budget-limited
quantity, gross-profit-maximizing quantity, per-venue quote cost and gross edge.
No displayed quantity is a realized or guaranteed fill.

Fees, extra collateral, settlement delay and cash-release delay remain UNKNOWN
without reviewed applicability. Kalshi expected expiration and US administrative
end date are separately labeled source fields, never cash-release estimates.
Combined 1/2/5-cent fee-per-unit sensitivity is hypothetical; break-even fees are
the gross edge's capacity to absorb costs, not an actual fee bound or approval.

Matching ordinary outcomes imply $1 combined payout per matched unit. Conditional
exceptional `K YES=1, US YES=0` pays zero on the selected legs, losing their quote
cost before unknown fees. This is a scenario from unresolved source reviews, not
a venue ruling or measured probability. Sports discretionary payouts, Fed
rescheduling/range changes, labor/CPI revisions and gas windows remain visible.
DISCOVERY pairs receive no arbitrage calculation.

Positive sample clusters join adjacent positive polls at most seven seconds apart.
Rejections, processing gaps and segment changes break clusters. Their spans are
**not continuously verified opportunity durations**. Repeated sample profits are
never summed as realized profit.

## Lifetime and failure handling

Each new output directory freezes an original UTC deadline at most 86,400 seconds
after launch. UTC and monotonic limits both apply; drift above one second stops
collection. NTP is checked before launch, every 30 seconds per worker and after
each segment. Request guards run after pacing, before network I/O. In-flight
responses may finish after the deadline and remain archived; they cannot create
post-deadline economic samples.

Pairs use new segments of at most 900 seconds, at most 100 segments. Schema-9
SQLite WAL archives each have one writer; no production schema change is needed.
Every segment's raw hashes and non-error observations are replayed before its next
segment. Audit processing gaps count against full-window planned coverage.
Replay failure stops the pair. Collection stops below 2 GiB free or above 20 GiB
in the run directory; 30-second storage checks allow in-flight overshoot. Raw
archives remain retained; no destructive pruning or automatic restart runs.

SIGTERM/SIGINT stops owned receivers. Cleanup allows 15 seconds per receiver and
180 seconds per worker for offline replay. Forced kills remain partial.
`DEADLINE_REACHED` means budget expiry, not continuous coverage, profitable
economics, successful workers or milestone completion. Existing output directories
cannot be reused to renew a run. Old M5I services remain disabled.

## Replay and verification

Each sample records source hashes, UTC/monotonic assessment clocks, normalized
books and the SQLite state visible to its reader. Receipt time differs from
commit visibility: a message received before a sample but committed afterward
must not retroactively replace its quote. Temporary views in read-only connections
restore those frontiers, pending validations and connection states during replay.
Source databases are never mutated. Pending-frame barriers remain even if their
validation later succeeds. Raw hashes, counts, clock order, closure and post-run
NTP are checked. Error samples are rejected; replay does not recreate outages.

The first smoke exposed this commit race and remains failed historical evidence.
The second exposed remaining visibility/representation differences. The third
45-second, 11-pair smoke passes all segment replays. The genuine NFL fixture keeps
exact public bytes, hashes and clocks; unused derived normalization JSON alone
was replaced with `{}`. Another fixture preserves all 22 selected definitions.
Fault injections and positive-price examples are explicitly hypothetical.

The [November 2 ladder correction](M5O_LADDER_FIX.md) handles Kalshi's documented
omitted empty snapshot sides. It is available to new processes; the existing
run's imported code, rejected evidence and fixed deadline remain preserved.

## Commands and status

Create a new selection and launch the authorized run once:

```bash
.venv/bin/python scripts/m5o_select.py --output data/m5o/selection-final
.venv/bin/python scripts/m5o_observe.py run \
  --candidates data/m5o/selection-final/candidates.json \
  --output data/m5o/run-20261101 --seconds 86400 \
  --report-path docs/M5O_RESULTS.md
```

Read `data/m5o/run-20261101/status.json`, `report.json` and per-pair `status.json`.
[M5O results](M5O_RESULTS.md) refresh about every 30 seconds and after cleanup.
The transient user service `predarb-m5o-20261101.service` has no restart or boot
enablement; capture continues independently of the chat. Stop it early with:

```bash
systemctl --user stop predarb-m5o-20261101.service
```

Replay a completed segment without network access:

```bash
.venv/bin/python scripts/m5o_observe.py replay \
  --config data/m5o/run-20261101/config.json --pair nfl-chicago \
  --segment data/m5o/run-20261101/nfl-chicago/segment-001
```

Run `.venv/bin/python -m unittest discover -s tests -v`. Exact test output and
smoke/preservation evidence are `docs/evidence/M5O_TESTS.txt` and
`docs/evidence/M5O_VALIDATION.json`. Actual 24-hour results remain pending until
the window and audits finish. Net profitability, independent adjudication and
representative AI-only coverage can remain unknown after a technically sound run.
