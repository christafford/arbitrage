# M2 acceptance results — 2026-10-21

M2 is complete: metadata suggestions, an audited human pair-review registry,
versioned settlement evidence, explicit complement/payout/timing review, expiry,
revocation and rule-change invalidation. No live pair was approved and no trading
or M3 book-normalization implementation was added.

## Implementation and verification

The M1 baseline suite was rerun first: **41 tests passed**. Current official
[Kalshi market documentation](https://docs.kalshi.com/api-reference/market/get-market),
[US market detail documentation](https://docs.polymarket.us/api-reference/markets/get-market-by-slug)
and [US rule structure](https://docs.polymarket.us/learn/advanced/rule-structure)
were checked again. Existing public endpoints and versioned schemas are used;
there are no new provider endpoint paths. Collector fixtures remain historical
real snapshots; all new decision examples are explicitly hypothetical.

Added `registry.py`, `registry_schema.py`, and `registry_cli.py`. Schema version 2
migrates starter/M1 databases and backfills validated catalogues without creating
or approving pairs. Market contract snapshots, supplemental event/series sources,
original document bytes and extracted resolution text have version hashes.
Document import records the operator, declared URL/retrieval time, import time,
exact bytes and independent raw/text SHA-256 values. Full source provenance and
resolution text are exposed for review and retained in approval audit events.

Metadata suggestions remain `UNVERIFIED`; no price/book field is used to generate
or approve them. Human review requires an exact current evidence hash, identity,
attestation, eight completed comparisons, explicit bijective YES/NO mapping,
complementary leg selection, and normal/exceptional payoff/timing scenarios.
Unknown payouts, unsupported precision, incomplete scenarios, mismatched evidence,
unavailable instruments and stale evidence fail closed. Expiry is explicit and
bounded by a 24-hour evidence window. Approvals authorize no trades.

Ordinary quote/volume/update-time changes preserve the contract version. Unknown
additional metadata is fingerprinted conservatively. Observed market, event,
series or document changes invalidate approvals; restoration does not revive them.
A failed/interrupted source collection also invalidates approvals. Audit/version
tables reject ordinary UPDATE/DELETE operations. The final approval/evidence check
uses `BEGIN IMMEDIATE` to serialize it with collector writes.

## Executed acceptance demonstration

```bash
.venv/bin/python scripts/m2_demo.py --db data/m2-final-demo.sqlite3
.venv/bin/predarb demo --db data/m2-final-demo.sqlite3
.venv/bin/predarb report --db data/m2-final-demo.sqlite3
```

The first command exercised real CLI propose/review/approve/reject/revoke/document/
list/audit actions against an isolated **hypothetical** database. It exited 0 and
asserted these outcomes:

| Case | Evidence and result |
| --- | --- |
| Metadata suggestions | Two identical-title suggestions; both UNVERIFIED |
| Near-identical but different rules | FINAL report including revisions versus FIRST report excluding revisions; approval refused, pair 1 REJECTED |
| Reviewed synthetic pair | Pair 2 approved with a simulated human review, then REVOKED |
| Changed resolution text | New pair 3 approved with a simulated review, then INVALIDATED after an imported amendment |
| Final state | No approved pairs; every pair hypothetical; trading_authorized=false |
| Audit | 12 immutable events, including document imports and all successful decisions |

[Demo summary](evidence/M2_DEMO.json) and [exact commands/exit codes](evidence/M2_COMMANDS.json)
record the outcomes. Full JSON output, review forms and the changed text remain
in local `data/m2-final-demo-artifacts/cli-trace.json`. The old arithmetic demo
still produced its labeled 400-pair, $391-capital, $9-profit hypothetical result.

## Live collection and archive migration checks

Both public collectors were run after the registry integration, **20:22:06–20:22:09 UTC**:

```bash
.venv/bin/predarb collect-kalshi --db data/m2-live-smoke.sqlite3 \
  --limit 1 --max-pages 4 --event-ticker KXLNBELITE2GAME-26OCT231430CHASTC --books 2
.venv/bin/predarb collect-polymarket-us --db data/m2-live-smoke.sqlite3 \
  --limit 1 --max-pages 3 --slug tec-mlb-champ-2026-09-27-mil
.venv/bin/predarb pairs candidates --db data/m2-live-smoke.sqlite3
.venv/bin/predarb pairs list --db data/m2-live-smoke.sqlite3
.venv/bin/predarb report --db data/m2-live-smoke.sqlite3
```

All exited 0. Kalshi: two pages, two unique markets, two books and eight raw
responses. Polymarket US: two pages, one unique market, one book and four raw
responses. Registry: three instruments, event/series evidence for each of the two
Kalshi markets, **zero live proposals or approvals**. No metadata candidates were
suggested between these unrelated small scopes. Raw captures remain local.

A SQLite backup of the original M1 acceptance archive was migrated separately:
12 raw observations, three catalogue entries and one hypothetical opportunity
were preserved; three registry instruments and four supplemental heads were
backfilled, with zero pairs. The original M1 database was not modified.
[Live and migration counts](evidence/M2_LIVE_AND_MIGRATION.json) record both checks.

Final suite: `python -m unittest discover -s tests -v` — **63 tests passed**,
including all 41 original/M1 tests and 22 M2 tests.
[Full test names/output](evidence/M2_TESTS.txt) list exactly what ran. Coverage
includes CLI actions, same-title semantic rejection, approval attestations, direct
and inverse outcome mappings, exact scenario arithmetic, missing/stale/future
inputs, raw/text hash changes, unchanged refreshes, metadata drift, event/series
changes, failed collection, expiry, revocation, restoration, immutable history,
synthetic/live separation and migration/backfill. `compileall` and Git whitespace
checks also passed. Hosted CI and additional Python versions were not executed.

## Limits and handoff

No M2 implementation/acceptance blocker remains. Read [the operator guide](PAIR_REVIEW.md)
for exact form fields and workflow. A real human still has to supply and review
complete official legal sources before approving any actual pair. File import
records declared provenance; it does not independently fetch URLs, validate PDF
extraction or authenticate human identity. A local operator can make an incorrect
semantic judgment; code validates review completeness and arithmetic, not legal
truth or exhaustive scenario coverage. No fabricated claim of real equivalence
was made in this milestone.

Changes are detected when data is collected or documents are imported; there is
no background watcher for remote amendments. Freshness/expiry checks bound reuse
and must be called by future consumers. The schema's cached status is not a
standalone authorization API. SQLite guards are not tamper protection against a
privileged owner. The 24-hour evidence window is a conservative local research
policy, not a measured guarantee about venue update latency.

At M2 completion, M3 remained unstarted: there were no normalized actionable
books, sequence/tick/lot checks, live opportunity evaluation or order paths.
Git author identity was unset from M1; no identity was invented and no push was
attempted. M3 was separately authorized afterward; see [M3 results](M3_RESULTS.md).
