# M5A D — payout, collateral and settlement mechanics

Implementation and official-source verification passed on **2026-10-23 UTC**.
**Real instrument/account review remains pending**, so overall M5A is incomplete.
E and M6 were not implemented. No real pair, fee profile, order, margin workflow,
funding action or settlement observation was created.

## Changes and source findings

The US documentation distinguishes full short collateral from net buying-power
reduction. Synthetic NO remains unsupported in economics and paper modeling;
normalizing `1-bid` does not change that restriction. Supported routes remain
cash-funded Kalshi YES/NO and US YES. Source evidence and exact scope are documented
in [the mechanics guide](SETTLEMENT_MECHANICS.md) and
[ten-source retrieval manifest](evidence/M5D_API_CHECKS.json).

Real pair reviews now require a versioned mechanics section with current source
hashes assigned to payout, collateral and timing roles. They explicitly declare
isolated long positions, cash-only funding, no offsets/proceeds reuse, account
scope and payout precision. Each scenario separates settlement from assumed cash
availability. No universal immediate-settlement or withdrawal guarantee is inferred.

Economics and paper models validate the actual book mechanism. Outputs separate
purchase cash, fee/slippage reserves and per-scenario settlement payouts. Capital-days
use the latest cash-availability assumption per venue. Unsupported sub-cent payout
rounding rejects a size; the size search continues. Paper cashflows use each leg's
hypothetical filled quantity; unknown fractional payout becomes UNOBSERVABLE.

Original/text source hashes are rechecked. Existing real approvals lacking D
mechanics invalidate on use; no automatic reapproval occurs. Legacy hypothetical
replays retain their explicitly assumed timing. Schema 7 is retained; review/audit
JSON carries `payout-mechanics/m5a-d-v1`, and new derived results use
`economics/m5a-d-v1` and `paper-stress/m5a-d-v1`. Earlier archived results are unchanged.

## Executed checks

`.venv/bin/python -m unittest discover -s tests -v` executed **270 tests**, all
passing. [The complete named output](evidence/M5D_TESTS.txt) records the exact tests.
The 20 new tests cover source hashes, explicit review, missing fields, stale/future
sources, cash timing, payout/route mismatches, unknown/negative/float values,
capital accounting, fractional payouts, partial liquidity, independent budgets,
scanner/paper integration, changed/corrupted documents, legacy live invalidation,
CLI review and the standalone isolated demo.

Executed smoke commands, all exit 0:

```bash
.venv/bin/python scripts/m4_demo.py --output data/m5d-demo \
  --mechanics-fixture tests/fixtures/m5d-hypothetical.json
.venv/bin/predarb pairs review 1 --db data/m5d-demo/research.sqlite3
.venv/bin/predarb research summary 1 --db data/m5d-demo/research.sqlite3
.venv/bin/predarb demo --db data/m5d-basic-smoke.sqlite3
.venv/bin/predarb report --db data/m5d-basic-smoke.sqlite3
```

Use new paths to repeat creation commands. The D demo ran at its **synthetic 2030
clock**, producing two positive observations followed by one stale-book rejection.
Its favorable sample modeled **200 contracts**, **$183.46 required cash** and
**$16.54 conditional profit**, with separate July 5/July 7 cash-availability dates.
Compared at the same evaluation time, the assumed extra holding days increase
capital-days by **380.38 dollar-days** ($85 × 1 + $98.46 × 3), without altering profit.
These are hypothetical model outputs, not observed fills, payouts or bank balances.

The subsequent `pairs review` smoke used the real clock and correctly returned
**INVALIDATED / UNVERIFIED mechanics** for future-dated synthetic evidence. Its
exit 0 means the report ran successfully, not approval. The archive still contains
three durable research cycles and **zero real pairs or fee profiles**. The
[validation record](evidence/M5D_VALIDATION.json) preserves results and commands.

The paper integration test modeled unequal fills of 200/40 contracts, retained a
minimum reviewed cash payout of $40 and a conservative downside of $64.69. A
separate fractional partial-fill test rejected unknown half-cent payout rounding.
Neither is a real settlement observation.

## Remaining acceptance

The tooling/source-check criteria passed; the following operator and operational
criteria remain open:

- Exact real contract equivalence, account scope and mechanics source-role review.
- Explicit supported payout precision and conservative cash-availability assumptions
  for every normal/exceptional scenario; unknown values keep a pair UNVERIFIED.
- Live fee applicability approvals from C and fresh comparable books.
- Workstream E readiness reporting and M4/M5 sustained zero-money run evidence.

No actual account balances, collateral postings, settlement timing or withdrawability
were measured. D does not enable US synthetic shorts. B's pre-rollout `sequence-v1`
compatibility still ends at October 29 UTC and requires revalidation before a longer
run crosses that boundary. The project's research-first funding ceiling is unchanged.
