# Payout, collateral and cash timing — M5A D

The scanner supports **new, isolated, cash-funded long positions**: Kalshi YES
or NO, and Polymarket US YES. A proposed pair must still be complementary under
its human-reviewed outcome mapping. Inverse propositions can permit two YES legs.
No position netting, portfolio collateral return, borrowing, margin execution,
short execution, transfers or proceeds recycling is implemented.

## Verified distinction: payout, profit and funding

The [US collateral documentation](https://docs.polymarket.us/market-structure/collateral-and-margin)
distinguishes the full $1 collateral requirement for a short from its net buying
power reduction. For example, selling YES at $0.40 credits $0.40 proceeds and
locks $1, reducing buying power by $0.60. That last figure is not the collateral
requirement. The US [market structure guide](https://docs.polymarket.us/learn/trading/basics/buying-yes-vs-selling-no)
confirms that NO is synthetic short exposure, with no separate NO token.
Consequently `1-bid` remains only a normalized quote/payoff representation. It
does **not** enable a long-buy route or prove sufficient funding for a short.
The existing `SYNTHETIC_US_NO_UNSUPPORTED_CAPITAL_MECHANICS` rejection is retained.

For a supported long, the modeled cash requirement is purchase cost plus the
conservative fee reserve plus slippage reserve. No second face-value collateral
charge is added. Settlement cash is the reviewed per-contract payout times the
actual modeled quantity. The original purchase debit is not refunded a second
time, and gross settlement payout is not labeled profit. Funding reports expose
these components separately, with zero additional collateral and sale proceeds
only because the approved model is a cash-funded long.

The [US settlement guide](https://docs.polymarket.us/learn/markets/contract-settlement)
allows market-specific alternative settlement; generic $1/$0 explanations cannot
establish exceptional-case equivalence. Kalshi likewise says each contract's
rules determine its payout in its [balance guide](https://help.kalshi.com/en/articles/13823844-portfolio-balances-and-positions).
All six existing review cases remain required: YES, NO, VOID, CANCELLED,
SUSPENDED and SOURCE_REVISION. If payouts or timing are unknown, leave the pair
UNVERIFIED. No generic document can approve two instruments as equivalent.

## Operator workflow

Use the existing [pair review workflow](PAIR_REVIEW.md). Import current original
market rules and mechanics documents for **each exact instrument**, with faithful
text and actual retrieval times. The existing `pairs document` command archives
bytes/hashes and invalidates decisions when the evidence changes. No separate
mechanics database or approval command exists.

```bash
predarb pairs document --db data/research.sqlite3 \
  --venue polymarket_us --source-id REAL_SLUG \
  --url https://docs.polymarket.us/market-structure/collateral-and-margin.md \
  --source-file path/to/collateral.md --text-file path/to/collateral.md \
  --retrieved-at ACTUAL_UTC_RETRIEVAL_TIME --operator YOUR_NAME
predarb pairs review PAIR_ID --db data/research.sqlite3 \
  --template-output data/new-unapproved-review.json
```

Replace placeholders; these are not executable real-market suggestions. The
live review template includes a blank `mechanics` object. Assign source hashes
from the current review bundle to `payout_rules`, `collateral` and
`settlement_timing` under each venue. A document can cover several roles only if
its content actually supports them. General collateral material supplements the
market's own settlement rules; it does not replace them.

Complete the mechanics fields after review:

| Field | Supported value / decision |
| --- | --- |
| `schema` | `payout-mechanics/m5a-d-v1` |
| `reviewed` | Human sets true after reading the evidence |
| `position_scope` | `NEW_ISOLATED_LONG_POSITIONS` |
| `netting` | `NONE` |
| `funding` | `CASH_ONLY_NO_PROCEEDS_REUSE` |
| `timing_basis` | `OPERATOR_CONSERVATIVE_ASSUMPTION` |
| `venues.<venue>.route` | Exact route in the table below, matching the selected side |
| `currency`, `notional` | `USD`, decimal string `1` |
| `additional_collateral_per_contract` | Explicit decimal string `0`, after confirming the cash-funded long scope |
| `account_scope_reviewed` | Nonempty explanation covering account/position scope and no reliance on offsets |
| `payout_precision_reviewed` | Nonempty explanation supporting the exact cash amounts; unknown rounding remains unsupported |
| `documents` | Each of the three roles has 1..10 current raw SHA-256 references for that instrument |

| Venue and side | Route |
| --- | --- |
| Kalshi YES | `BUY_YES_FROM_COMPLEMENTARY_NO_BID` |
| Kalshi NO | `BUY_NO_FROM_COMPLEMENTARY_YES_BID` |
| Polymarket US YES | `BUY_LONG_FROM_OFFER` |
| Polymarket US NO | Unsupported for economics and paper modeling |

For **every settlement scenario**, add `kalshi_cash_available_at` and
`polymarket_us_cash_available_at`, with explicit UTC offsets. These must be at or
after that scenario's respective settlement time and in the future. A supported
local magnitude bound limits cash timing to 100 years; this is input validation,
not an exchange promise. Keep the existing payout, settlement time, condition,
outcome mapping and rationale fields.

Market close, determination, settlement, and cash availability are distinct.
The [Kalshi market FAQ](https://help.kalshi.com/en/articles/13823821-market-faqs)
says timing depends on official results and market rules. No universal guarantee
of immediate settlement or withdrawability was found. Cash-availability dates
here are **explicit operator assumptions for research**, not verified exchange
SLAs or bank withdrawal dates. If no reasonable bound can be supported, leave the
review incomplete. The model never transfers or reinvests assumed cash.

Only the operator should run `pairs approve ... --human-review` with a completed
real review. D validates its mechanics alongside the original equivalence checks;
it does not provide an automated reviewer. Required source hashes must belong to
the current instrument bundle and be no more than 24 hours old. Registry use
rechecks original/text hashes as well as existing freshness/evidence gates.
Legacy live approvals missing D fields invalidate on review/use, without automatic
reapproval. A new proposal and human decision are needed. Legacy **hypothetical**
M2–M5 replay remains available, labeled with its assumed settlement timing.

## Evaluation and paper behavior

Production economics requires explicit scenario cashflows. It rechecks the
book's actual mechanism, uses the latest cash-availability assumption per venue
for capital-days, and records the per-scenario payout and cash dates. Independent
venue budgets and the $10,000 research ceiling are unchanged; zero remains the
default authorized real-money exposure.

D supports only payouts exactly representable in cents. This is a conservative
local restriction, not a claim that either venue universally rounds settlements
to cents. For example, 0.01 contract paying $0.50 would produce half a cent. The
scanner skips that quantity and can consider 0.02 contract, whose one-cent payout
is exact. It never rounds an unknown payout up or silently assumes the full pair
payout. Rejected quantities appear in `payout_grid_rejections`; all unsuitable
sizes produce `PAYOUT_PRECISION_UNVERIFIED` in the rejection summary.

The paper model applies the same mechanism checks and records cashflow for each
leg's actual **hypothetical filled quantity**. It retains the existing unequal-fill
downside calculation and now exposes the associated cash events. If a partial-fill payout needs unsupported
rounding, the production paper comparison becomes UNOBSERVABLE. Original fill,
latency, cancellation, outage and participation assumptions remain unchanged.
No real position, settlement or transfer is observed or created by this model.

## Offline verification

From the repository root, use a new directory:

```bash
.venv/bin/python scripts/m4_demo.py --output data/new-m5d-demo \
  --mechanics-fixture tests/fixtures/m5d-hypothetical.json
.venv/bin/python -m unittest discover -s tests -v
```

The demo archives the fixture before parsing and runs at its explicit synthetic
2030 clock. It records supported source-bound hypothetical reviews, delayed cash,
two positive cycles and stale-book rejection. Inspecting that archive using the
ordinary CLI's real clock rejects the future-dated evidence; the fixture is not
a way to seed a live approval. See [D results and outstanding acceptance](M5D_RESULTS.md).
