# Research readiness (M5A E)

`research readiness` explains which prerequisites currently pass and what blocks
useful zero-money live research. It opens an existing archive read-only, takes a
consistent SQLite snapshot, and rechecks evidence at the current UTC clock. It
does not collect data, approve pairs or fees, migrate a database, write audit
records, install services, or access credentials.

```bash
predarb research readiness --db data/research.sqlite3
predarb research readiness --db data/research.sqlite3 --session-id SESSION_ID \
  --horizon-days 21 --backup-dir data/backups --format json
```

Replace the database path and `SESSION_ID` with the intended live archive and its
integer session ID. Omitting the session still reports pair blockers, but cannot
pass the session or operational prerequisites. Text is the default; JSON uses
schema `research-readiness/m5a-e-v1`. The horizon defaults to 21 days, with a
supported range of 1–31 days. There is no historical-clock CLI override.

Exit **0** means `PREREQUISITES_PASS_NOW`; **2** means `BLOCKED`; **1** means an
input/database/probe failure prevented the command from completing. Invalid
argparse syntax exits 2. An absent database is never created. Schema versions
below 7 produce a migration blocker without being changed; unsupported newer
versions fail. Readers remain available while the application's writer lock is held.

## What the checks mean

| Check | Requirement |
| --- | --- |
| Archive | Schema 7; at most 50 total pair rows, matching the scanner limit; no hypothetical pairs or replay sessions. |
| Pair approval | At least one real pair whose current rule provenance, metadata, expiry and human decision pass the existing registry checks. Cached `APPROVED` alone is insufficient. |
| Mechanics | D's explicit account/instrument review, source roles, cash timing and supported cash-funded position routes. Polymarket US synthetic NO remains blocked. |
| Fees | Current C capture-bound, operator-reviewed applicability on both selected instrument sides, with hashes, source/effective windows and failed-refresh supersession rechecked. |
| Books | Newest captured book per venue/instrument, valid raw provenance and schema, fresh metadata/source/receipt clocks, valid continuity and route; authenticated Kalshi WebSocket data is required. |
| Comparison | Source timestamps and receipt timestamps each within two seconds, and displayed depth for one common lot on both selected legs. |
| Session | Explicit current `LIVE_READ_ONLY` session, valid economics policy, positive research budgets for both venues within the $10,000 cap, and 1–10,000 common lot search increments for at least one ready pair. These are simulation budgets, not deposits or balances. |
| Host | Existing health checks: database integrity, free disk, database size and confirmed host clock synchronization. |
| Backup | A recent structurally valid manifest and nonempty snapshot, using existing 26-hour tolerance. Full backup content hashing is **not** performed by readiness; use `ops verify-backup BACKUP_PATH`. |
| Protocol horizon | At least one otherwise ready, searchable pair uses a protocol whose configured validity extends beyond the requested end. `sequence-v1` cannot support a run ending at or after 2026-10-29 00:00 UTC. |

Per-pair results expose stored and effective approval states, fee IDs/hashes,
book IDs and timestamps, checks, expiry and next actions. A bad pair remains
visible but does not prevent another fully eligible pair from qualifying.
The whole-archive size and hypothetical-data gates still apply. Oversized
registries show the first 50 rows and explicitly report truncation.

Discovery queue freshness and latest collection status provide context. Discovery
is not mandatory for an already reviewed pair. Book/registry validators enforce
relevant collection failures independently. The latest research cycle is reported
separately: a heartbeat, a large cycle count, or host health does not prove useful
economic observations. A session with no cycles can pass preflight once its other
prerequisites pass; deployment and sustained-run acceptance remain unverified.

## Acting on blockers

1. Select candidate real contracts from the [discovery queue](DISCOVERY.md), archive
   current official rules, and complete the [human pair review](PAIR_REVIEW.md).
2. Complete [fee applicability](FEE_REVIEW.md) and [mechanics/cash-timing reviews](SETTLEMENT_MECHANICS.md).
   The report never supplies human decisions or fills in unknown account terms.
3. Capture contemporaneous US books and [Kalshi stream data](KALSHI_WEBSOCKET.md).
   Refresh metadata as well as depth. Fix invalid provenance or failed refreshes;
   a passing older capture is not a fallback for the newest invalid evidence.
4. Select a session with the intended research policy; create/verify backups and
   resolve clock, disk and database failures using the [operations guide](OPERATIONS.md).
5. Re-run readiness, then inspect the actual deployed collection/scanning cadence
   and the first completed cycle before attempting a sustained run.

The report emits the configured October 29 cutoff even when there are no pairs.
Revalidate default `clocked` mode live before relying on a run across that boundary.
A passing clocked book is assessed from its archived frames, not a separately
maintained global rollout approval. E does not alter the protocol's compatibility
window or prove continued availability.

## Limits

`ready_now` describes the checked current prerequisites before the horizon gate.
`protocol_supports_requested_horizon` describes the configured protocol window,
not quote or approval lifetime. `prerequisites_pass` combines both. None promises
that a future run will stay ready: books require continuous refresh (including
Kalshi's five-second liveness gate), and pair/fee/mechanics evidence requires
human renewal within 24 hours. `valid_until` is the earliest ready-pair evidence
expiry in the snapshot; changes can invalidate evidence sooner.

This command does not calculate profit, prove sufficient cash for a profitable
hedge, validate deployed timers/stream processes, or establish a completed
multiweek/30-day run. These limitations are explicit JSON fields; all live
observations remain `UNVERIFIED` and `trading_authorized` is always false. The
existing scanner/evaluator and run audit remain necessary. No funding, order,
margin or service activation is implied by exit 0.
