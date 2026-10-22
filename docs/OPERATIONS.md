# Read-only operations and deployment (M5)

M5 provides local monitoring, bounded research/paper polling, process locking,
SQLite backup/restore and systemd templates. These tools cannot place orders or
send alerts to outside services. The units were syntax-checked; **no unit was
installed or enabled**. No multiweek uptime claim is made. See [results](M5_RESULTS.md).

## Health, metrics and alerts

```bash
predarb ops health SESSION_ID --db data/research.sqlite3 --backup-dir data/backups
predarb ops metrics SESSION_ID --db data/research.sqlite3 --backup-dir data/backups
predarb ops events --db data/research.sqlite3 --limit 100
```

The monitor records UTC health snapshots and append-only local alerts. Standalone
health/metrics/events commands are read-only and remain available while it runs.
Metrics are plain
Prometheus-compatible text on stdout, with no network listener. Alerts appear in
JSON, SQLite and the service journal; there is no email, Slack or webhook sender.
Operators must inspect these or connect their own existing monitoring separately.

HIGH health conditions block the monitor: unconfirmed clock synchronization,
low space, excessive database/WAL size, integrity failure or a large wall-clock
step. WARN conditions include absent/stale research heartbeat, absent/stale backup
manifest, failed latest collection and no cached approved pair. Cached approval
counts are descriptive; economic/paper consumers independently revalidate them.

Health also includes a `research` object for the selected session's latest cycle:

| Status | Meaning |
| --- | --- |
| `NO_CYCLES` | No committed observation cycle exists |
| `NO_PAIRS` | A recent cycle ran with an empty registry |
| `DATA_GATED` | Every pair was rejected before quote-based economics could be evaluated |
| `RECENT_ECONOMICS` | At least one pair reached economics; a zero budget or no profitable edge can still produce a rejection |
| `STALE` / `FUTURE` | The latest cycle clock fails the existing heartbeat age checks |

Empty cycles emit `NO_RESEARCH_PAIRS`; cycles entirely blocked by approval,
book or fee gates emit `NO_RECENT_ECONOMIC_OBSERVATIONS`. Both are WARN conditions.
Metrics `predarb_research_latest_pairs`, `predarb_research_latest_rejected`,
`predarb_research_latest_modeled_edges` and
`predarb_research_latest_economics_evaluated` expose the recorded counts. These
describe the latest cycle, not current quote validity or multiweek coverage.
Use the `research` status alongside the counts: stale cycles keep their recorded
counts. Hypothetical sessions remain explicitly warned and cannot establish live
coverage. Invalid or incomplete cycle evidence fails the health command.

`ready=true` means the process may run read-only monitoring, not that contracts,
fees or feeds qualify for economics. Zero approved pairs legitimately produce
empty/rejected cycles. Old backups and failed feeds remain warnings because a
bounded scanner can record and diagnose them without authorizing any trades.

The clock probe reads `timedatectl show --property=NTPSynchronized --value` with a
three-second timeout. False, unknown or unavailable state fails closed. The probe
does not measure clock offset or configure NTP. Runtime also compares wall-clock
elapsed time to monotonic elapsed time, stopping on a configured jump (default
1000 ms, maximum 5000 ms). Use the host's time service to investigate drift:

```bash
timedatectl status
timedatectl timesync-status
```

Other NTP implementations may require their own operator inspection; this runner
currently needs the documented timedatectl synchronization property. Do not
replace unknown state with a guessed successful probe.

Clock divergence is checked before a cycle, after its scan and after optional
paper processing, including the final cycle. A detected jump exits 2 and emits
`WALL_CLOCK_JUMP` to SQLite and stdout/journal with its phase and affected cycle
ID. Already committed source/derived evidence is preserved for review; a cycle
flagged `cycle_evidence_requires_review=true` must not count as clean observation
evidence. The post-scan check prevents further paper processing in that invocation.
These boundary checks cannot detect a clock excursion that reverses entirely
between checks.

## Bounded monitor

Copy [the example config](../examples/M5_MONITOR_CONFIG.json) and set an existing
live read-only session/database path:

```bash
predarb ops run --config path/to/session.json
```

The JSON fields are exact: `db`, `session_id`, `cycles`, `refresh`,
`shadow_policy`, `min_free_bytes`, `max_db_bytes`, `backup_dir`,
`max_clock_jump_ms`. `refresh` is a boolean; `shadow_policy` is either null or the
full object from [the paper policy](../examples/M5_PAPER_POLICY.json), not a path.
The default example runs **one cycle**, without refresh or shadow generation.
The fixed M4 session supplies budgets and polling interval; it grants no funding
or order authority.

When `refresh=false`, startup emits `RUN_REFRESH_DISABLED` to SQLite and stdout/
journal. With the single writer lock held, this monitor does not ingest new venue
data. For an intended collection run, configure `refresh=true`; refresh still
collects only currently approved pairs, and cannot fix missing approvals or the
unknown Kalshi REST book timestamp. Check the first completed cycle with `ops
health` and `research summary` before committing to weeks of unattended runtime.
An operational endurance run with no qualified data is useful, but does not meet
M4/M5's economic observation acceptance criteria.

Every invocation is bounded to 31 days. For example, a 60-second session with
30241 cycles schedules approximately 21 days, subject to request latency,
interruption and health stops. No such run was launched here. A stored session
can resume after restart; absent cycles and interrupted attempts are never
backfilled as observations. Renewal of human contract reviews and fee evidence
remains explicit; the monitor cannot approve or renew them.

All ordinary CLI writers and the monitor share an advisory lock alongside the
database. A second process fails clearly. The kernel releases the lock on exit;
the leftover lock file is not proof that a process is still running. Direct
Python/SQLite writers must obey the same lock convention. The online backup
tool is a read-only source client and can safely run while the scanner writes.
Research summaries/CSV, paper reports and operational diagnostics also use
read-only connections without migrations or a writer lock.

SIGTERM/SIGINT interrupts the monitor cleanly, rolls back unfinished derived
writes and records a stop event. Existing collectors preserve earlier raw captures
and mark interrupted runs. Already committed cycle evidence remains. A real
SIGTERM during idle wait after a completed cycle was demonstrated; forced kills,
power failure and loaded in-flight deployment still require field validation.

Defaults: at least **200 MiB** free; maximum **10 GiB** for database plus WAL/SHM;
50 pending paper intents processed per cycle. A health stop exits **2**, ordinary
success/signal stop exits **0**, other failures exit **1**. High paper downside
events are labeled separately from HIGH operational health events.

## Backup and restore drill

```bash
predarb ops backup --db data/research.sqlite3 --output data/backups/research-NEW.sqlite3
predarb ops verify-backup data/backups/research-NEW.sqlite3
predarb ops restore data/backups/research-NEW.sqlite3 --output data/restored-NEW.sqlite3
```

Destinations must be new paths. These commands never overwrite a live archive or
migrate the source. Backup uses SQLite's online backup API rather than copying a
live main file without its WAL. It requires free space of twice the estimated
snapshot size plus 200 MiB, uses an exclusive partial file and a bounded 60-second copy phase,
then performs full integrity/foreign-key checks. Full fingerprint/hash verification
can take longer for large archives.

The manifest contains file SHA-256, schema version and a logical digest/count of
all user tables, exact BLOB bytes, indexes and triggers. Backup file/manifest
permissions are 0600. Publication refuses overwrite and fsyncs data/manifest and
directory. A failed publication can leave an orphan snapshot without a valid
manifest; do not treat it as a verified backup. Stale partial files require
operator inspection and must not be mistaken for complete copies.

Restore verifies the backup and creates a separate database/manifest, checking
the same logical digest and counts. This milestone performed a real preserved-copy
drill and matched all contents. The manifest detects accidental corruption; it
does not authenticate a privileged owner's changes or establish source accuracy.
Once a restored database is opened for new writes, its snapshot manifest is no
longer a checksum of its changing live state.

For recovery: stop the writer service, verify the selected backup, restore into
a new path, inspect counts/reviews/expiry and reports, then change the configured
database path and restart the bounded read-only service. Preserve the damaged
archive for investigation. A local restore drill is not proof of recovery from
total host loss; retain an independently verified off-host copy under applicable
provider data rights.

The [daily helper](../scripts/daily_backup.py) generates unique UTC filenames:

```bash
.venv/bin/python scripts/daily_backup.py --db data/research.sqlite3 --directory data/backups
```

It deletes nothing. Plan storage for daily backups; retain at least 14 verified
daily copies and a separately verified recovery copy before manually archiving
older snapshots. Source/audit deletion is not automated. Check size/free-space
alerts and backup age daily. The age monitor reads each manifest with a 2 MB cap,
validates its format/schema/hash/count fields and requires the corresponding
nonempty snapshot file. Orphan/empty snapshots emit `BACKUP_SNAPSHOT_MISSING`;
malformed/unreadable manifests emit `BACKUP_MANIFEST_UNREADABLE`. Neither can hide
an older stale backup. Future timestamps are warned and cannot satisfy backup
freshness. With no eligible snapshot, `BACKUP_NOT_OBSERVED` is also emitted.
Backups older than **26 hours** warn, allowing daily timer jitter and verification
time. This check does not read/hash snapshot contents; full `verify-backup` and
periodic restore drills remain necessary. Large source/WAL,
space reclamation, rotation and verification duration need deployment measurement.

## systemd preparation

Templates are [research service](../deploy/predarb-research@.service),
[backup service](../deploy/predarb-backup.service) and
[backup timer](../deploy/predarb-backup.timer). They use a dedicated unprivileged
`predarb` account, code/venv under `/opt/predarb`, configuration under
`/etc/predarb` and private writable state under `/var/lib/predarb`. They do not run
code from the operator's home directory.

Prepare those paths/account and install this package in the dedicated venv before
using the templates. Keep code/configuration read-only to the service and grant
write access only to its state directories. Import/review source evidence and
create a zero-budget session explicitly under the service identity. Set the
matching integer session ID and absolute paths in `/etc/predarb/session-1.json`.
Review current venue access/data-use terms before any ongoing public refresh.

Validate on the target host:

```bash
systemd-analyze verify deploy/predarb-research@1.service deploy/predarb-backup.service deploy/predarb-backup.timer
```

After installation/configuration by the operator, the normal service controls are:

```bash
sudo systemctl daemon-reload
sudo systemctl start predarb-research@1.service
sudo systemctl start predarb-backup.service
journalctl -u predarb-research@1.service -u predarb-backup.service
```

Enable the timer/boot service only when that configured ongoing run is intended.
The checked-in one-cycle default exits successfully and does not restart forever.
Unexpected failures use a 30-second backoff with a three-start/300-second limit;
health exit 2 prevents automatic restart until the underlying condition is fixed.
Shutdown timeout is 90 seconds. Read-only filesystem, home/device restrictions,
empty capabilities, private temporary storage, 512 MiB memory limit and bounded
tasks are configured. Runtime behavior under these restrictions is **not** proven
by the syntax check and still needs an actual deployment trial.

The daily timer targets 04:00 UTC with up to five minutes jitter; it is persistent
across missed schedules. Backups may run alongside the single writer using SQLite's
snapshot API. Review journal alerts, restore verification, disk growth, clock
state, rejection patterns, paper queue coverage and renewal needs daily.

Official operational sources and actual validation commands are recorded in
[the source/unit manifest](evidence/M5_SOURCE_AND_UNIT_CHECKS.json). M5 remains
open until a multiweek zero-money run and evidence/incident audit actually pass.

M5A follow-up: [bounded Kalshi WebSocket capture](KALSHI_WEBSOCKET.md) uses the
same writer lock and can optionally scan an existing research session in that
writer. Do not run it alongside the monitor on the same database. Its live
continuity is unvalidated, and no WebSocket service was installed or activated.
