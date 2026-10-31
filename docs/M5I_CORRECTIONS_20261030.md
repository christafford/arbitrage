# M5I keyword mismatch repairs and retrieval profile — October 30

**The four reported mismatch patterns are now detected and demoted.** A saved
100-event queue replay flags five pairs: the four reviewed examples plus the same
state-versus-US-Senate mistake for New Hampshire. Retrieval is approximately 16%
faster in the measured 250-query replay. Backfill services remain stopped.

## Proposition checks

`proposition-guards/m5i-v2` compares explicit asserted fields:

| Observed case | New material conflict |
| --- | --- |
| NC or NH state-senate control versus US Senator election | `POLITICAL_OFFICE_CONFLICT` |
| Musk appointed CEO of X versus departing as Tesla CEO | `CEO_COMPANY_CONFLICT`, `CEO_ACTION_CONFLICT` |
| Spotify USA #2 song versus #1 | `RANKING_POSITION_CONFLICT` |
| December Fed hike versus no change | `RATE_DIRECTION_CONFLICT` |

The checks use the first settlement assertion rather than later examples or
contingencies. `U.S.` is normalized locally before sentence splitting; original
public text remains unchanged. Ambiguous/missing offices, mixed companies/actions,
multiple rankings and negated rate directions stay unknown. The CEO parser
currently recognizes X/Twitter and Tesla; it is not a general entity resolver.
Ranking detection is limited to explicit Spotify song/artist/album wording.
These are bounded language guards, not comprehensive legal interpretation.

The [new genuine fixture](../tests/fixtures/m5i-keyword-mismatches-genuine.json)
contains 11 archived market definitions for four negative pairs and two positive
Spotify #1 controls. Parent raw bytes/hashes, adapter schemas, excerpt hashes,
source IDs, URLs and original receipt clocks are retained. Labels are assistant
annotations, not operator adjudication. It consumes existing documented public
fields; no new venue schema is assumed. Current official detail schemas were
captured during the October 30 run audit.

Deterministic comparison, sidecar retrieval and saved queue reads all use these
checks. Old feature rows and empty warning lists are recomputed on read; vector
contents, model namespaces and embedding text do not change. The 100-event
[historical replay](evidence/M5I_CORRECTIONS_20261030_REPLAY.json) demotes all five
newly flagged pairs to score zero, with material conflicts ordered before scores.
No archived source or production queue was rewritten during validation. A raw old
JSON snapshot remains historical evidence; inspect the replay or current reader
for corrected warnings. Similarity of 1 in hypothetical stress tests cannot remove
the conflicts. All candidates remain UNVERIFIED.

## Measured retrieval cost

The first read-only cProfile run used 50 queries against the actual 457,661-document
sidecar, fixed at the last saved queue clock. Of its 38.13 instrumented seconds,
27.54 were in vector candidate retrieval, including 14.91 in vector unpacking and
validation. The full coverage scan took 7.68 seconds. Timings overlap within the
call tree and must not be added together. Profiler overhead is substantial;
these timings are not comparable to uninstrumented wall times below.
[Call profile](evidence/M5I_PROFILE_20261030.txt).

The vector path now validates the checksum and length, unpacks the coordinates,
and checks the unit-norm interval using `math.hypot`. A valid unit-range norm
already establishes that every coordinate is finite; NaN, infinity, overflow,
zero vectors and nonunit values still fail. This removes a redundant Python
coordinate walk. Cosine multiplication uses `map(operator.mul, ...)` with the
same values, order, summation and threshold. No vector cache, dependency, candidate
cap change, approximate-index change or validation bypass was introduced.

The supervisor also uses the full coverage report already returned by retrieval,
rather than performing the same catalogue scan again. `BATCH_COMPLETE.coverage_at`
exposes that report's assessment clock. Explicit `index-coverage` remains available,
and initial full synchronization still reports coverage. AI outages still run
retrieval and report coverage before backoff.

Uninstrumented comparisons on the same archive and historical clock:

| Query budget | Before | After | Reduction | Result comparison |
| --- | ---: | ---: | ---: | --- |
| 50 | 15.64 s | 12.91 s | 17.49% | Entire retrieval/coverage output identical; 20 candidates |
| 250 | 54.22 s | 45.50 s | 16.10% | Entire retrieval/coverage output identical; 83 candidates |

Both implementations use the new proposition guards in the timed comparison;
this isolates the retrieval implementation change. Services enforced 256 MiB
memory, 64 MiB swap, 16 tasks and wall-clock limits. Python peak RSS was about
34–36 MiB in these comparisons. The initial uncapped instrumented trace reported
about 431 MiB peak RSS, so its memory figure is not a production-cap validation.
Neither timed comparison used cProfile or made network requests.

These are bounded hash-order windows, not a full query traversal or a sustained
run. They use `persist=False`, so the saved reservoir is not merged. Filesystem
caches were not controlled, and no collector/inference service ran concurrently.
A preliminary 250-query baseline preceded the final abbreviation fix; it was
excluded and rerun with the final guards. The final output comparison is exact.
The overnight run's 3.60 retrieval hours cannot simply be reduced by this percentage.
The duplicate coverage removal is separate; its next-run time savings are not yet
measured.
A final 50-query cProfile run under the same resource caps completed in 15.85
seconds: coverage used 7.64 seconds, vector candidate retrieval 5.47 seconds and
vector unpacking 0.76 seconds (overlapping cumulative times). Coverage is now the
largest cost in this sample. [Final profile](evidence/M5I_PROFILE_20261030_AFTER.txt). [Measurement/provenance manifest](evidence/M5I_CORRECTIONS_20261030.json).

## Reproduce and verify

The profile command opens source and index read-only, checks schema/source binding,
uses an explicit replay clock, does not advance checkpoints and makes no network
requests. It accepts 1–250 queries and a 1–600-second deadline. Use the same memory
limits as production when profiling this archive:

```bash
systemd-run --user --wait --pipe --collect \
  --property=MemoryMax=256M --property=MemorySwapMax=64M \
  --property=TasksMax=16 --property=RuntimeMaxSec=330 \
  "$PWD/.venv/bin/python" "$PWD/scripts/m5i_profile.py" \
  --db "$PWD/data/research.sqlite3" \
  --index-db "$PWD/data/m5i/qwen-8f1b.semantic.sqlite3" \
  --at 2026-10-30T10:56:38.146227+00:00 \
  --query-budget 50 --seconds 300 --cprofile \
  --output "$PWD/data/m5i-profile.json"
```

`--implementation` can load an explicitly preserved local `semantic.py` for a
performance comparator; other modules still come from the current checkout.
Use retained archives for historical comparison after production data changes.

**397 tests passed in 21.157 seconds** with
`python -m unittest discover -s tests -v`; [exact output](evidence/M5I_CORRECTIONS_20261030_TESTS.txt).
New tests cover the genuine mismatches and controls, ambiguous/negated wording,
old sidecar/main-queue revalidation, invalid vectors with valid checksums,
read-only profiling/bounds/source binding and outage reporting without duplicate
coverage. `pip check`, profile CLI help and both bounded production-size profiles
passed. The existing 49-definition corpus still returned 18/18 labeled positives
at Recall@20 and Recall@100 with 18/18 precision among returned candidates in
historical deterministic replay; no new inference, independently adjudicated
quality estimate or incremental semantic yield is claimed.

No production DB, model pin, source freshness, fees, timestamps, collateral or
approval gate changed. No new backfill run was started. Broader proposition
recognition, full vector/query coverage, production recall and operator adjudication
remain open; stop after M5I.
