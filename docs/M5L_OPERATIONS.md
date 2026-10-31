# M5L operations and replay

M5L is read-only economic research. The outcome and open acceptance items are in
[M5L results](M5L_RESULTS.md). Production source/index files and expired M5I runs
remain preserved. No command here renews a human approval or authorizes trading.

Use the existing virtual environment (`. .venv/bin/activate`). There are no new
third-party dependencies. Output benchmark/evaluation directories must be new;
raw archives in `data/m5l/` are intentionally retained locally. Reports/fixtures
under `docs/evidence/` and `tests/fixtures/` are source-backed evidence, not model
approvals. Provider data rights remain those documented in API_SOURCES.md.

## Benchmark

```bash
python scripts/m5l_benchmark.py --help
python scripts/m5l_benchmark.py --directory data/NEW-m5l-benchmark \
  --url https://cachyos.tail2be75f.ts.net/v1/embeddings --repeats 3
```

This explicitly requests bounded private inference, not venue collection. It uses
separate method/batch SQLite files, 64 distinct genuine descriptions, 1–5 repeats,
one outstanding request, 30-second socket timeout, no retries and at most 100
standard client requests per archive. Successful observations are committed before
conversion. Errors remain visible in `results.json`; incomplete/failed settings
are never filled with estimated throughput. The corpus is for text benchmarking;
older source receipts are not renewed into eligible production work.

Persistent-worker trials seed separate sources, then read them read-only while
writing only separate indices. Every request keeps the production model pin.
This benchmark records HTTP wait, client CPU, local processing and persistence,
not pure GPU inference. The current service does not expose metrics and no trusted
SSH host key was available. Supply verified host telemetry before interpreting
GPU offload or VRAM. Do not disable SSH host verification or modify the server to
make a benchmark pass. No model reconfiguration belongs to these scripts.

`large_diagnostic()` in the same script is an explicitly separate 64-input,
16 MiB-response experiment. It uses fresh archives and three passes per method.
It does not modify the production 4 MiB response guard. Its successful full bodies
and the original rejected/truncated responses both remain preserved. The diagnostic
process exceeded the previous service memory cap; validate resource usage before
considering larger production responses.

The method namespace hashes the actual probe identity and exact query instruction.
Only query text is instructed. Guards still parse original public definitions.
Compare identical data and preserve before/after hashes; never merge instructed
vectors into the production namespace.

## Priority plan and optional worker integration

```bash
python scripts/m5l_backfill.py \
  --db data/research.sqlite3 \
  --index-db data/m5i/qwen-8f1b.semantic.sqlite3 \
  --scheduler-db data/NEW-m5l-scheduler.sqlite3 \
  --output data/NEW-m5l-backfill.json
```

Source and semantic index use `mode=ro`. Only the separate scheduler is written.
Its schema `economic-backfill/m5l-v1` binds absolute source/index paths and the
exact active namespace. Unknown schemas/bindings fail closed. Plan creation
streams eligible documents and validates current heads; it is an O(eligible
catalogue) scan, not a cheap per-request step. All activity/liquidity/category and
administrative-horizon denominators are reported. Rule-version contract data
intentionally omits volume, so activity comes from the matching archived catalogue
entry with its observation ID, not an invented rule field.

`--at ISO_UTC` explicitly requests historical replay, never current eligibility.
A refresh replaces only the derived task snapshot, retaining the per-venue fair
cursor/slot. It does not delete source evidence, vectors or completed research.
Take the normal SQLite backup before modifying any important state. The CLI
refuses source/index/scheduler path collisions. Do not run simultaneous plan
writers; the application worker takes a separate scheduler writer lock.

The worker's optional `--scheduler-db PATH` must name an existing prepared plan,
and `--expected-identity PIN` must match the existing index namespace. This path
was integration-tested using hypothetical data; it was **not run against production**.
Missing/incompatible plans fail rather than silently reverting to ordinary order.
The legacy default is unchanged when the option is absent.

Every fourth successful work slot traverses stable hashed backfill order, so
lower-priority categories retain progress. Selection itself does not acknowledge
work. Only existing, current, checksum-valid committed vectors allow advancement.
A crash between index commit and cursor commit safely rechecks cached work; it
does not report uncommitted vectors complete. Stale snapshots (>24 hours), changed
source versions, closed contracts and cached vectors are excluded. The scheduler
rechecks source freshness and demotes expired depth/event-date bonuses; it does
not refresh source timestamps. Inference failures can still prevent progress.
No background service was started and no prior deadline/checkpoint was extended.

## Offline evaluation and economic replay

```bash
python scripts/m5l_evaluate.py --benchmark data/m5l/benchmark \
  --directory data/NEW-m5l-replay --at 2026-10-31T19:41:22.542350+00:00
python scripts/m5l_production_compare.py --db data/research.sqlite3 \
  --index-db data/m5i/qwen-8f1b.semantic.sqlite3 \
  --at 2026-10-31T19:38:36.591860+00:00 --output data/NEW-m5l-production.json
python scripts/m5l_economics.py data/m5l/nba-capture data/m5l/nfl-capture \
  --output data/NEW-m5l-economics.json --fixture data/NEW-m5l-public-fixture.json
python -m unittest discover -s tests -v
```

Evaluation makes no inference/venue calls. It verifies raw inference SHA-256,
model provenance, input hashes and actual exported vectors before using them.
Current-clock mode refuses stale/ineligible corpus definitions; `--at` supports
explicit historical replay using the preserved archives. Do not move receipt clocks
backward to accommodate newer vectors. Production comparison never advances
retrieval checkpoints. If source heads change later, use retained matching archives;
a historical clock alone cannot restore overwritten heads.

Review packets keep independent labels null until reviewed. Development corpus
metrics exclude UNLABELED pairs from precision and retain their count. Production
sampling includes returned and displaced candidates and exposes incomplete traversal
and bucket saturation. A stratified bounded sample is not venue-wide recall.

Economic replay recomputes book validity at each actual capture assessment clock.
Current stopped streams are not live quotes. Rejected commitments return `null`
net returns and quantities, not zeros or simulated profits. Passing economics
belongs to the existing human-approved research evaluator; this diagnostic has no
approval shortcut. Fees were captured into separate `research.sqlite3` files,
while quotes/stream frames are in `capture.sqlite3`; do not confuse their raw IDs.

Actual live smokes used the existing `soak run` coordinator for 45 seconds per
pair with `--protocol clocked`, five-second US polling and 45-second segments.
The first attempted two-second poll was refused by the existing five-second lower
bound before capture; it is not a successful run. Four `research fees-capture`
commands produced NEEDS_OPERATOR_REVIEW packets, never imported profiles.
Research readiness exited 2/BLOCKED, as expected. Current captures have expired;
any later research requires fresh data and explicit review, not automatic renewal.
