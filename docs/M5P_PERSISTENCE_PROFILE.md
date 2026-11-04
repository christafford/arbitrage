# M5P — persistence and validation profiling

This is the preserved original profiling report. The operator subsequently
authorized the [atomic-final-commit follow-up](M5P_ATOMIC_FINAL_COMMIT.md); its
implementation, tests and new measurements are recorded separately.

The operator authorized profiling after the stronger-candidate screen identified
material cumulative Kalshi pending-barrier time. This follow-up measures the
unchanged collector in new, isolated local archives. It does not renew any capture,
change transaction boundaries, lower durability, bypass validation, or alter
freshness, sequence, source-clock, settlement or approval gates.

## Frozen method

`scripts/m5p_profile.py` reads each pair's first connection from the completed
second-candidate archive through SQLite `mode=ro`. It freezes the first 256 frames
(or that connection's entire available prefix if shorter), including subscription
acknowledgment and initial snapshot. There is no substitution of a better connection.
The plan and exact fixture bytes are saved before timed runs.

Three repetitions per pair alternate instrumented/plain execution order. Each
execution uses a fresh database on the collector's existing data filesystem, the
same production `kalshi_ws.capture`, `ws_store` and `KalshiBookStream` functions,
WAL, synchronous FULL and all four per-book commits. A delegated connection times
real execute/commit calls without modifying them. Nested phase measurements record
wall and thread CPU nanoseconds, including exclusive totals to prevent double
counting. SQLite commit wall time includes possible synchronization, checkpoint,
scheduling and filesystem costs; it is not an isolated physical-device metric.

The transport is explicitly hypothetical and offline, serving genuine archived
bytes at original historical receipt clocks. No credentials are loaded; network
socket creation is prohibited while capture runs. Metadata is revalidated from
its archived source. Historical clocks allow deterministic validation and do not
represent current quote validity. The deadline inside this simulated clock is a
local benchmark artifact, not a renewal of the original observation window.

The actual M5P journal executes its normal hash, append and state-accounting work.
Only Kalshi events are supplied: other receiver threads, US state, polling samples,
real network waits and cross-thread contention are absent. These serial unpaced
prefix measurements cannot predict live wall-time coverage or concurrent throughput.
Per-execution real-time work is capped at 120 seconds, with a 600-second overall
budget. Failures retain a FAILED status and their partial raw archives.

## Integrity acceptance

Every replayed raw frame, status and normalized book must match the archived
original, including intermediate books. Instrumented and plain executions must
have the same normalized digest. Post-run checks verify raw hashes, SQLite
integrity/foreign keys, journal hash chains and pending-before-book publication.
Original archive hashes must remain unchanged. No performance threshold can turn
an integrity failure into a passing run.

Tests use a genuine four-frame source fixture and explicitly labeled hypothetical
faults for hash tampering, missing clock, invalid price, sequence gap, stale source,
partial depth, false expected output and storage failure. An independent SQLite
reader verifies that pending raw/provenance records are committed before book
validation. Existing output directories cannot be overwritten. Nested timing
accounting is checked with deterministic clocks.

[Official source receipts](evidence/M5P_PROFILE_SOURCES.json) recheck Kalshi stream,
connection and market schemas plus SQLite WAL/synchronous documentation. Existing
consumed fields and schemas are reused. No US or international endpoint is called.
The [genuine regression fixture](../tests/fixtures/m5p-profile-live.json) retains
exact public bytes, original schema/receipt clocks and hashes; its expected books
are derived local evidence, not an exchange response.

## Reproduction

Use a new output directory; the source must be a completed M5P archive:

```bash
.venv/bin/python scripts/m5p_profile.py \
  --source data/m5p/second-candidate-20261104/screen-01 \
  --output data/m5p/persistence-profile-20261104/baseline-01 \
  --frames 256 --repeats 3
.venv/bin/python -m unittest discover -s tests -v
```

Instrumentation patches are process-local and intended only for this dedicated
serial command. Do not import/run the profiler alongside an active collector in
the same process. Product collectors do not import the profiling module.

## Measured results

All **18** baseline executions passed: 256 frames × three pairs × three
repetitions × instrumented/plain. That is **4,608 replayed frames, 4,590 normalized
books and 4,626 verified raw records** including each execution's metadata.
Every intermediate normalized result matched its original and its plain/profiled
counterpart. Original source archive hashes stayed unchanged. The launch-time
61 source files are preserved under the baseline archive's `code/` directory.

[Full run evidence](evidence/M5P_PROFILE_RUNS.json),
[aggregated measurements](evidence/M5P_PROFILE_SUMMARY.json).

| Pair | Median plain time, 256 frames | SQLite commit share | Stream validation/reconstruction share | Journal share |
| --- | ---: | ---: | ---: | ---: |
| Senate reference | 3.815s | 60.13% | 23.54% | 4.95% |
| Michigan Senate | 3.674s | 63.69% | 20.31% | 4.91% |
| Georgia Governor | 3.854s | 63.02% | 20.55% | 5.04% |

Shares use exclusive wall-time accounting across the three instrumented runs for
each pair. Journal includes its engine/hash/append work; nested timings must not
be summed again. Real SQLite commits averaged **2.28–2.29ms**. Two occur while
archiving raw/provenance and two while recording the validated normalized book.
The latter two alone consumed **29.57–31.98%** of total capture time in this probe.

Median instrumented versus plain run time varied from **−3.16% to +1.13%**.
This is observed order/cache/scheduling variation mixed with instrumentation
overhead, not proof of zero overhead or a speedup. No collector optimization was
implemented. The benchmark preserves WAL auto-checkpoint settings and does not
separate individual checkpoint/fsync/device service times.

A separate three-run [CPU diagnostic](evidence/M5P_PROFILE_CPU.txt) used
`cProfile` with `thread_time_ns`, limited to capture itself. It verified the same
normalized results. Most validation CPU work sits in complete book reconstruction
and price/quantity validation: 255 books invoked `_levels` 1,276–1,277 times and
`exact` 121,468–153,238 times per prefix. Metadata rules were checked 510 times.
`Book.as_dict`/recursive dataclass conversion is another visible cost when writing
normalized results. CPU profiling adds substantial overhead; its absolute times
must not be compared with the baseline wall times. Call counts identify work,
not permission to omit checks.

The measured commit share supports a local persistence explanation for part of
the previous screen's accumulated pending time. It does not establish the cause
of every live gap: raw archival commits precede the journal's pending event,
and network, competing workers, clock age and US cadence also affect coverage.

## Recommended next change

First test **one atomic final transaction for validation status plus normalized
book persistence**, replacing those two final commits with one. Keep the raw and
pending-provenance commits, synchronous FULL, all validation and the pending
barrier. Publish a book only after the final commit succeeds. This is a narrow
candidate optimization, not an implemented change or promised coverage gain.

Acceptance should include crash/failure injection before and during final commit,
independent-reader visibility, identical intermediate normalization/rejections,
same-source repeated before/after profiling, and then a separately bounded live
validation before claiming coverage improvement. Avoid changing durability to
NORMAL/OFF, batching unvalidated frames, or making a pending book usable. Only
after this should repeated full-depth parsing/serialization be considered for a
separate, equivalence-tested optimization.

## Verification and limits

The full command `.venv/bin/python -m unittest discover -s tests -v` executed
**574 tests, all passing in 24.054s**; [complete test names and output](evidence/M5P_PROFILE_TESTS.txt).
The ten new profiling tests also passed independently. A four-frame CLI smoke
passed all six plain/profiled executions, followed by the 18-run benchmark and
three CPU probes above. No production collector module, schema, credential,
model/index, quality gate or service was changed. No live market-data or inference
requests were made by the benchmarks; official documentation was fetched separately.
The stronger second-candidate and sustained-quality acceptance gaps remain open.
