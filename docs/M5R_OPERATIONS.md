# M5R offline operations

Authorization: execution of `M5R_ECONOMIC_VIABILITY_AND_MARKETDATA_FEASIBILITY.md`.
Scope is retrospective economic sensitivity, raw M5Q replay attribution, official
fee/interface documentation review, and a decision report. No new capture window
or service was authorized or started. $3,000 is a hypothetical research budget
within the unchanged $10,000 cumulative external seed ceiling, not deposited money.

`src/predarb/viability.py` is an isolated consumer. It neither replaces the production
fee evaluator nor changes `Engine`, source age, metadata, continuity, approval or
collateral gates. Decimal calculations retain separate venue caps, book/lot validity,
unsupported-short rejection and UNKNOWN actual fees/net/cash release. Every assumed
fee schedule and fill partition is explicitly hypothetical. The calculator optimizes
gross-positive marginal depth, not a strategy for executing negative net trades.

Reproduce from the preserved M5Q artifacts, choosing a **new** output directory:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m5r_analyze.py \
  --source data/m5q/run-20261108 \
  --output data/m5r/replay-unique-directory
.venv/bin/python scripts/m5r_analyze.py --help
```

The analysis command makes no network requests. It requires the original raw
archives referenced by M5Q, not only the committed summary JSON. It hashes inputs
before and after, opens original SQLite archives read-only, reconstructs all three
M5Q workers and validates the original samples/intervals before reporting attribution.
Missing archives, unknown schemas, bad hashes, changed classifications or unexpected
positive-population counts fail instead of supplying default prices. An existing
output directory is refused. A failed directory must remain visibly incomplete;
it is not a resumed run or evidence of completed acceptance.

Outputs under `data/m5r/analysis-20261108/`:

- `sources/`: original official HTTP bodies, including the Kalshi 429 body; UTC/SHA
  manifests; copied historical schedules; ten exact historical metadata bodies;
  official linked proto ZIP and its two inspected source members. No download was
  executed. Source scripts are retained beside them. The 16 new fee requests used
  only fixed public Kalshi GET paths, one-second spacing and 20-second timeouts.
- `offline/`: incomplete first development execution, failed on a datetime/string
  boundary in the new attribution consumer. Original source files were untouched.
- `offline-02/`: successful full analysis after fixing that boundary. No old
  collector or source archive changed. `offline-03/` repeats the analysis with the
  final isolated code; its normalized analytic results are compared exactly.
- `prospective-tiers.json`: separate November 6 coefficient sensitivity using the
  genuine historical Senate prices. These are not historical fee assertions.

The source manifest distinguishes **current retrieval** from **historical capture**.
Kalshi series history is requested with `show_historical=true`; event history must
have an empty final cursor. Empty arrays never establish account applicability.
The November 1 US schedule and November 3 market coefficient are preserved beside
the November 8 tier notice. No approval form, import, credential or account endpoint
was used. A valid production fee profile requires separate review; the M5R scenario
coefficients must never be copied into one automatically.

Attribution integrates the same event availability boundaries and unchanged
source/receipt/metadata expiry cuts as the original Engine. Exclusive combination
bins partition wall time; per-reason/category totals overlap. “Sole category”
seconds measure only how much recorded time would change if that rejection category
were removed. That offline arithmetic is not physical causal identification and
does not make an ignored blocker safe. Latency distributions are event-weighted,
with nearest-rank p95 and lower median. Source gaps omit unchanged timestamps but
report their count; snapshots and their cadence remain part of the observations.

The standard fee sensitivity assumes one taker order per venue, either one fill
per displayed price level or one-contract fragments plus a final fractional lot.
The separate upper bound permits minimum-lot Kalshi fragmentation without rebates
and the US cumulative fee cap. These cases are neither a prediction of matching
nor an exhaustive fee-partition optimizer. Bound-funded quantities include those
fees within both venue caps; purchase-only quantities do not. Account extras,
settlement payouts and required cash-release reserves remain unreviewed.

The [decision report](M5R_RESULTS.md) is complete as offline research. All failed
earlier selection results, service disablement and fixed deadlines remain binding.
No automatic next screen, gRPC integration, inference run, live execution or M6.
