# Architecture

```text
Kalshi REST/WS          Polymarket US REST/gRPC
      |                           |
raw response capture -> normalized instrument / quotes
                       |
              reviewed pair registry
                       |
          depth-aware hedge evaluator
                       |
        opportunities / rejection reasons
                       |
              SQLite + reports
                       |
         future paper execution replay

           NO LIVE ORDER PATH IN MVP
```

## Components

- `src/predarb/provider.py`: bounded, paced public HTTPS GET transport; exact US origin allowlist, redirects disabled, timeouts, retry/backoff and raw archival before decoding or validation. No credentials or write methods.
- `src/predarb/validation.py`: strict consumed-field schemas, duplicate JSON key/nonfinite number rejection, Decimal parsing, source IDs and UTC timestamps. Additive unconsumed fields remain archived, not interpreted.
- `src/predarb/kalshi.py`: versioned public catalogue, market/event/series detail and raw fixed-point bid book contracts. No complement conversion into asks in M1.
- `src/predarb/polymarket_us.py`: versioned US public gateway catalogue, instrument-side metadata and raw book contracts. The institutional refdata interface requires access and is not the public collection path.
- `src/predarb/collector.py`: bounded traversal, source ID deduplication, loop detection, selected detail/book capture, separate source/receipt times, freshness/liquidity classifications and run accounting. All evidence is `UNVERIFIED`.
- `src/predarb/models.py`, `math.py`: the existing independent Decimal evaluator for explicitly hypothetical inputs. Collected books do not feed this evaluator.
- `src/predarb/store.py`: SQLite WAL, atomic migration from starter schema to version 1, committed raw responses, collection runs and metadata/rule/book evidence. Connection contexts close explicitly.
- `src/predarb/cli.py`: hypothetical demo, archival reports and one-shot collectors. Exit 2 identifies incomplete bounded traversals.

[Current verified schemas](API_SOURCES.md), [M1 acceptance evidence](M1_RESULTS.md).

## Assumptions / unknowns

- A binary YES/NO pair pays $1 collectively **only** if their legal settlement outcomes are complementary and each venue pays as expected. Settlement terms, void/cancellation, timing, rounding, outage risk must be reviewed.
- NO is not automatically available as a long-buy instrument on every venue in identical form. Map the documented venue mechanics explicitly. A quote might be bid, ask, or implied from complements; document direction.
- Two API responses are **not synchronous**. Timestamps need source and receipt time; stale or crossed books must be rejected.
- Execution and post-trade settlement involve fees and capital tied up. Fees can depend on price/contract type, trade direction, and current schedule.
- No guaranteed simultaneous fills across venues; actual realized P&L can differ substantially from quoted theory.

## Data storage after M1

SQLite `PRAGMA user_version=1`:

- `raw_observations`: original response bytes and SHA-256, JSON/text inspection copy, venue/endpoint, UTC receipt time, separate source time where available, HTTP status, allowlisted headers, validation status/error and local/upstream schema version. Oversized responses are marked truncated and rejected. Starter rows remain `LEGACY_UNVALIDATED`.
- `collection_runs`: scope, schema version, start/finish times, `RUNNING`/`COMPLETE`/`PARTIAL`/`FAILED`/`INTERRUPTED`, accepted catalogue page count, returned/unique/duplicate record counts, next cursor/offset and failure text.
- `catalogue_entries`: per-run source IDs, raw observation reference, provider metadata timestamp, exact metadata/rule evidence JSON and evidence SHA-256; `verification='UNVERIFIED'`. A repeated ID updates this run's derived entry; every raw response remains separately archived.
- `book_captures`: raw observation reference, run/source IDs, source timestamp, freshness and liquidity at capture, `verification='UNVERIFIED'`. No normalized ask levels or executable sizes are stored yet.
- `opportunities`: existing illustrative simulation only, with `hypothetical=1`; monetary reporting now sums Decimal values directly.

Raw response commits precede validation; catalogue pages and run progress are
committed incrementally. A failed run can retain earlier evidence but never
becomes complete. `records = unique_records + duplicates` for accepted pages.
Raw HTTP response counts also include details/books and retry attempts, so they
are reported separately from catalogue counts. There is no claim of transactionally
consistent remote pagination; changing catalogues can overlap or omit records.

Kalshi book source time is absent and remains NULL. Metadata update times are not
book times; HTTP Date remains a header, not an inferred source timestamp. Original
nanosecond source strings remain archived even though Python age calculations use
microseconds. Provider metadata and unknown fields stay available for later review.

The local contract IDs identify which consumed fields are validated, not a promise
that all upstream fields or future schema versions are supported. Replay fixtures
preserve bytes, provenance and clocks, and test identical results offline.

Later migrations: reviewed rule versions and pair approvals (M2), normalized book
levels/sequence checks (M3), fee schedules and depth-based evaluations/retention
(M4), operational simulation/audit data (M5). M1 does not wire those paths together.

Storage uses short transactions and indexes by venue/time. Back up existing
archives before upgrading. Polling is bounded per command, but repeated commands
accumulate data; scheduled retention, disk thresholds and deployment hardening
remain later milestones.

## Deployment

Dedicated non-root Linux user, systemd service with restart/backoff, localhost-only dashboard (later), secrets external to repo (later). Backup the database regularly. Start with polling and small selected markets; only graduate to streaming after snapshot correctness and missed-update recovery are tested.
