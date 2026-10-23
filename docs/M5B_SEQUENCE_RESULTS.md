# M5A Workstream B — bounded live acceptance

**B acceptance passed on 2026-10-23 for explicit pre-rollout `sequence-v1`.**
Authenticated snapshots, incremental deltas, real reconnect/recovery, archival
provenance and deterministic replay were demonstrated. This does not complete
M5A's C–E work or M4/M5's sustained-run acceptance. No orders, account actions,
pair/fee approvals, credential changes or service activation occurred.

## Why the clock discrepancy was resolvable

The [official changelog](https://docs.kalshi.com/changelog) dates market-clock
introduction to **October 29, 2026**, after these October 23 captures. It dates
exchange send timestamps to October 1. Earlier work checked the reference schema
but missed this future rollout date and incorrectly treated the newer shape as
already deployed. The [rollout source manifest](evidence/M5B_ROLLOUT_SOURCES.json)
preserves downloaded sources, exact hashes and UTC retrieval times. The earlier
[discrepancy report](KALSHI_PROTOCOL_DISCREPANCY.md) and rejected archives remain
historical evidence rather than being silently rewritten as successes.

The explicit `--protocol sequence-v1` option uses a separate local schema,
`kalshi-ws/m5a-sequence-v1`. It requires one market per subscription, a full initial
snapshot, contiguous subscription `seq`, stable market/subscription identity,
exchange `sending_ts_ms`, fresh metadata/books, exact prices and quantities, and
new snapshot state after every reconnect. It never synthesizes `msg.clock` or
combines generations. A clock field appearing in this version causes a stop for
review. Default `clocked` mode still requires the clock and retains its existing
schema `kalshi-ws/m5a-v1`; unknown or mixed versions are rejected. Database schema
remains 7, and earlier rejected observations cannot become valid via replay.

Compatibility is bounded to **2026-10-01 inclusive through 2026-10-29 exclusive,
UTC**, checking source, receipt and evaluation times. The UTC cutoff is a local
conservative review boundary, not a claim about the venue's deployment hour.
After it, this mode fails with `PROTOCOL_REVIEW_REQUIRED`. Historical replay with
an original `--at` clock remains possible. Recheck rollout status and demonstrate
the clocked protocol live before continuing beyond the boundary. No automatic
fallback or extension is provided, so this is not an uninterrupted multiweek mode.

## Actual captures

[Validation evidence](evidence/M5B_SEQUENCE_VALIDATION.json) records complete
commands, outputs, exit codes, counts, per-connection boundaries and smoke results.
Both runs used the fixed production endpoint and existing protected RSA credentials.

| Run | Snapshots | Deltas | Usable book observations | Exit |
| --- | ---: | ---: | ---: | ---: |
| 65-second receive budget, up to 3 connections | 3 | 219 | 222 | 2 |
| 20-second / 10-message budget, 1 connection | 1 | 8 | 9 | 0 |

The first run used three real socket generations. Generation 1 refreshed after
30 seconds, generation 2 reached the existing five-second message timeout, and
generation 3 reconnected, received a fresh snapshot and accepted another 34 deltas.
The timeout remains recorded as a failure, so the overall result correctly stays
`INCOMPLETE`/exit 2 despite successful recovery. All three generations had usable
deltas. `reconnected_continuity_demonstrated=true` establishes that new generations
rebuilt valid books; it makes no claim of gapless observation while disconnected.
The separate short run demonstrates a clean `CAPTURED`/exit 0 result.

The longer archive contains 228 raw observations, 225 WebSocket frames and 222
normalized books, with zero pairs, fee profiles or paper intents. All raw hashes,
SQLite integrity and foreign keys checked successfully. Source time remains the
exchange send time, not local receipt or mutation time. At command exit the
connections are closed and their books are no longer current.

An initial sequence-mode development smoke failed because the book normalizer's
continuity allowlist did not yet recognize the new explicit label. That integration
gap was fixed before the successful runs; its rejected archive remains at
`data/m5b-sequence-live-20261023T124434Z/`. The accepted run is
`data/m5b-sequence-live-20261023T124703Z/`, and the clean run is
`data/m5b-sequence-clean-20261023T125005Z/`.

## Tests and smoke checks executed

```bash
.venv/bin/python -m unittest discover -s tests -v
```

**231 tests passed**; [full output](evidence/M5B_SEQUENCE_TESTS.txt) names every test.
New coverage includes version selection, valid actual frames, missing/stale source
time, wrong identity, invalid prices/quantities, partial depth, sequence gaps,
fresh-generation recovery, no cross-generation merging, unexpected clocks,
unknown/mixed schemas, cutoff rejection before network access and during capture,
and current-time cutoff enforcement on archive reads. Existing clocked-protocol,
credential privacy, backup/migration, research and economics tests also passed.

The [real fixture](../tests/fixtures/kalshi-ws-sequence-live.json) preserves all
225 exact public-shaped frames and their public metadata. Tests replay it into
two isolated SQLite archives, compare all 222 normalized states exactly, recheck
each generation through the M3 inspection path, and reject disconnected books.
Credential headers, signatures and account identifiers are excluded. Generated
fault variations remain explicitly hypothetical.

Eight additional CLI smoke checks passed their expected outcomes: help, historical
book inspection, current book rejection (exit 2), book listing, backup, full backup
verification, new-path restore and report. Restored logical fingerprints matched.
Compilation, local documentation links and Git whitespace checks also passed.

## Using the validated mode

With a current open ticker, before the cutoff:

```bash
predarb stream-kalshi KALSHI_TICKER --db data/research.sqlite3 \
  --protocol sequence-v1 --seconds 60 --max-messages 10000 --max-connections 10
```

Use a new database or back up an existing archive first. All observations remain
`UNVERIFIED` for settlement equivalence and grant no trading authority. Read
[setup, failure codes and limits](KALSHI_WEBSOCKET.md). The single writer can run
an existing research-session callback, but coordinated continuous US polling is
still missing; existing US books otherwise expire. Real pair review, live fee
applicability, C–E and multiweek evidence remain pending. Stop after B for this task.
