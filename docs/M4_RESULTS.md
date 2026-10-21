# M4 implementation results — 2026-10-21 UTC

**M4 remains IN PROGRESS.** Economics, fee evidence, recording, polling, reporting,
derived-detail retention and exports are implemented and tested. The required
actual 30-day scanner observation and evidence audit have not happened. No live
trading, credentials, funds, real pair approval or M5 execution work was added.

## Implemented and tested

- Versioned taker models tied to exact venue/instrument/side/time, operator-reviewed
  applicability, raw fee-document hashes, expiry and failed-refresh invalidation.
  Unsupported/missing fees are rejected; no live fee profile was installed.
- Exact multi-level two-leg cost, conservative fill-fragmentation fee bounds,
  explicit reserve, independent venue budgets, bounded complete lot search,
  reviewed settlement delays and locked-capital ranking.
- Resumable read-only sessions, optional public GET refresh for approved pairs,
  current registry/book/fee gates, durable rejection records, cycle-attempt audit,
  cadence/equal-quote sampling metrics, summary and CSV exports.
- Atomic schema-4 migration; immutable evidence/summaries and isolated synthetic
  replay; explicit retention of at least 31 days of derived details, with permanent
  hashes/summaries and source evidence preserved. Raw archive growth is not solved
  by deleting provenance.

Operational behavior and configuration: [economics guide](ECONOMICS.md).

## Tests and demonstrations actually run

Environment: local Linux, Python **3.13.5**, project virtual environment, stdlib
SQLite and unittest. The baseline **101** tests passed before M4 changes.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m4_demo.py --output data/m4-final-demo
.venv/bin/predarb collect-kalshi --db data/m4-live-smoke.sqlite3 --limit 1 --max-pages 4 --event-ticker KXLNBELITE2GAME-26OCT231430CHASTC --books 2
.venv/bin/predarb collect-polymarket-us --db data/m4-live-smoke.sqlite3 --limit 1 --max-pages 3 --slug tec-mlb-champ-2026-09-27-mil
```

All commands above exited 0. **124 tests passed**; see the
[full log](evidence/M4_TESTS.txt). Tests include previous milestones, official fee
rounding examples, cumulative caps/rebates, unknown applicability, missing source
files, time/identity errors, fee refresh failures, reserves, multilevel size
selection, independent budgets, depth exhaustion, stale books, unsupported US NO,
raw replay provenance, registry revocation, resume/clock checks, disk guard,
audit immutability, migration, retention and CLI behavior. Compilation, whitespace checks and local documentation links also passed.
Hosted CI, other Python
versions and a long-running deployment were not executed.

The [hypothetical pipeline demo](evidence/M4_DEMO.json) archives source bytes and
simulates review of inverse propositions and fees in an isolated database. It
selected **200 contracts**, quote costs **$80 + $94**, fee bounds **$4 + $3.46**,
and reserves **$1 per venue**: **$183.46 modeled capital, $16.54 conditional net
profit bound**. The solver rejected the expensive tail, recorded another matching
fresh sample after 30 seconds, then a stale rejection at 61 seconds. The fixture
uses a synthetic 2030 clock; it is not observed performance. CSV and detailed
SQLite evidence remain in the local demo output directory.

Both [live collector smoke runs](evidence/M4_LIVE_RUNS.json) reached terminal
pagination: Kalshi 2 pages / 2 unique markets / 2 books / 8 raw responses;
Polymarket US 2 pages / 1 unique market / 1 book / 4 raw responses. Kalshi
normalization correctly rejected unknown source time; US quote quality passed
at capture. These unrelated scopes test adapters, not settlement equivalence.
All records remain `UNVERIFIED`.

The [research CLI trace](evidence/M4_COMMANDS.json) records actual `start`, two
empty-registry polling cycles, a deliberately UNVERIFIED rejection-only proposal
in a separate smoke copy, another `scan --refresh`, summary, CSV, prune dry run,
original demo and report. All exited 0. The third research cycle recorded
`PAIR_NOT_CURRENTLY_APPROVED`; no unreviewed economics or research network calls
occurred. The three cycles spanned about **1.21 seconds**, not 30 days. No real
pair was approved. The sample policy's budgets were zero.

A preserved-copy [M3 migration](evidence/M4_MIGRATION.json) retained **12 raw
observations, 3 catalogue entries, 3 registry instruments and 3 normalization
assessments**. New fee profiles/sessions/cycles were zero; nothing was backfilled
as a historical opportunity. The original M3 archive was preserved.

## Official documentation verification

The [source manifest](evidence/M4_API_CHECKS.json) records official document URLs,
local downloaded hashes/times and the direct PDF fetch's HTTP 429 failure. The
current July 7 Kalshi fee schedule was successfully read through the browser
tool; no downloaded PDF fixture/hash is claimed. Kalshi's fee-rounding, series
and scheduled-fee schemas were fetched directly. The US fee document was fetched
directly and read through the browser.

Models use current primary documentation, including the US schedule effective
**October 19, 2026 at 17:00 UTC**. They do not apply an older flat US rate. Series
exceptions/account-specific applicability still require operator review before
any live profile import. See [official source notes](API_SOURCES.md).

## Remaining acceptance gaps

1. **Actual 30-day read-only run and audit:** not run, not simulated as live history,
   and not marked complete. The application can record/resume bounded polling;
   its local tests and short smoke runs do not establish deployment reliability.
2. **Live prerequisites:** no real reviewed pair or real fee applicability profile
   exists. Kalshi REST has no source book time, so current live comparisons cannot
   pass M3 freshness gates. No authenticated transport was added. These conditions
   must be resolved before collecting useful cross-venue economics evidence.
3. **Measured lifespan:** the synthetic replay demonstrates matching-sample
   intervals and stale rejection only. Real quote-lifespan distributions, coverage,
   observed rejection patterns and independent opportunity audit remain pending.
4. **Supported scope:** long buys only; US synthetic NO, flat/unknown schedules,
   combos, additional account charges and unverified settlement fees fail closed.
   Public depth does not reveal actual fill fragmentation, so research uses fee
   bounds rather than claiming exact execution commissions or fills.
5. **Retention/operations:** source evidence and durable summaries intentionally
   remain; total archive growth, backup rotation, space reclamation and service
   hardening need an explicit operational policy and measurement.

The [roadmap](ROADMAP.md) remains open at M4. Stop before M5. Git author identity
is now configured in the repository. The earlier M1 and M2–M3 prerequisite work
was committed separately using that existing identity; the staged prerequisite
tree independently passed all 101 M3 tests before committing. M4 is recorded as
its own subsequent change. No identity was invented, and nothing was pushed or
published.
