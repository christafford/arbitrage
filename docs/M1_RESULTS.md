# M1 acceptance results — 2026-10-21

M1 is complete for **read-only catalogue and selected book capture** through the
official public US APIs. No credentials, live order paths, deposits or trading
were added. M2 and subsequent milestones have not been started.

## Baseline actually executed

Read `AGENTS.md`, `README.md`, all six files originally in `docs/`, and all source
and test files before editing. Created `.venv` and ran `python -m pip install -e .`.
The original `python -m unittest discover -s tests -v` executed **6 tests**, all
passing. It emitted an unclosed SQLite connection warning; connection context
managers now close explicitly and migration tests cover that behavior.

Executed `predarb demo` and `predarb report` against
`/tmp/predarb-baseline.sqlite3`. Output: hypothetical 400 pairs, $391.000 capital,
$9.000 modeled profit, 2.302% modeled ROI. One hypothetical evaluation was archived.
Those values come from the existing illustrative inputs, not venue observations.

## Implemented behavior

- Kalshi: cursor pagination excluding multivariate contracts, optional event
  filter, exact market rules/deadlines, selected market details, cached event and
  series details with settlement sources and official contract URLs, raw YES/NO
  bid snapshots.
- Polymarket US: stable-ID-ordered offset pagination, optional slug filter,
  market/instrument/side metadata, exact provider description/asset-term evidence,
  selected details and bid/offer snapshots with source timestamps. The public
  gateway replaces the starter's unverified refdata URL; see [API verification](API_SOURCES.md).
- Strict validation of consumed fields and shape, finite exact Decimal values,
  identity checks, schema drift rejection, page/cursor loop detection, and
  per-run instrument deduplication with reconciled counts. Uninterpreted additive
  fields are retained; opaque provider metadata is never guessed.
- Every completed HTTP response is committed before JSON parsing/validation,
  including error and invalid-schema bodies. A response over the 10 MB limit
  retains only its capped prefix and is explicitly marked truncated/rejected.
- TLS and verified US origins only, redirects disabled, GET only, 12-second
  timeout, maximum three attempts, at most four request starts per second per
  client, exponential backoff and `Retry-After`. A delay above 60 seconds stops
  with an explicit retry-later error. No aggressive provider limit probing.
- SQLite schema version 1 migrates starter databases atomically. Original
  observations remain `LEGACY_UNVALIDATED`; bytes cannot be reconstructed after
  the fact. New records retain raw bytes, body hash, allowlisted response headers,
  schema version, validation result, UTC receipt time, separate source time and
  endpoint. Catalogue rows retain IDs, metadata, exact rule evidence and hashes.
- Runs record status, scope, counts, duplicates and continuation. CLI exit codes:
  0 terminal traversal; 2 page budget/incomplete; 1 failure; 130 interruption.
  Previously committed pages remain available after failure/interruption.
- Every live catalogue/book record is `UNVERIFIED`. No matching, approvals,
  normalized actionable asks, fee estimates or automatic signals were added.

## Live acceptance evidence

Final acceptance collection ran **19:58:27–19:58:30 UTC**. Both commands exited 0:

```bash
.venv/bin/predarb collect-kalshi --db data/m1-final.sqlite3 \
  --limit 1 --max-pages 4 --event-ticker KXLNBELITE2GAME-26OCT231430CHASTC --books 2
.venv/bin/predarb collect-polymarket-us --db data/m1-final.sqlite3 \
  --limit 1 --max-pages 3 --slug tec-mlb-champ-2026-09-27-mil
.venv/bin/predarb demo --db data/m1-final.sqlite3
.venv/bin/predarb report --db data/m1-final.sqlite3
```

| Measure | Kalshi | Polymarket US |
| --- | --- | --- |
| Scope | One named event | One named market |
| Catalogue pages | 2 | 2 |
| Returned rows by page | `[1,1]` | `[1,0]` |
| Returned / unique / duplicates | 2 / 2 / 0 | 1 / 1 / 0 |
| Terminal continuation | Empty cursor | Empty page at offset 1 |
| Run status | COMPLETE | COMPLETE |
| Detail responses | 2 markets + 1 event + 1 series | 1 market |
| Selected books | 2 | 1 |
| All raw HTTP responses | 8 | 4 |
| Book liquidity | Both two-sided | Two-sided |
| Freshness at capture | UNKNOWN_SOURCE_TIME | FRESH under 60 seconds |

Kalshi's REST book has no source timestamp; neither HTTP `Date` nor market metadata
update time was substituted. Polymarket US source time was
`2026-10-21T19:58:06.110730908Z`, separate from receipt time. A quiet book's transaction
time can be old even when freshly fetched; the conservative classification is
still stale when it exceeds the threshold. "Fresh" in the report describes the
historical capture, not the book's age when a later report runs.

[Machine-readable run results](evidence/M1_LIVE_RUNS.json) record original UTC
boundaries and all book classifications. The complete sanitized raw response
sequences are in [Kalshi fixtures](../tests/fixtures/kalshi-scoped-acceptance.json)
and [Polymarket US fixtures](../tests/fixtures/poly-scoped-acceptance.json).
The local SQLite archive is ignored by Git. Additional real unscoped two-page
fixtures contain four distinct markets per venue; they test broader pagination
without claiming a full venue census. Scoped acceptance was deliberate: it reaches
real terminal pages with a small request budget.

The report showed eight Kalshi and four Polymarket US raw responses, three
`UNVERIFIED` books, and the same single $9.00 **hypothetical** demo evaluation.
No exchange-derived opportunity or realized P&L was produced.

## Executed verification

Final suite: `python -m unittest discover -s tests -v` — **41 tests passed**.
[Full test names and output](evidence/M1_TESTS.txt) identify exactly what ran.
The suite is offline: live captures are replayed through the real HTTP parser,
validator, collector and SQLite path using a socket-free transport.

Coverage includes both real schemas and complete acceptance sequences, deterministic
replay, pagination/terminal behavior, duplicate counting, unknown/missing/wrong-type
fields, malformed/nonstandard JSON, changed identities, invalid prices/quantities,
empty and partial liquidity, stale/future/missing source times, 401/404, 429/503,
network failures, bounded retries, delay headers, response caps, redirect/host
restrictions, interruptions, CLI outcomes, migrations and the original arithmetic
and storage tests. Live commands exercised both public providers successfully;
failure scenarios are labeled hypothetical offline tests.

Also executed package installation, `compileall`, `git diff --check`, local
documentation link checks, and the smoke commands above. After final pagination
and freshness review, both live collector commands plus demo/report were rerun
against `data/m1-postreview.sqlite3`; both traversals completed with the same
counts. [Final smoke output](evidence/M1_FINAL_SMOKE.json) records the new run
timestamps and classifications. Validation ran on Python 3.13.5; other supported
Python versions were not executed. Hosted CI was not run; M0's outstanding hosted CI item remains
unchecked. No multiweek reliability or performance claim is made.

A local milestone commit was attempted after verification. Git rejected it because
`user.name` / `user.email` are unset. Changes are staged; no identity was invented
and no remote push was attempted. This affects commit creation, not acceptance
test or collection results.

## Operational limits and next milestone boundary

There are no remaining M1 code/acceptance blockers for the tested public API path.
The institutional Polymarket US refdata interface returns 401 without access;
that interface is not needed for the public collector and was not bypassed.
Venue eligibility and permission for ongoing storage/redistribution are not
established by connectivity. See the checked restrictions and future-dated
Polymarket terms issue in [API sources](API_SOURCES.md).

Offset/cursor catalogues can move during traversal; terminal pagination proves
completion of the observed filtered traversal, not atomic completeness across
venues. Defaults bound pages and selected books; capped runs are partial. A
continuation is audit evidence, not an automatic resume command: restart a fresh
run after reviewing a failure. Repeated invocations grow the archive; automated
retention, disk alarms, scheduling and deployment remain later roadmap work.

API descriptions and rule links are evidence, not a complete human-reviewed legal
settlement specification. Missing/blank rule evidence never approves anything.
Contract PDF review, equivalence approvals and their invalidation belong to M2;
book normalization, tick/lot/sequence checks and actionable stale-book rejection
belong to M3. M1 freshness flags convey uncertainty without feeding the hypothetical
evaluator. Stop here before M2.
