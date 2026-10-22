# M5 implementation results — 2026-10-22 UTC

**M5 remains IN PROGRESS.** Paper stress/comparison and operational tooling are
implemented and tested. The required actual multiweek zero-money run has not
happened. M4's separate 30-day acceptance is still open. The user explicitly
authorized M5 implementation after that gap was reported; neither milestone was
marked complete to bypass the missing observations.

No credentials, real orders/cancellations, funds, real positions, service
installation, externally delivered alerts or M6 work were added.

## Implemented scope

- Exact hypothetical adverse-selection, partial/unequal-fill, one-leg outage,
  hedge-deadline, cancel-race and effective-cancel scenarios using later quote
  samples, supported lots, current fees, reserves and reviewed payout cases.
- Immutable paper intent provenance from gated M4 evaluations, later-tick input
  hashes, causal timestamp checks, approval/fee rechecks and unobservable results
  that explicitly retain uncertainty. Scenarios are independent, not a position
  ledger or realized profit series.
- A bounded monitor with single-writer locks, local metrics/alerts, clock/disk/WAL
  monitoring, graceful signals and optional paper generation/comparison. There is
  no network-exposed admin/metrics endpoint or outbound alert sender.
- Verified online SQLite backup, manifest verification and restore to a new path;
  schema-5 migration preserving old evidence; hardened systemd templates and a
  daily backup helper. No automatic source/backup deletion or host configuration.

Usage: [paper model](PAPER_EXECUTION.md), [operations/deployment](OPERATIONS.md).

## Tests actually executed

Local Linux, Python **3.13.5**, SQLite and stdlib unittest. Before M5 edits,
**124 baseline tests passed**. The final command:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

passed **154 tests**. The [full log](evidence/M5_TESTS.txt) records previous
milestones plus paper fees/downside/latency, partial and stale/off-grid/future
inputs, malformed schemas, changed/expired approvals, provenance tampering,
idempotent replay, retained evidence, health/clock/space faults, runner stops,
process lock contention, migrations, online WAL backup, corruption detection,
new-path restore and CLI failures. No hosted CI or other Python version was run.

## Hypothetical paper demonstration

```bash
.venv/bin/python scripts/m5_demo.py --output data/m5-final-demo
```

This exited 0 and archived seven generated input sets before normalization.
[Demo evidence](evidence/M5_DEMO.json) records all results, assumptions and hashes
through the local SQLite source references. It uses synthetic inverse contracts,
simulated human approvals and a **2030 replay clock**, never real equivalence or
historical fill evidence.

| Hypothetical case | Unhedged contracts | Worst conditional net | Flags |
| --- | ---: | ---: | --- |
| Matched full fills | 0 | $16.54 | Assumed displayed-depth participation |
| US-side outage | 200 | -$85.00 | HIGH one-leg exposure |
| US fills 40 versus Kalshi 200 | 160 | -$64.69 | HIGH partial/unhedged exposure |
| US ask moves beyond cap | 200 | -$85.00 | HIGH adverse-selection exposure |
| US sample misses cancel window | 200 | -$85.00 | HIGH one-leg exposure |
| Late fill during cancel-ack window | 0 | $16.54 | HIGH modeled hedge latency; cancel race |
| Both samples after assumed acknowledgment | 0 | $0.00 | Assumed effective cancel and no earlier fills |

The last case does not prove zero exposure: unseen prior fills remain possible.
No actual fill probability, acknowledgment or execution latency was measured.
The five HIGH paper-risk findings are deliberate stress outcomes, distinct from
real operational incidents. Repeated scenarios must not be summed as positions.

## Actual host and compatibility checks

[Command evidence](evidence/M5_COMMANDS.json) records actual `research start`,
`ops run`, backup/verify/restore, health, text metrics, events, paper report and
original demo/report invocations. All recorded commands exited 0.

- A zero-budget live-mode smoke completed **three short cycles**, with **zero
  real paper intents**, zero HIGH operational events and no approved pair.
  Monitoring readiness did not authorize economics or invent fills.
- A separate monitor process received **actual SIGTERM after its first cycle**
  while idle. It exited 0 and recorded exactly one `RUN_SIGNAL_STOP`. In-flight
  network shutdown was covered by hypothetical collector interruption tests,
  not a loaded production signal trial.
- Host `timedatectl` reported synchronization. This is a state probe, not a
  measured clock offset or a long-term drift guarantee.
- The actual online backup/restore drill passed file hash, SQLite integrity,
  foreign-key, all-table/BLOB/count/schema/trigger/index logical fingerprint
  checks. The original database was preserved; restored output used a new path.
  Its exact digest and manifest are in the command evidence/local artifacts.

The [two live collector compatibility runs](evidence/M5_LIVE_RUNS.json) reached
terminal pagination at **02:00:27–02:00:31 UTC** on October 22. Kalshi: 2 pages,
2 unique markets, 2 books, 8 raw responses; US: 2 pages, 1 unique market, 1 book,
4 raw responses. Kalshi correctly retained `UNKNOWN_SOURCE_TIME`; US quality
passed at capture. These unrelated scopes test collectors, not a contract match.
No real pair was approved and no fee profile was installed.

A preserved-copy [M4 migration](evidence/M5_MIGRATION.json) retained 12 raw
observations, 3 catalogue entries, 3 registry instruments and 3 normalization
assessments. New paper/ops tables were empty; no historical paper evidence was
fabricated. The original M4 archive was preserved.

The [source/unit manifest](evidence/M5_SOURCE_AND_UNIT_CHECKS.json) records current
primary SQLite/systemd references, systemd **257.13** on this host and this actual
successful command:

```bash
systemd-analyze verify deploy/predarb-research@1.service deploy/predarb-backup.service deploy/predarb-backup.timer
```

No units, users, clock settings or system configuration were installed/changed.
Compilation, whitespace checks and local documentation links also passed.

## Remaining acceptance gaps and limits

1. **Multiweek actual zero-money run and evidence/incident audit:** not run. Short
   tests and smoke checks cannot establish sustained uptime, coverage, backup
   rotation or absence of high-severity incidents over weeks.
2. **M4 prerequisites remain:** no real approved pair, live fee applicability or
   timestamped Kalshi book source. No authenticated feed was implemented. The
   scanner correctly rejects uncertain data, so live shadow execution evidence
   is unavailable rather than fabricated.
3. **Forward comparison is implemented, not field-validated:** the seven cases
   compare later synthetic ticks. No actual live intent/fill sequence, fill
   probability, exchange acknowledgment or true execution latency was observed.
   Polling may be much slower than the modeled hedge window.
4. **Deployment remains prepared:** systemd syntax verification does not prove
   runtime behavior under its sandbox, memory/task caps, dedicated account or
   restart policy. Actual enabled service, host reboot, power-loss and off-host
   recovery drills remain pending.
5. **Monitoring/retention limits:** clock offset is not independently measured;
   local JSON/journal alerts need an operator consumer; raw/summary/backup growth
   remains bounded by monitoring/stops and an explicit storage policy, not
   automatic deletion. Full backup fingerprinting duration needs measurement on
   larger archives. Paper comparison retries stop after 180 seconds and report
   queue saturation rather than claiming complete coverage.

The [roadmap](ROADMAP.md) keeps both M4 and M5 open. Stop before M6. Changes are
recorded locally using the existing Git identity; nothing was pushed or published.
