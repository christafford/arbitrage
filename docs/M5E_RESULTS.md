# M5A Workstream E verification — 2026-10-24 UTC

E's research-readiness CLI is implemented and tested. It combines A–D evidence
checks with session policy, host/backup observations and the requested protocol
horizon, and returns actionable blockers in text or JSON. It is a read-only
snapshot, not an approval workflow, deployment command or sustained-run audit.

## Executed verification

```bash
.venv/bin/python -m unittest discover -s tests -p test_readiness.py -v
.venv/bin/python -m unittest discover -s tests -v
```

The final targeted run passed **17 tests**. The full run passed **287 tests** in
9.429 seconds. Every executed full-suite test name and outcome is recorded in
[evidence/M5E_TESTS.txt](evidence/M5E_TESTS.txt). An earlier targeted run exposed
a test setup that attempted to update an immutable session policy; the test now
creates a separate session, preserving the production immutability rule.

New coverage includes read-only expiry and evidence invalidation without audit
writes; CLI text/JSON/exit codes; missing files and unsupported schemas without
creation/migration; the writer lock and preservation of an outer transaction;
hypothetical rejection; bounded registry inspection; session, budget, host-clock
and backup gates; approval/mechanics/fee failures; missing books, wrong transport,
unknown schema, identity mismatch, stale/future/missing clocks and skew; invalid
prices, missing book fields, partial liquidity; search bounds; and protocol cutoff
versus present-time readiness. Offline archived venue replay exercises raw book
provenance, stale data and deliberate hash corruption through E. Positive gate
compositions are explicitly **HYPOTHETICAL mocks**, not real approval or live
acceptance evidence. The fixture is `readiness-test/m5a-e-v1`, contains no downloaded
venue data and therefore has no venue retrieval time.

Nine CLI smoke commands executed successfully against their expected exit codes
at approximately **2026-10-24 04:44 UTC**. Exact commands, stdout, stderr, exit
codes and archive file hashes are in
[evidence/M5E_VALIDATION.json](evidence/M5E_VALIDATION.json):

| Command / archive | Result |
| --- | --- |
| `research readiness --help` | Exit 0; documented options displayed. |
| `research start` on a new isolated empty smoke database with the zero-budget sample policy | Exit 0; session 1 created, no service started. |
| `ops backup` on that smoke database | Exit 0; snapshot and manifest created. |
| Readiness on smoke session 1 with its backup directory, JSON | Exit 2; host/session/backup passed, pair data/zero budgets/search/horizon blocked. No cycles or approved pairs existed. |
| Readiness on `data/m5c-live.sqlite3`, JSON and text | Both exit 2; schema 7, no pairs, no selected session. |
| Readiness on `data/discovery-validation.sqlite3`, JSON | Exit 2; schema 6 reported as requiring migration; no migration performed. |
| Readiness on `data/m5d-demo/research.sqlite3`, JSON | Exit 2; hypothetical pair evidence rejected for live readiness. |
| Readiness on an absent smoke database | Exit 1; file was not created. |

All three existing inspected archive files retained their SHA-256 hashes. The
unit tests additionally compare full logical database fingerprints, including
audit rows. No fresh venue calls, real approval changes, fee imports, credentials,
funding, order endpoints, services or M6 implementation were part of E.

## Remaining acceptance and next work

The CLI/tooling acceptance passes. Overall M5A and the M4/M5 sustained-run criteria
remain open:

- Human approval of equivalent real contracts and current C fee applicability.
- D instrument/account mechanics, payout precision and cash-timing reviews.
- Fresh comparable books and a verified collection/scanning deployment cadence.
- Live clocked-protocol revalidation before relying on a horizon crossing the
  configured **2026-10-29 00:00 UTC** `sequence-v1` cutoff.
- Evidence renewal within the current 24-hour limits, backups and actual
  multiweek/30-day run observations and audit.

A 21-day run starting on October 24 cannot rely on `sequence-v1` throughout.
Readiness always exposes that configured cutoff, but does not alter it. A passing
snapshot never proves future availability, profitable opportunities, live fills,
settlement cash availability or trading authorization. See the
[operator guide](READINESS.md) for exact semantics and how to resolve blockers.
