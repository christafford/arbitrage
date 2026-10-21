# M3 acceptance results — 2026-10-21 UTC

M3 is complete for read-only normalization, archival inspection and deterministic
sequence-recovery checks. Both public US collectors now persist normalized book
assessments. **101 tests passed**, including unchanged real provider snapshots
and explicitly hypothetical failure/recovery scenarios. No live trading, real
pair approval, M4 fee model or profit scanner was implemented.

## Acceptance evidence

| Requirement | Implemented and checked |
| --- | --- |
| Documented YES/NO depth | Kalshi complementary bids; US offers and explicitly synthetic NO from short-YES bids; quantities preserved and asks sorted |
| Timestamps and increments | Separate receipt/metadata/source times, current-age and close rechecks, documented tick/count checks, conservative supported US quantity grids |
| Sequence/reconnect | Offline Kalshi snapshot/delta replay; subscription sequence gaps, duplicates, generation changes, clock/send-time regression, deletion and invalid liquidity discard depth and require snapshot recovery |
| Reject bad/incomparable data | Missing/partial/empty/crossed/locked/off-grid books; unknown source time; stale/future data; superseded books/metadata; raw provenance; registry/identity/source-and-receipt skew gates |
| Exact depth exhaustion | Three hypothetical US YES contracts cover at $1.45; a request for five covers four at $1.94 and reports `DEPTH_EXHAUSTED` |

`data_usable` describes quote quality at a particular evaluation time, not fills
or an actionable opportunity. Every live record remains `UNVERIFIED`. US NO is
explicitly a synthetic quote representation, not a separate NO-token order path.
See the [inspection guide](BOOKS.md) for supported cases and failure behavior.

## Commands actually executed

Environment: local Linux, Python **3.13.5**, project virtual environment, SQLite,
stdlib tests. Before M3 edits, all **63** existing tests passed. After M3 changes:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m3_demo.py --output data/m3-postreview-demo
.venv/bin/predarb collect-kalshi --db data/m3-live-smoke.sqlite3 --limit 1 --max-pages 4 --event-ticker KXLNBELITE2GAME-26OCT231430CHASTC --books 2
.venv/bin/predarb collect-polymarket-us --db data/m3-live-smoke.sqlite3 --limit 1 --max-pages 3 --slug tec-mlb-champ-2026-09-27-mil
.venv/bin/predarb books list --db data/m3-live-smoke.sqlite3
.venv/bin/predarb demo --db data/m3-live-smoke.sqlite3
.venv/bin/predarb report --db data/m3-live-smoke.sqlite3
```

All commands above exited 0. The [full test log](evidence/M3_TESTS.txt) records
**101 tests / OK**, covering previous milestones plus normalization, archived
inspection/migration/CLI, exact depth and streaming recovery. The original
hypothetical demo still reported 400 paired contracts, $391 capital and $9
illustrative profit, independently of collected books. No hosted CI or other
Python version was executed.

`python -m compileall -q src scripts tests`, `git diff --check`, local Markdown
link checks and M3 evidence/fixture JSON parsing also passed.

The [offline M3 demo](evidence/M3_DEMO.json) recorded stream states
`SYNCED, SYNCED, REJECTED, REJECTED, SYNCED, REJECTED, SYNCED`: initial snapshot,
delta, sequence gap, refused delta, recovery snapshot, reconnect delta before
snapshot, new-generation snapshot. It also checked staleness and depth exhaustion.
The frames and raw fixture copy are in the ignored local demo output directory;
the source fixture and script reproduce the run offline.

## Live public snapshots

Both bounded runs reached terminal pagination at **21:23:26–21:23:29 UTC**.

| Venue | Pages / unique markets / books / raw responses | Assessment at capture |
| --- | --- | --- |
| Kalshi | 2 / 2 / 2 / 8 | Both normalized; rejected with `UNKNOWN_SOURCE_TIME` |
| Polymarket US | 2 / 1 / 1 / 4 | Normalized; quote-quality checks passed at capture |

The scopes identify unrelated markets used to verify each adapter; they are not
a proposed matched pair. [Run evidence](evidence/M3_LIVE_RUNS.json) records exact
IDs, schema contracts, clocks and assessments. The sanitized
[snapshot fixture](../tests/fixtures/m3-live-snapshots.json) retains unchanged raw
response bodies/hashes and exact expected results; an offline test checks all
three snapshots. Provider rights remain reserved; these local captures confer
no redistribution permission.

Additional [CLI inspections](evidence/M3_INSPECTION.json) actually executed:

- US observation 12 at `2026-10-21T21:23:29.028171+00:00`, one hypothetical YES
  contract: exit 0, `historical_replay=true`, quote quality passed.
- Kalshi observation 6 at its capture assessment time: exit 2,
  `UNKNOWN_SOURCE_TIME`.
- US observation 12 at the later current time: exit 2,
  `STALE_RECEIPT`, `STALE_METADATA`, `STALE_SOURCE`.

Persisted capture-time flags therefore cannot silently become current quotes.
No live cross-venue comparison passed. Positive comparison-gate behavior is tested
with isolated, explicitly hypothetical inputs; it is not live equivalence evidence.

## Migration, documentation and limits

A SQLite backup of the M2 live archive was opened as
`data/m3-migrated-m2.sqlite3`; the original was preserved. The schema-3 migration
retained **12 raw observations, 3 catalogue entries, 3 registry instruments and
4 registry supplements**, with zero pairs and zero fabricated normalization
assessments. See [migration evidence](evidence/M3_MIGRATION.json). Tests also
exercise legacy and schema-2 migrations, rejection of future schemas, provenance
tampering and current-context invalidation.

Current official API docs were checked for both US venues before using M3 fields;
[source notes](API_SOURCES.md) explain side/time/increment semantics, and the
[document manifest](evidence/M3_API_CHECKS.json) records URLs, hashes and local
save times. Upstream versions remained Kalshi 3.34.0 and US MarketService 1.0.0;
normalization is versioned `binary-books/m3-v1`.

No M3 acceptance test remains failing. Operational limits are explicit:

- Kalshi REST has no source book time and cannot supply a freshness-qualified
  comparison. A timestamped authenticated feed would need separate transport and
  live validation work. The M3 recovery helper was tested offline only.
- Neither authenticated WebSocket was connected. US snapshots have no documented
  sequence/delta contract assumed by this implementation.
- Supported binary/tick/quantity cases are deliberately narrow; unknown grids,
  partial books or uncertain semantics are rejected. A passed quality check does
  not model margin, fees, leg risk or liquidity after capture.
- No continuous scanner, 30-day measurement, retention scheduler, paper execution
  or live order path was added. Those belong to later milestones.
- Changes remain local and uncommitted: repository author identity was unavailable
  in the earlier milestone, and no identity was invented or configured. Nothing
  was pushed or published.

The [roadmap](ROADMAP.md) is updated. Work stops before M4 pending a separate request.
