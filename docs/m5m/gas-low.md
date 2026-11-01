# M5M review packet — gas-low

**UNVERIFIED. Assistant screen: exclude from strict arbitrage. Human decision pending.**
Prepared 2026-11-01T04:03:40.190784+00:00. Both markets reported open in the captured definitions;
this is a historical observation, not a current availability guarantee.

- Kalshi: `KXAAAGASMIN-26DEC31-3.20` ([official definition](https://external-api.kalshi.com/trade-api/v2/markets/KXAAAGASMIN-26DEC31-3.20), [full terms](https://assets.kalshi.com/contract_terms/AAAGASMINMAX.pdf).
- Polymarket US: `aaagaspc-usgas-low-2026-12-31-lt3pt20` ([official definition](https://gateway.polymarket.us/v1/market/slug/aaagaspc-usgas-low-2026-12-31-lt3pt20), [full terms](https://www.polymarketexchange.com/files/products/PMUS%20-%20AAAGASPC%20-%20(2026.08.07).pdf).
- [Complete packet with original definition bytes](../../data/m5m/review-packets/gas-low-packet.json).
- [Source-bound registry review](../../data/m5m/review-packets/gas-low-registry.json).
- [Blank human form](../../data/m5m/review-packets/gas-low-human-review.json). Pair ID 4 in `data/m5m/non-sports/research.sqlite3` only.

## Observation and thresholds

Both reference AAA's US national average **regular gasoline** price per gallon,
strictly below **$3.20**, at any observation in the specified interval.
Equality does not meet the criterion. They are not state prices, premium gas,
or a single year-end observation.

The intervals differ. US explicitly covers **September 9–December 31, 2026,
inclusive**. Kalshi covers issuance through December 31 inclusive; its API open
time is March 24 00:00 UTC (March 23 Eastern). The low contract explicitly confirms
March 23 issuance in its secondary rule. The high contract's precise issuance
boundary must be verified against its listing record; it is not silently inferred
from a generic annual title. End-date timezone boundaries also require review.

Authoritative ordinary data: [AAA prices](https://gasprices.aaa.com/).
The US product names the exchange as Source Agency with AAA as primary reference;
it can substitute sources. Kalshi names AAA. Kalshi excludes changes after
expiration; US uses the first sufficient official publication, with a separate
clearly-erroneous-data correction exception.

## Settlement scenario comparison

| Case | Kalshi | Polymarket US | Strict assessment |
| --- | --- | --- | --- |
| Qualifying price within the common interval | YES, subject to its rules | YES, subject to its rules | Conditional ordinary correspondence only |
| No qualifying price in either interval | NO | NO | Conditional ordinary correspondence only |
| Qualifying price only before September 9, within Kalshi interval | YES | NO | K NO + US YES can both lose; direct observation-window mismatch |
| Later correction crosses threshold | Expiration-based rule | Initial-publication rule except clear-error discretion | Outcomes not proven identical |
| AAA data unavailable or discontinued | Contract/Rulebook review | Source substitution and outcome review | Common fallback payout not established |
| Cancellation, suspension, ambiguous or erroneous source | Venue-specific review | Venue-specific review / alternative source | Independent discretion and release uncertainty |

This mismatch is about the proposition itself. A common headline, end date and
threshold cannot establish a strict hedge. Do not assume pre-September observations
were harmless without complete source-backed evidence and human review.

## Cutoff, settlement and reusable capital

| Role | Kalshi | Polymarket US |
| --- | --- | --- |
| API trading cutoff / administrative date | `close_time`: 2026-12-31T06:25:00Z | `endDate`: 2027-01-15T04:00:00Z — administrative field, not cash release |
| API expected expiration | 2027-01-01T06:45:00Z | Not supplied as an equivalent field |
| API latest expiration | 2027-01-07T06:30:00Z | Not supplied as an equivalent field |
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

- [Kalshi fee review](../../data/m5m/non-sports/gas-low-kalshi-fees/review.json), [blank profile](../../data/m5m/non-sports/gas-low-kalshi-fees/profile.json).
- [US fee review](../../data/m5m/non-sports/gas-low-polymarket_us-fees/review.json), [blank profile](../../data/m5m/non-sports/gas-low-polymarket_us-fees/profile.json).

Kalshi captured `quadratic`,
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
