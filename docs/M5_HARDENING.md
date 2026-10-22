# M5 pre-run operational hardening

This focused review addresses monitoring gaps before the operator's multiweek
test. M5 remains **IN PROGRESS**, and M4's 30-day acceptance is still pending.
No schema migration, new venue fields, live credentials or trading capability
were introduced. Existing archives and service configuration were preserved.

## Changes

- Health now distinguishes a running process from useful recorded research:
  empty cycles and cycles blocked before economics generate explicit warnings.
  A valid calculation with zero budget or no profitable edge still counts as an
  economic observation. Counts are scoped to the selected session's latest cycle;
  stale and future cycle clocks remain explicit. Historical counts never assert
  that quotes remain usable now.
- Disabled refresh generates a startup warning in SQLite and stdout/journal.
  The example still defaults to one cycle with no network refresh. With refresh
  enabled, only currently approved pairs are collected.
- Backup monitoring bounds manifest reads, validates the local manifest contract
  and checks that a nonempty snapshot actually exists. An orphan, malformed or
  future-dated manifest cannot hide the lack of a recent backup. A 26-hour age
  allowance accommodates the daily timer's jitter and verification time.
  Content hashes/integrity are still checked by `verify-backup`, not by health.
- Wall/monotonic divergence is checked after scan and paper processing as well
  as before each cycle. A jump during the final cycle now stops with exit 2,
  identifies the affected cycle and preserves committed evidence for review.
  A post-scan jump prevents further paper processing in that invocation.

Usage and failure handling are in [operations](OPERATIONS.md).

## Verification actually performed

The unchanged baseline passed **154 tests**. After changes:

```bash
.venv/bin/python -m unittest discover -s tests -p test_operations.py -v
.venv/bin/python -m unittest discover -s tests -v
```

The targeted command passed **28 operations tests**; full discovery passed
**165 tests**. The [full test log](evidence/M5_HARDENING_TESTS.txt) names every test.
Added cases cover empty/session-isolated/stale/future/gated economic observations,
valid zero-budget calculations, invalid cycle evidence, disabled refresh, forward
and backward clock jumps during a final scan, clock divergence during final paper
processing, slow work without a jump, missing/empty/future snapshots, daily jitter,
unreadable/oversized/malformed manifests and missing/invalid manifest fields.
Faults use explicitly hypothetical fixtures and probes; none is an observed venue
execution or actual host clock change.

[CLI smoke evidence](evidence/M5_HARDENING_SMOKE.json) records the exact arguments,
stdout, stderr and exit status of **15 commands**, all exiting 0:

- The seven-case hypothetical M5 demo and original demo/report.
- Zero-budget research start, a real two-cycle monitor invocation with refresh
  disabled, and research summary reporting exactly two cycles and no acceptance.
- Backup, full verification and new-path restore with matching logical hashes.
- Health, text metrics, event listing, empty paper report and daily backup helper.
- A second health check after deleting only a disposable smoke snapshot,
  confirming `BACKUP_SNAPSHOT_MISSING` despite its retained manifest.

Smoke databases lived in automatically cleaned temporary directories; their
captured command paths describe that run and are not persistent artifacts. The
actual host clock probe returned `NTPSynchronized=yes`. The sandbox initially
blocked system-bus access, so the read-only probe and bounded smoke script ran
with approved host access. No clock state, service, account or deployment settings
were changed. No live venue requests were made during this review; existing
provider fixture replay tests ran offline. `git diff --check` also passed.

## Remaining run prerequisites and limits

The documented lack of real approved pairs, live fee applicability and a
timestamped Kalshi book feed still blocks useful cross-venue economic evidence.
An endurance run can validate monitoring and recovery while these gates reject
data; elapsed uptime alone cannot satisfy M4/M5 acceptance. Inspect `ops health`
and `research summary` after the first completed cycle and daily thereafter.

Full backup verification/restore drills, storage planning and operator review of
local alerts remain necessary. Source and backup retention are not automatically
pruned. Large-archive verification cost, actual service sandbox behavior, reboots,
off-host recovery and multiweek coverage/incident auditing remain field work.
Clock checks occur at boundaries; an excursion that reverses entirely between
checks can evade detection. Committed cycles flagged by a clock-jump event require
review and must not be counted as clean evidence merely because they exist.

These checks establish local behavior, not multiweek acceptance. Stop before M6.
