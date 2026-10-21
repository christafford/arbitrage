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
- `src/predarb/kalshi.py`: versioned public catalogue, market/event/series detail and raw fixed-point bid book contracts. Complement conversion is isolated in M3 normalization.
- `src/predarb/polymarket_us.py`: versioned US public gateway catalogue, instrument-side metadata and raw book contracts. The institutional refdata interface requires access and is not the public collection path.
- `src/predarb/collector.py`: bounded traversal, source ID deduplication, loop detection, selected detail/book capture, separate source/receipt times, freshness/liquidity classifications and run accounting. All evidence is `UNVERIFIED`.
- `src/predarb/models.py`, `math.py`: the existing independent Decimal evaluator for explicitly hypothetical inputs. Collected books do not feed this evaluator.
- `src/predarb/store.py`: SQLite WAL and atomic schema migrations through version 4; committed raw responses, collection progress, and registry updates on metadata changes. Connection contexts close explicitly.
- `src/predarb/registry.py`, `registry_schema.py`, `registry_cli.py`: metadata candidates, immutable rule/source versions, human decision forms, explicit payoff review, expiry/invalidation and append-only audit. Registry approval grants no trading authority.
- `src/predarb/orderbooks.py`: immutable exact ask representations, supported market grids/side semantics, source/receipt/metadata clocks and quote-only depth coverage. All live evidence remains `UNVERIFIED`.
- `src/predarb/book_stream.py`: offline single-market Kalshi snapshot/delta replay, subscription sequence and connection-generation checks, conservative clock/send frontiers and fail-closed recovery. No live transport.
- `src/predarb/book_store.py`, `books_cli.py`: archived assessments with raw provenance, use-time validity, supersession and registry/skew comparison gates; local `books` commands.
- `src/predarb/fees.py`, `fee_store.py`: supported exact hypothetical taker-fill math, conservative quote bounds, immutable imported source evidence, operator-declared per-instrument/side applicability and expiry. No automatically installed live rates.
- `src/predarb/economics.py`: bounded complete common-lot search, per-venue research budgets, explicit reserve, reviewed settlement delays and conditional profit/capital-days. US synthetic shorts are refused.
- `src/predarb/research.py`, `research_schema.py`, `research_cli.py`: resumable bounded polling, approval/book/fee gates, rejection audit, immutable summaries, optional detail retention, sampling metrics and CSV. No unreviewed calculations or execution.
- `src/predarb/cli.py`: hypothetical demo, archival reports, one-shot collectors and local `pairs`/`books` commands. Exit 2 identifies incomplete bounded traversals or requested rejected book inspections.

[Current verified schemas](API_SOURCES.md), [M1 acceptance evidence](M1_RESULTS.md), [M2 acceptance evidence](M2_RESULTS.md), [M3 acceptance evidence](M3_RESULTS.md), [M4 implementation and pending acceptance](M4_RESULTS.md).

## Assumptions / unknowns

- A binary YES/NO pair pays $1 collectively **only** if their legal settlement outcomes are complementary and each venue pays as expected. Settlement terms, void/cancellation, timing, rounding, outage risk must be reviewed.
- NO is not automatically available as a long-buy instrument on every venue in identical form. Map the documented venue mechanics explicitly. A quote might be bid, ask, or implied from complements; document direction.
- Two API responses are **not synchronous**. Timestamps need source and receipt time; stale or crossed books must be rejected.
- Execution and post-trade settlement involve fees and capital tied up. Fees can depend on price/contract type, trade direction, and current schedule.
- No guaranteed simultaneous fills across venues; actual realized P&L can differ substantially from quoted theory.

## M1 archive tables (retained)

These tables were introduced in schema version 1 and remain in current schema 4:

- `raw_observations`: original response bytes and SHA-256, JSON/text inspection copy, venue/endpoint, UTC receipt time, separate source time where available, HTTP status, allowlisted headers, validation status/error and local/upstream schema version. Oversized responses are marked truncated and rejected. Starter rows remain `LEGACY_UNVALIDATED`.
- `collection_runs`: scope, schema version, start/finish times, `RUNNING`/`COMPLETE`/`PARTIAL`/`FAILED`/`INTERRUPTED`, accepted catalogue page count, returned/unique/duplicate record counts, next cursor/offset and failure text.
- `catalogue_entries`: per-run source IDs, raw observation reference, provider metadata timestamp, exact metadata/rule evidence JSON and evidence SHA-256; `verification='UNVERIFIED'`. A repeated ID updates this run's derived entry; every raw response remains separately archived.
- `book_captures`: raw observation reference, run/source IDs, source timestamp, freshness and liquidity at capture, `verification='UNVERIFIED'`. M3 derived levels/assessments are stored separately.
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

M2 registry, M3 assessment and M4 research tables are described below. M5 operational
simulation remains future work. These paths are not wired to execution.

Storage uses short transactions and indexes by venue/time. Back up existing
archives before upgrading. Polling is bounded per command, but repeated commands
accumulate source evidence. M4 adds a cycle space guard and explicit derived-detail
pruning; broader source retention, backup rotation and deployment hardening remain.

## M2 registry storage and validity

M2 introduced SQLite schema version **2**, retaining all M1 tables/data. Migration
backfills validated catalogue observations as unapproved instrument evidence.
Legacy or unsupported rows never become approvals; rejected backfills are audited.

| Added tables | Purpose |
| --- | --- |
| `rule_versions`, `registry_instruments` | Immutable contract snapshots and current per-instrument observation/provenance |
| `supplement_versions`, `registry_supplements` | Versioned collected Kalshi event/series rules, source URLs and raw references |
| `rule_documents`, `document_heads` | Original operator-imported source bytes and UTF-8 text, separate hashes and declared retrieval time |
| `pairs` | Proposed IDs, hypothetical/live separation, current decision, evidence hash, reviewer, expiry and reason |
| `pair_audit` | Append-only proposals, imports, decisions and invalidation/expiry records; approvals retain full reviewed evidence/form |

Contract fingerprints omit documented quote/volume/update-time fields and include
uninterpreted metadata conservatively. Event/series enrichment is tracked separately,
so a later catalogue page without enrichment does not erase or revive its sources.
Source freshness remains explicit. Imported document provenance is operator-declared,
not an independent network fetch. Evidence/version and audit UPDATE/DELETE operations
are blocked by SQLite triggers under ordinary writes.

Approval uses a serialized final evidence check and a complete, explicitly attested
human review. Observed rule/source changes and failed refreshes invalidate current
approvals. Expiry, freshness and cutoff checks run through registry reads/reporting;
future consumers must use those checks rather than raw cached status. No daemon
or cryptographic identity/tamper protection is claimed. See [the workflow](PAIR_REVIEW.md).

## M3 normalization and current validity

M3 introduced SQLite schema version **3**. `normalized_books` stores raw book/detail
observation references, normalizer version, evaluation time and age threshold,
serialized exact levels/rejections and quote usability **at assessment**. Migration
does not invent old assessments; existing raw evidence and registry history remain.
Collectors archive/validate raw responses before inserting derived results.

On inspection, raw hashes, complete snapshots, exact provider schema/endpoints,
same-run market/detail identity and detail-before-book order are rechecked. Validity
is recomputed at the requested/current clock. Old books and old metadata contexts
cannot silently override newer observations. Receipt, metadata and source age,
known market close, missing/future timestamps, supported ticks/quantities, both
ladders and crossed/locked levels are checked. Historical clocks are labeled replay.

Kalshi YES/NO asks derive from the opposing bid at `1-price`. Kalshi REST source
time remains unknown and blocks quote usability. US YES uses offers; US NO is an
explicitly synthetic short-YES quote equivalent from bids, not a separate NO-token
order path. Full REST snapshots replace independently. The Kalshi stream helper
only replays archived hypothetical messages with gap/reconnect recovery; no
authenticated WebSocket transport or undocumented US delta protocol is implemented.

Pair comparison rechecks human approval and market identity, both books and
source/receipt skew. It never computes profit or authorizes trading. Quote-only
depth walks preserve partial coverage and exhaustion. See [book inspection](BOOKS.md)
for semantics and limits. M4 consumes these gates in its separate research path;
the illustrative evaluator and all order paths remain disconnected.

## M4 economics and audit

Current schema version is **4**. Migration preserves all previous raw data, book
assessments and registry history; it creates no historical economic observations.

| Tables | Purpose |
| --- | --- |
| `fee_imports`, `fee_documents`, `fee_profiles` | Original configuration/source bytes and hashes, import failures, exact identity/time applicability, operator and expiry |
| `research_sessions`, `research_cycles` | Immutable policy/interval/mode and committed cycle records; a stored 30-day target is not proof of observation |
| `research_evaluations`, `research_details` | Durable rejection/economics summary and hash, separately expirable full registry/book/fee detail |
| `research_replays`, `research_audit` | Immutable synthetic input bytes and append-only session/cycle-attempt/pruning history |

Production research first rechecks human registry validity, optionally refreshes
approved sources using public GET collectors, then rechecks M3 comparability and
current fee profiles. It rejects unreviewed or incomparable data before economics.
Kalshi REST therefore remains blocked by unknown source time. Hypothetical replay
requires isolated storage and matching synthetic identities and cannot become live
evidence. No authenticated transport was added.

The pure evaluator walks exact depth and every bounded common lot, applying
independent venue budgets, conservative fee bounds and explicit reserves. Reviewed
latest settlement scenarios determine capital-days. Only supported long-buy
mechanics are evaluated. Results assume simultaneous full fills; repeated samples
and competing pairs are independent alternatives, never summed as realized P&L.

Source archives commit first. Cycle attempts are audited before processing;
finished summaries/details commit atomically. Summaries/audit/source evidence are
retained, while explicit pruning can remove derived detail older than 31 days.
Reports stream historical rows and retain per-pair sampling aggregates. Equal
quote samples do not prove continuous lifespan. A real 30-day observation and
reviewed audit remain pending; M4 is not complete. See [economics operations](ECONOMICS.md).

## Deployment

Dedicated non-root Linux user, systemd service with restart/backoff, localhost-only dashboard (later), secrets external to repo (later). Backup the database regularly. Start with polling and small selected markets; only graduate to streaming after snapshot correctness and missed-update recovery are tested.
