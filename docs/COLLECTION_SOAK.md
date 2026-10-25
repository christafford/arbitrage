# Bounded collection-only soak

This M5A operational extension coordinates one Kalshi WebSocket subscription and
one Polymarket US detail/book poller in a single SQLite writer. It can use rejected
or unverified instruments for transport testing. It does not propose or approve
pairs, import fees, create research sessions, calculate profit, or place orders.

Each invocation creates a **new directory and isolated database**. Existing
directories are refused. The original research database and rejection audit remain
separate. No registry approval is needed for public market-data collection.

## Run and inspect

Use a five-minute smoke first. Existing protected Kalshi read-only credentials
are loaded from the same external file as `stream-kalshi`; never pass key values
on the command line. The optional WebSocket dependencies must be installed.

```bash
predarb soak run --output data/soak-smoke-NEW \
  --kalshi-ticker KXFEDCUT-31DEC28-31DEC26 \
  --us-slug cbpac-usfed-2026-cut \
  --seconds 300 --protocol sequence-v1
```

These example instruments were rejected for arbitrage; their use here asserts no
equivalence. `sequence-v1` is explicit and only valid before the existing
**2026-10-29 00:00 UTC** cutoff. The entire requested duration plus a 60-second
shutdown allowance must fit before it. `clocked` remains the default and needs
live validation against the rolled-out feed. No automatic fallback or extension
is implemented.

For the authorized 24-hour collection test, choose a new output directory and set
`--seconds 86400`. Run in a persistent terminal or background process; this command
does not install a service or reboot timer. For example:

```bash
nohup .venv/bin/predarb soak run --output data/soak-24h-NEW \
  --kalshi-ticker KXFEDCUT-31DEC28-31DEC26 \
  --us-slug cbpac-usfed-2026-cut \
  --seconds 86400 --protocol sequence-v1 \
  > data/soak-24h-NEW.log 2>&1 < /dev/null &

predarb soak report data/soak-24h-NEW
```

`status.json` and the report show the process ID. To stop, verify that PID still
belongs to this exact run, then send `SIGTERM`; Ctrl-C also requests graceful
shutdown. Signals set a flag rather than interrupting a database transaction.
The stream closes, evidence stays archived, and a final backup is attempted if
resources permit. Reboot/SIGKILL cannot finalize a run: after 120 seconds without
a heartbeat the report says `INTERRUPTED_OR_UNRESPONSIVE`. Start a **new** run after
inspection; never reuse the prior stream generation or silently reset its history.

## Scheduling and limits

- Default US poll spacing is 10 seconds **after the preceding poll completes**,
  with a fresh exact market detail followed by its book. These are selected
  captures, not a full catalogue traversal. No missed-poll catch-up burst occurs.
- Public requests are serialized, paced at at most one per second per venue,
  with three-second socket timeouts and one transport attempt. The coordinator
  retries US failures with bounded exponential backoff and respects `Retry-After`.
  Kalshi HTTP cooldown persists across reconnects too. Requests use fixed official
  US origins with redirects disabled; there is no international fallback.
- The existing Kalshi five-second message timeout, 30-second resnapshot boundary,
  source-time, sequence, identity and schema gates remain. US polling also runs
  while the stream is quiet and during reconnect backoff.
- One thread owns all database writes. US HTTP work can delay draining the socket;
  source timestamps are never replaced by receipt time. Delayed/stale frames fail
  existing gates and force recovery. This is not a claim of gapless simultaneous
  collection. `max_poll_duration_ms` exposes stalls.
- Default segments last at most 60 seconds, followed by a checkpoint. Periodic
  reconnects and segment boundaries lose continuity and require a fresh snapshot.
  Startup, six-hourly and final verified backups use the existing online backup
  format. Scheduled backups pause collection with the socket closed; their start
  and finish are archived explicitly. A failed backup stops the run.
- Clock synchronization must be confirmed at startup. A greater-than-one-second
  wall/monotonic discrepancy stops collection. This probe does not measure actual
  clock offset or guarantee future synchronization.
- Default free-space floor is 1 GiB; total run-directory budget is 4 GiB, including
  backups, DB/WAL and local reports. Resource guards check about once per second,
  reserve 32 MiB for in-flight writes, and reserve additional snapshot space before
  backup. These cooperative guards are not filesystem quotas; an in-flight write
  or transport call can exceed a sampling boundary. A resource stop is reported,
  not disguised as 24-hour completion.
- No evidence is automatically deleted. Duration (at most 24 hours) and total
  storage bound retention. Preserve failed runs; copy verified backups elsewhere
  under the existing backup procedure if long-term retention is needed. Same-host
  backups do not protect against loss of the host/storage device.

The duration limits the collection loop; an in-flight request/handshake, close or
final backup can add shutdown time. Backup verification is real work, so long
pauses are reflected in heartbeat/sample gaps. The run does not auto-restart after
process failure or stop merely because an instrument has little activity.

## What the evidence means

`status.json` is atomically replaced at heartbeats and phase boundaries. The same
reports plus segment/backup records are appended to `ops_events`. Raw responses,
validation failures, exact metadata/book references, and connection boundaries
remain in the schema-7 archive. No schema migration is introduced.

Inspect these fields:

| Field | Meaning |
| --- | --- |
| `status`, `stop_reason` | Duration completed, signal stopped, resource/protocol failure, or stale writer heartbeat |
| `counts.us_poll_*` | Attempted, completed and failed US polls; a completed response can still contain stale/partial data |
| `counts.kalshi_*`, `failures` | Messages, snapshots/deltas, usable books, connections, recoveries and failure codes; stream totals update at segment end |
| `counts.*fresh_samples`, `timestamps_within_2s_samples` | Periodic current-time freshness/skew samples, never contract equivalence or profitability |
| `sample_rejections`, `latest_sample` | Missing, stale, partial, disconnected or failed-refresh reasons, including the stopped stream at finalization |
| `max_sample_gap_ms`, `max_poll_duration_ms` | Observed scheduling gaps and HTTP work duration |
| `storage_bytes`, `backups` | Observed footprint and completed snapshot hashes |

Sampling is approximately every 10 seconds, after any due US poll. Sample counts
are **not time-weighted uptime percentages** and may be biased toward fresh US
receipts; gaps are not filled with invented observations. An inactive book's old
source time stays stale even if the API request succeeds. Short schema/transport
failures are preserved even after recovery.

Exit 0 means the requested duration completed and each venue produced at least
one usable book. It does not mean uninterrupted coverage. Exit 2 means a running,
stopped, failed/unresponsive, or completed-but-insufficient-data report. Exit 1
means configuration/setup failure. Inspect counters and reasons in every case.
`OBSERVATIONS_RECORDED` is a minimal observation indicator, not a soak acceptance
threshold. Every result remains `UNVERIFIED`, with no trading authorization.

After 24 hours, review freshness/skew samples, worst gaps, rejected responses,
reconnect recovery, storage growth and backup restore/replay. A useful collection
test does not complete M4's 30-day economics or M5's multiweek acceptance. Those
still require genuinely equivalent human-approved contracts, reviewed fees and
mechanics, and a protocol supporting the full horizon.
