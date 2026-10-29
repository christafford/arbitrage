# M5I 24-hour run — post-run findings

**The bounded run stopped successfully; the full backfill and retrieval-quality
acceptance did not complete.** Both services exited successfully at the configured
October 29 **13:31:44 UTC / 09:31:44 EDT** deadline. All four full refresh rounds
completed for both venues. The expired units are now disabled; no further run was
started. No real contract approval, trading, fee or collateral decision was made.

## Coverage at shutdown

| Venue | Eligible definitions | Indexed | Coverage | Backlog |
| --- | ---: | ---: | ---: | ---: |
| Kalshi | 119,035 | 18,794 | 15.79% | 100,241 |
| Polymarket US | 9,108 | 9,108 | 100% | 0 |
| Total | 128,143 | 27,902 | 21.77% | 100,241 |

Metadata synchronization covered **411,558 archived instrument heads** with zero
unsynced heads. These include unavailable/expired instruments and are a different
denominator from current eligible contracts. Polymarket US's 100% means the
eligible subset at shutdown, not every market offered by the venue.

The shutdown table was recomputed from the stopped archives at the fixed deadline
and matches the last persisted coverage counts. At the later **15:35 UTC** review,
953 indexed Kalshi definitions had closed: eligible coverage was 17,841/118,048,
with 100,207 still unindexed. Vectors were retained; this change reflects time-based
eligibility rather than loss of cached data. Venue/category/deadline breakdowns
and both clocks are preserved in the [final evidence](evidence/M5I_RUN_20261028_FINAL.json).

The pinned model namespace contains 31,249 vector records, including definitions
that are no longer eligible. Another 1,456 vectors remain isolated under the
alternate fingerprint observed before the pin. They are not combined to inflate
coverage. The original namespace contained 1,136 vectors before the run.

## Collection and inference

| Round | Kalshi run / unique markets | US run / unique markets |
| --- | --- | --- |
| 1 | 24 / 156,891 | 25 / 82,413 |
| 2 | 26 / 157,838 | 27 / 83,073 |
| 3 | 28 / 159,384 | 29 / 80,706 |
| 4 | 30 / 155,376 | 31 / 78,424 |

All eight runs reached terminal pagination. Final collection completed at 09:43
UTC for Kalshi and 09:34 UTC for US on October 29; full metadata synchronization
completed at 10:06 UTC. Pagination is a traversal, not an atomic census. Counts
across refreshes must not be summed as distinct markets.

There are **106 completed background worker reports**: 96 READY and 10 FALLBACK.
They record 22,032 Kalshi and 9,089 US definition completions, 2,190 HTTP attempts,
and 60,413.80 worker seconds. That is **0.515 definitions/second** of worker time,
including probes, inference and local processing, well below the initial short-run
1.819/second. Startup checks and an interrupted worker are excluded from this
throughput calculation; their successfully committed vectors remain in the index.
This is not isolated GPU performance or a reliable full-backfill ETA.

Two batches reported `SERVICE_UNREACHABLE`. Eight reported `HTTP_OR_SIZE_ERROR`;
the raw archive confirms **24 HTTP 502 responses** between 12:33 and 13:25 UTC on
October 29. The last successful vector receipt was at 12:32:32 UTC. Thus the final
hour made no further inference progress. The underlying cause of the 502s has not
been established. The runner backed off and still performed retrieval. No complete
background report recorded a pinned-identity mismatch.

The command archives also show the planned SIGINT interruption when applying the
identity pin and one writer-lock collision during restart; later commands recovered
and continued. Neither service ended in failure. No journal files were available
at post-run review, so this audit relies on captured command reports/stderr,
source/raw observations, final status files and systemd exit status rather than
claiming a complete host incident audit.

Source/index files grew by approximately **16.63 GiB**, from 8.28 GiB to 24.91 GiB,
excluding the preserved pre-run backups. About 818 GiB remained free. Raw evidence
was retained. Sustained operation needs a storage budget as well as a vector budget.

## Retrieval quality: a material remaining gap

There were **106 retrieval reports**, totaling 26,326 query executions. These are
not distinct-query coverage. The final 250-query window was incomplete, reported
125 capped approximate probes and zero vector-validation failures. Full-catalogue
retrieval recall is not established.

The [final persisted queue](evidence/M5I_RUN_20261028_FINAL_QUEUE.json), ranked at
13:25 UTC, contains **100 distinct events**: 53 sports identity, 42 keyword and five
embedding-assisted suggestions. All are `UNVERIFIED`. These are archived candidate
snapshots, not fresh executable quotes or independently accepted matches.

Inspecting the archived public definitions for those five semantic suggestions
found four material differences that **the automatic `known_contradictions` field
did not flag**:

| Suggestion | Assistant assessment of archived definitions |
| --- | --- |
| December Fed 25-basis-point hike | Same ordinary decision, but US rounds off-grid rate changes into displayed buckets; Kalshi specifies an exact 25-basis-point hike. Settlement rules differ. |
| Spotify “Stateside” | Promising ordinary-event candidate: both name the same song and the 2026 Spotify Wrapped global top-song ranking. Full operator settlement review remains required. |
| Elon Musk net worth | Different thresholds: more than $1.7 trillion versus at least $1.2 trillion. |
| Supreme Court appointments | Different propositions: count of confirmations during a presidential term versus Barbara Lagoa becoming the next justice. |
| Bitcoin year-end price | Different threshold, direction and observation period: above $199,999.99 during a window versus at or below $19,999.99 at a final timestamp using a trimmed one-minute statistic. |

The [five-case review](evidence/M5I_RUN_20261028_SEMANTIC_REVIEW.json) preserves IDs,
links, source receipts, definition versions, public text, retrieval reasons and
assistant assessments. These labels are not independent adjudication or legal
approval. Four mismatches in this selected five-item sample are not a venue-wide
precision estimate. The Spotify suggestion is not proven new relative to a
controlled deterministic baseline; four of the five suggestions also had keyword
retrieval support. **Incremental semantic discovery yield remains unproven.**

UNVERIFIED/approval gates continued to prevent action, but contradiction detection
is incomplete. The next implementation work should repair numeric units and
inequalities, observation-window comparisons, proposition types, and exceptional
settlement-rule differences, using these genuine cases as regressions. The Qwen
502 failure also needs diagnosis before another sustained inference run. Remaining
Kalshi backfill can then resume from the existing namespace and checkpoints.

## Verification and acceptance

The post-run full suite executed **377 tests**, all passing in **18.206 seconds**
with `python -m unittest discover -s tests -v`; the
[exact output](evidence/M5I_RUN_20261028_POST_TESTS.txt) is retained. Existing tests
passing does not cover the four newly identified semantic contradiction misses.
An optional read-only full SQLite integrity/foreign-key scan was stopped after
approximately ten minutes without a completed result to bound this review; **no
post-run full-database integrity pass is claimed**. That limitation is recorded
in the final evidence. Verified pre-run backups remain available.

The 24-hour bounded orchestration and four catalogue refreshes are observed.
Full Kalshi vector coverage, complete retrieval traversal, independently adjudicated
quality, contradiction handling for these cases, and demonstrated additional
reviewable events remain open. This run does not satisfy M4/M5 economics, trading
readiness or M6 authorization.
