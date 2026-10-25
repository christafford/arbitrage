# Collection-soak implementation and verification — 2026-10-25

The M5A operational extension adds `predarb soak run` and `predarb soak report`.
It coordinates selected Kalshi streaming and Polymarket US polling in one writer,
with independent HTTP cooldowns, explicit connection generations, current-time
freshness samples, storage guards, heartbeat reporting and verified backup pauses.
No production schema, pair approval, fee applicability, research economics or
trading behavior was changed. See [operation and limits](COLLECTION_SOAK.md).

## Tests executed

```bash
.venv/bin/python -m unittest discover -s tests -v
```

**307 tests passed** in the final full run, with no skipped tests. Exact test names
and results are in [SOAK_TESTS.txt](evidence/SOAK_TESTS.txt). The new tests cover
coordinated archive/replay, quiet-feed reconnects, polling during backoff,
missing fields, wrong identities, invalid prices, partial liquidity, stale source
timestamps, failed-refresh barriers, HTTP recovery and cross-attempt cooldowns,
clock/cutoff/resource limits, periodic verified backups, graceful stop and stale
heartbeats, CLI exits, and signal-handler restoration. Hypothetical inputs remain
visibly labeled and cannot become approved registry records.

The actual US stale-source response is preserved in a separate public fixture and
replayed with its original bytes and receipt clocks. This verifies that a successful
HTTP response does not make an old book source timestamp fresh. Earlier targeted
and full runs were used during implementation; the final full run supersedes them.
Compilation and Git whitespace checks also passed.

## Live smoke evidence

The first 90-second smoke ran from **15:10:34 to 15:12:04 UTC** on October 25 in
`data/soak-smoke-20261025a/`, using the rejected Fed contracts as transport inputs.

- Eight US detail/book polls completed, with no HTTP polling failures. All eight
  book assessments had `STALE_SOURCE`; no US book was counted usable.
- Kalshi captured eight usable snapshots over eight connections. No delta arrived
  during this quiet interval. Eight five-second message timeouts were retained,
  with six recovery snapshots recorded inside segments. This does not demonstrate
  new snapshot/delta live acceptance or uninterrupted continuity.
- Eight periodic samples included five fresh Kalshi samples, zero fresh US samples,
  and zero samples with both venues fresh. The maximum observed sample gap was
  11.554 seconds and the maximum US poll duration 1.150 seconds.
- The run completed its duration but exited **2 / INSUFFICIENT_USABLE_DATA**.
  Source-time checks were preserved, not relaxed to make the smoke pass.
- Two backup files passed hash/logical verification. The final backup restored
  successfully into a new path. All raw observation hashes were verified.

A second CLI smoke using the final implementation was stopped with SIGTERM.
It exited **2 / STOPPED / SIGNAL_STOP**, closed its stream, and produced two
verified backups. A concurrent CLI writer was rejected before making a request;
the read-only report remained available. Existing output-directory reuse and
invalid configuration both exited 1 without overwriting the prior report or
creating the invalid-run path. Exact commands/results and manifests are in
[SOAK_VALIDATION.json](evidence/SOAK_VALIDATION.json).

The main research database still has pair 1 `REJECTED`. No main catalogue refresh,
new approval, funding or account operation was performed. The new archives are
isolated. Source-document URLs, retrieval times and hashes are in
[SOAK_API_CHECKS.json](evidence/SOAK_API_CHECKS.json).

## Outstanding acceptance

The 24-hour operational test and post-run inspection remain pending. A successful
start or completed duration alone does not satisfy acceptance. Review actual
freshness/skew samples, gaps, recovery, resource growth and restore/replay before
extending the run. Current evidence already shows stale US data on this test
instrument. Overall M5A, M4's 30-day economics and M5's multiweek run remain open.
The pre-rollout protocol cutoff remains October 29 at 00:00 UTC; the clocked
protocol still needs live revalidation before a run crossing that boundary.
