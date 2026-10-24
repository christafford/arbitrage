# Discovery update timestamp correction — 2026-10-24

The reported discovery failure was caused by a local schema requirement, not the
preceding recoverable transport retry. `data/research.sqlite3` observation 1224,
received at **2026-10-24 05:32:26.653418 UTC**, contains 130 US markets; **116 omit
`updatedAt`**. The official MarketService 1.0.0 schema makes this field optional
and nullable. Our adapter incorrectly required a string for every market.

The failed US run was correctly excluded from discovery, causing zero cross-venue
candidates even though Kalshi had completed 818 pages. The final queue's
`coverage.scope=queued_instruments` explains its zero Kalshi eligible count;
`catalogue_coverage_at_refresh` records the broad Kalshi catalogue eligibility.
The stored 80,999 US instruments are not silently usable after the failed refresh.

The fix accepts absent/null metadata update time and stores SQL NULL in catalogue
and detail source timestamps. Present malformed times still reject the raw
response. No created/receipt timestamp replaces source update time. Book source
time, stale-data checks, price/quantity validation and human approval gates stay
in force. There is no database migration or rewriting of rejected history.

## Verification

Executed:

```bash
.venv/bin/python -m unittest discover -s tests -p test_collectors.py -v
.venv/bin/python -m unittest discover -s tests -v
```

The targeted collector run passed **23 tests**. The final full suite passed
**291 tests**, including four new regression tests for the captured omission,
absent/null page and detail clocks, malformed present clocks, independent stale
book time and required book timestamps. Existing price, quantity, partial-depth,
provenance, discovery and readiness tests also ran. Exact full-suite names and
results are in [the test log](evidence/DISCOVERY_UPDATED_AT_TESTS.txt).

The complete original 130-market page now passes validation in memory. Its stored
status remains `REJECTED`, and collection run 2 remains `FAILED`. A representative
public excerpt with retrieval time, schema and parent/body hashes is saved in
`tests/fixtures/poly-missing-updated-at-live.json`. Altered test values and synthetic
pagination sequences are explicitly hypothetical.

A live scoped collection of one affected slug in an isolated smoke database
completed in **two pages, one market, exit 0**. This later live response supplied
`updatedAt`; the original archived response is the observed missing-field regression
case. Offline discovery against that
smoke archive exited 0 and found one eligible US instrument; it had no Kalshi
catalogue, so zero cross-venue candidates was expected. Exact commands, source
verification and output are recorded in
[the validation manifest](evidence/DISCOVERY_UPDATED_AT_VALIDATION.json).

The full two-venue discovery traversal was **not rerun**. The operator's main
archive was inspected read-only. The successful one-market smoke does not prove
that every current catalogue record satisfies every other schema requirement or
that a real pair is equivalent. Follow the [recovery commands](DISCOVERY.md) to
start a new US traversal while the completed Kalshi observations remain fresh,
then rebuild the queue. Offline refresh alone cannot clear a failed collection.
