# M5P — atomic final book commit

The operator authorized this offline follow-up to the
[persistence profile](M5P_PERSISTENCE_PROFILE.md). It combines validation status,
book-capture classification and normalized-book insertion in one final SQLite
transaction. Raw response archival and pending frame/provenance archival still
commit separately before validation. Each accepted book now needs three commits
instead of four. No frame batching, validation shortcut or schema migration is
introduced; WAL, synchronous FULL and the existing pending barrier remain intact.

## Transaction and publication behavior

`ws_store.record_frame` requires a connection without an unfinished transaction.
It serializes the validated book, begins an explicit transaction, updates raw
validation status without committing, updates capture classification, inserts the
normalized result, then commits once. Missing capture or frame provenance fails
closed. `store.validate_observation` keeps its original immediate-commit behavior
for all other callers; deferred status writes require an active transaction.

Any exception or interruption in finalization rolls back its unfinished writes
before capture cleanup can commit a disconnect. Already committed raw bytes,
hashes, provenance and pending captures survive. Both book callbacks still occur
only after successful finalization. No earlier usable book can bypass a newer
pending frame through the existing latest-book lookup.

Independent readers see the pending record until all final writes commit. A reader
holding an older SQLite read transaction continues seeing its original snapshot
until it starts a new one. A process death before commit leaves pending state; a
death after commit leaves the whole final record. If commit has completed but the
caller loses its acknowledgment, rollback cannot undo it: the complete record
remains, no callback publishes it, and ordinary exception cleanup closes the
connection generation. A hard-killed process cannot run disconnect cleanup;
existing stream liveness limits and the journal's pending state remain relevant.
A leftover benchmark `RUNNING` status is incomplete evidence, never success.

SQLite's [transaction behavior](https://www.sqlite.org/lang_transaction.html) and
[WAL/FULL semantics](https://www.sqlite.org/pragma.html#pragma_synchronous) were
rechecked alongside the existing Kalshi stream schema.
[Raw source receipts](evidence/M5P_ATOMIC_SOURCES.json) preserve hashes and UTC times.
No new venue field, metadata interpretation or API path is used.

## Verification method

The unchanged [genuine prefix fixture](../tests/fixtures/m5p-profile-live.json)
retains public raw bytes, source schema versions, original UTC receipts and expected
intermediate books. The new
[hypothetical fault plan](../tests/fixtures/m5p-atomic-faults-hypothetical.json)
is explicitly local fault injection, not purported venue evidence.

Boundary tests inspect independent readers after each final write, before commit,
and after commit. Tests inject storage exceptions after status/capture/normalized
writes, a pre-commit failure, a real SQLite deferred-foreign-key rejection at commit,
and `KeyboardInterrupt`. Subprocess tests terminate without Python cleanup after
writes, at commit entry, inside SQLite's COMMIT VM entry callback and immediately
after commit. They verify raw hashes, pending/complete state, foreign keys, database
integrity and absence of book publication. These are process-crash and software
failure tests; no physical disk failure, fsync interruption or power-loss experiment
is claimed. Existing malformed/missing fields, invalid prices, stale source,
sequence loss, partial liquidity and exact replay tests run against the new path.

## Reproduction and measurements

The new local archive is `data/m5p/atomic-final-20261104/`. The `before/` benchmark
ran the original code; `after/` uses the atomic transaction. Both freeze the same
first 256 frames of the first connection for every pair in the completed
second-candidate screen. Three repetitions alternate instrumented/plain order
within each version. The before and after versions run as separate blocks, so
filesystem/cache/scheduling drift is a limitation. Each run uses a fresh isolated
archive and real WAL/FULL commits on the same filesystem. No network transport,
credential loading or inference occurs in replay; documentation fetches are separate.

```bash
# Use a new destination; this now measures the atomic implementation.
.venv/bin/python scripts/m5p_profile.py \
  --source data/m5p/second-candidate-20261104/screen-01 \
  --output data/m5p/atomic-final-NEW/after --frames 256 --repeats 3
.venv/bin/python -m unittest discover -s tests -v
```

Per-run plans preserve source-code hashes; frozen fixture digests, effective SQLite
settings, normalized-result digests and original archive hashes must match before
any timing comparison. Historical receive clocks exercise unchanged validators;
real performance/thread clocks measure local execution. This serial Kalshi-only
prefix benchmark is not a live multi-pair coverage measurement.

All **36 executions passed** (18 before, 18 after), replaying **9,216 frames**,
**9,180 normalized books** and **9,252 raw records** including metadata across
executions. Every intermediate book matched its genuine source expectation.
Eighteen matched before/after executions also had exact equality across all rows
and columns in `raw_observations`, `book_captures`, `normalized_books`, `ws_frames`,
`ws_connections` and `catalogue_entries`. Original archive hashes stayed unchanged.
SQLite reported WAL, synchronous **2 (FULL)**, foreign keys enabled, 4,096-byte
pages and the unchanged 1,000-page auto-checkpoint setting.

| Pair | Median plain before | Median plain after | Observed wall-time reduction |
| --- | ---: | ---: | ---: |
| Senate reference | 3.877s | 3.394s | 12.46% |
| Michigan Senate | 3.672s | 3.185s | 13.25% |
| Georgia Governor | 3.703s | 3.507s | 5.29% |

Each 256-frame execution includes one acknowledgment and 255 books. Across three
instrumented runs per pair, total timed commits fell **3,078 → 2,313**, and final
book commits fell **1,530 → 765**. Both raw and pending-provenance commit counts
remain one each per frame. Commit timings include checkpoint/scheduling costs;
these observed reductions do not isolate physical-device latency or guarantee a
specific speedup under concurrent receivers.

[Comparison, exact table digests and method limits](evidence/M5P_ATOMIC_COMPARISON.json),
[all before runs](evidence/M5P_ATOMIC_BEFORE_RUNS.json), and
[all after runs](evidence/M5P_ATOMIC_AFTER_RUNS.json) preserve the measurements.
Baseline source hashes bind the recorded base Git commit. Local `before-store.py`,
`before-ws_store.py` and corresponding `after-` copies preserve the changed modules.
The old profiling evidence and expired capture configurations were not modified.

Verification actually executed:

- `.venv/bin/python -m unittest discover -s tests -v`: **581 tests passed in
  25.384s**. [Every test name and result](evidence/M5P_ATOMIC_TESTS.txt).
- `.venv/bin/python -m unittest discover -s tests -p 'test_atomic_frame_commit.py' -v`:
  seven tests passed; the finalized fixture-driven versions also passed in the
  full suite. An initial test import error was corrected before successful runs.
- `.venv/bin/python -m unittest discover -s tests -p 'test_persistence_profile.py' -v`:
  all ten existing profiling/replay tests passed with the new commit counts.
- `scripts/m5p_profile.py` with `--frames 256 --repeats 3` ran once before and
  once after, using the source above and separate `before/` and `after/` outputs.
  Both returned success; no timing experiment ran concurrently with the full suite.
- Four-frame CLI smoke: the same profiler with `--frames 4 --repeats 1` and
  output `data/m5p/atomic-final-20261104/smoke`: all six executions passed.
- `.venv/bin/predarb demo --db data/m5p/atomic-final-20261104/demo.sqlite3` and
  `.venv/bin/predarb report --db data/m5p/atomic-final-20261104/demo.sqlite3`:
  passed, visibly hypothetical. [Smoke output](evidence/M5P_ATOMIC_SMOKE.txt).
- `git diff --check`: passed.

Offline final-transaction acceptance is satisfied. This does not complete the
broader M5P quality milestone.

## Remaining scope

This task establishes only offline integrity and local execution costs. Stronger
second-candidate selection, held-out multi-pair quality, sustained coverage, US
continuity and independent settlement/fee/mechanics review remain open. No capture,
service restart, expired deadline renewal, inference/model/index change, funds,
orders, automatic approvals or M6 work is authorized by these measurements. Live
coverage improvement would require a separately authorized bounded validation.
