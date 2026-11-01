# M5M review packet — cpi-two

**UNVERIFIED. Assistant screen: exclude from strict arbitrage. Human decision pending.**
Prepared 2026-11-01T04:03:40.190784+00:00. Both markets reported open in the captured definitions;
this is a historical observation, not a current availability guarantee.

- Kalshi: `KXCPI-26OCT-T0.2` ([official definition](https://external-api.kalshi.com/trade-api/v2/markets/KXCPI-26OCT-T0.2), [full terms](https://assets.kalshi.com/contract_terms/CPI.pdf).
- Polymarket US: `cpic-uscpi-october-mom-2026-11-10-gt0pt2pct` ([official definition](https://gateway.polymarket.us/v1/market/slug/cpic-uscpi-october-mom-2026-11-10-gt0pt2pct), [full terms](https://www.polymarketexchange.com/files/products/PMUS%20-%20CPIC%20-%20(2026.04.06).pdf).
- [Complete packet with original definition bytes](../../data/m5m/review-packets/cpi-two-packet.json).
- [Source-bound registry review](../../data/m5m/review-packets/cpi-two-registry.json).
- [Blank human form](../../data/m5m/review-packets/cpi-two-human-review.json). Pair ID 2 in `data/m5m/non-sports/research.sqlite3` only.

## Observation and thresholds

Both target October 2026, US all-urban-consumer, seasonally adjusted CPI,
month over month, strictly above **0.2%**. Equality is NO. The Kalshi
terms specify a one-decimal figure; US specifies the precision of the initial
publication. Verify the exact BLS series and published precision, not a calculation
from independently rounded index levels. This is a monthly statistic, not a touch
event or annual inflation rate. The captured descriptions schedule publication
for November 10, 2026 at 08:30 Eastern (13:30 UTC).

Authoritative ordinary source: [BLS CPI](https://www.bls.gov/cpi/).
Kalshi's definition uses the value available at expiration and excludes revisions
after expiration. US uses the first official non-preliminary release and excludes
later revisions. A correction between publication and Kalshi expiration can change
only one result. The exact cutoff and precedence of the specific description,
product terms and Rulebook remain a human review question.

## Settlement scenario comparison

| Case | Kalshi | Polymarket US | Strict assessment |
| --- | --- | --- | --- |
| Ordinary unchanged release above threshold | YES | YES | K NO + US YES pays $1 per matched unit, conditional on all other reviewed terms |
| Ordinary release at/below threshold | NO | NO | Same conditional $1 payout |
| Correction before Kalshi expiration crosses threshold | Expiration-value wording can include correction | Initial-release result retained | Complementarity unproven; both selected legs can lose |
| Publication delayed | Three-month generic limit plus captured government-shutdown extension to release or six months after shutdown end | Specific description waits up to three months, then substitutes most recent previous month | Timing and fallback conflict |
| No qualifying publication | Terms use an annualized-root calculation from last available index and its value 12 months earlier | Specific description uses previous available month; generic product terms also permit independent fair-price settlement/review | Different functions and precedence; cannot approve a common payoff |
| Cancellation/indefinite delay | Contract and Rulebook outcome-review contingency | Product permits last fair price or review | No guaranteed matched $1 payout |
| Source/methodology changed | Requires rule-specific review | Initial methodology retained; source/underlying/criterion may be changed under contingencies | No shared exceptional mapping established |
| Suspension/disputed result | Review can defer settlement | Review can defer settlement | No synchronized release or guaranteed endpoint |

A **hypothetical counterexample**, not an observed publication: the initial figure
is at the threshold and a correction before Kalshi expiration is above it. If the
Kalshi expiration-value clause applies, Kalshi YES wins while US YES loses;
buying Kalshi NO plus US YES pays $0. A human must resolve applicability rather
than replacing this scenario with a convenient fixed payout.

## Cutoff, settlement and reusable capital

| Role | Kalshi | Polymarket US |
| --- | --- | --- |
| API trading cutoff / administrative date | `close_time`: 2026-11-10T13:29:00Z | `endDate`: 2026-11-25T04:00:00Z — administrative field, not cash release |
| API expected expiration | 2026-11-10T14:56:00Z | Not supplied as an equivalent field |
| API latest expiration | 2027-02-09T14:56:00Z | Not supplied as an equivalent field |
| Contract settlement | Generally next day after expiration, with review exception | Generally next day after expiration, with review/contract exception |
| Account cash available / withdrawable | UNKNOWN | UNKNOWN |

Do not equate those API clocks with actual cash availability. The product PDFs and
metadata have different timing descriptions: Kalshi CPI's generic 08:31 Eastern
expiration differs from the current expected-expiration field; gas has scheduled
intraday termination rules that differ from its API cutoff. US contract defaults
can differ from `endDate`. Record precedence and an explicitly conservative
cash-release assumption if a candidate ever reaches mechanics review. No maximum
review delay or withdrawal SLA is established here.

## Trading sides, funding and fees

The only currently supported complementary route to review is **cash-funded Kalshi
NO plus US long YES** on the same proposition. Each venue needs its own purchase
cost and fees available in USD; no collateral offsets, cross-venue netting, borrowed
funds or proceeds reuse are credited. Buying the US synthetic NO side means short
YES; its full-payout collateral is not the displayed complement price, and the
scanner does not support that route. No account endpoint or balance was accessed.

The captured API side metadata and grids are in the full packet. Both venues'
account eligibility, access/FCM status, payout precision, funding availability,
settlement charges and transfer holds still need human verification. A published
100%-at-risk margin description is not permission to add margin or short trading.

- [Kalshi fee review](../../data/m5m/non-sports/cpi-two-kalshi-fees/review.json), [blank profile](../../data/m5m/non-sports/cpi-two-kalshi-fees/profile.json).
- [US fee review](../../data/m5m/non-sports/cpi-two-polymarket_us-fees/review.json), [blank profile](../../data/m5m/non-sports/cpi-two-polymarket_us-fees/profile.json).

Kalshi captured `quadratic_with_maker_fees`,
multiplier `1`,
no event override and no next scheduled change in the captured bounded responses.
US captured coefficient `0.0695`.
These are advertised parameters, not approved account applicability. Check the
[Kalshi schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf),
[rounding rules](https://docs.kalshi.com/getting_started/fee_rounding), and
[US schedule](https://docs.polymarket.us/fees). The Kalshi PDF download returned
429; the current July 7 schedule was read through the browser, with no new local
full-PDF hash claimed. A local official PDF is still needed for fee import.

## Human decision and economics

Human settlement, fee and mechanics review: **pending**. No form has been approved.
The assistant recommends exclusion from strict arbitrage for the conflicts above;
this is not a registry approval or a claim that a reviewer agreed.

For **$5, $25, $100 and $500** combined commitments, gross/net edge, executable
quantity, per-venue capital, opportunity duration and numeric unmatched-leg
exposure remain **UNKNOWN / BLOCKED**. Live economics has not been run. Displayed
sizes, even if archived, do not prove a fill. An unmatched purchased long can lose
its purchase cost and fees; no hypothetical partial fill is reported as realized.

Use the [review guide](../M5M_REVIEW_GUIDE.md) to record a reasoned rejection or
unresolved questions. Do not mark exceptional scenarios equivalent to enable a
calculation. All original captures remain intact.
