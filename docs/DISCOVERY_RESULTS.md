# Discovery extension verification — 2026-10-22 UTC

This is an M1/M2 discovery extension, not M6 or authorization for trading.
Human equivalence approval requirements remain unchanged.

Implemented and verified offline:

- Full fresh-catalogue search by default, indexed normalized subject/description
  retrieval, explicit event dates, threshold inclusivity/unit/magnitude signals,
  and resolution-language/cutoff conflicts.
- Exact displayed-depth ranking with missing/stale/invalid provenance rejection;
  Kalshi source time remains unknown and never becomes executable liquidity.
- A bounded persistent review queue with original definition links, rule-version
  references and prior human decisions; use-time checks remove stale or changed
  members. Suggestions cannot create or approve registry pairs.
- Bounded two-venue refresh, active filters, terminal pagination versus partial
  coverage, shared paced clients for selected details/books, errors, disk guards,
  and offline mode. Hourly systemd timer/service templates pass syntax validation.
- Atomic schema-6 migration and queue replacement. A preserved copy of the
  schema-5 live smoke archive retained every row in all 28 pre-existing tables.
  The source archive remained schema 5. Schema-6 backup verification also passed.

Executed `python -m unittest discover -s tests -v` in `.venv`: **192 tests passed**,
including all existing human review, economics, paper, provider retry and backup
checks plus 27 discovery tests. Discovery coverage includes more than 500
instruments, altered report policies, missing/conflicting thresholds, event-time
normalization, failed/partial collections, real-schema detail/book replay,
source links, empty/stale/invalid liquidity, queue rollback, migrations, CLI,
provenance tampering, disk exhaustion and retired-market filtering. Test market
alterations and review scenarios are explicitly hypothetical.

CLI smoke commands executed: `discovery --help`, `discovery refresh --help`,
offline queue refresh on a migrated copy, `pairs candidates`, `demo`, `report`,
schema-5/schema-6 `ops backup`, and the complete hypothetical `scripts/m2_demo.py`
workflow (one rejection, one revocation, one evidence-change invalidation). No existing research archive was upgraded
in place and no service was installed or activated.

A read-only profile using 1,000 Kalshi records and 22,447 US records initially
produced 8,108,334 candidate comparisons from shared metadata. Restricting
description retrieval to rare shared terms reduced that to 792,935; 3,680
survived the evolving top-20 score floor. This is a sampled retrieval profile,
not a recall/precision measurement or a full-catalogue performance guarantee.

Live collection results are recorded below after the bounded validation run.
Raw provider evidence stays in ignored local `data/` archives; it is not published.

Remaining limits: heuristic false positives/negatives, explicitly partial page
budgets, no resumption within a capped traversal, no automatic raw archive pruning,
no authenticated Kalshi streaming source time, no reviewed live pair or fee
profile, no sustained scheduled-run evidence. M4's 30-day and M5's multiweek
acceptance remain pending. See [discovery usage](DISCOVERY.md).
