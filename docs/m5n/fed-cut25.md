# December FOMC — cut 25 bps

**UNVERIFIED — human review pending; no economic eligibility or trading authority.**
This is an assistant screen. Read [the scope and stream result](../M5N_RESULTS.md)
before interpreting a matching exceptional scenario as strict equivalence.

## Exact instruments and evidence

- Kalshi: `KXFEDDECISION-26DEC-C25`. Status at capture: `active`;
  receipt `2026-11-01T15:28:16.112884+00:00`.
- Polymarket US: `rdc-usfed-fomc-2026-12-09-cut25`. Status at capture: `MARKET_STATUS_OPEN`;
  receipt `2026-11-01T15:28:16.249195+00:00`.
- [Kalshi definition](../../data/m5n/contracts/fed-cut25-kalshi.json),
  [US definition](../../data/m5n/contracts/fed-cut25-polymarket_us.json).
  These readable JSON copies are reserialized; exact bytes and hashes are in
  [the evidence fixture](../evidence/M5N_DEFINITIONS.json) and isolated SQLite.
- [Official Kalshi terms](https://assets.kalshi.com/contract_terms/FEDDECISION.pdf); [official US product terms](https://www.polymarketexchange.com/files/products/PMUS%20-%20RDC%20-%20%282026.04.06%29.pdf).
  [Current document receipts and hashes](../evidence/M5N_SOURCES.json).
  US RDC applicability is product-family identification from the official listing
  and market description, pending reviewer confirmation; NFPC/URC PDFs are also
  explicitly linked by their market descriptions.

## Exceptional-payout screen

Outright cancellation makes both cut-YES payouts zero. A hypothetical 10-bps cut illustrates the rounding difference: Kalshi exact-25 YES is not established, whereas the US rounded-25 rule encompasses it. Under the exact Kalshi reading, Kalshi NO + US YES pays $2, not $0. Rounding alone therefore does not demonstrate downside on this route. It also does not prove the required lower bound in all other scenarios.

Review cancellation/rescheduling, early or missing decisions, revisions between different expiration clocks, asymmetric range changes and discretionary review. No full scenario dominance or equivalence is approved.

The ordinary event, threshold, observation period and authoritative source are
specified in the two complete definitions above. For Fed pairs this is the
December 8–9 FOMC decision, sourced to the Federal Reserve. For labor pairs it is
the October 2026 BLS Employment Situation release, scheduled in the descriptions
for November 6; payroll counts and seasonally adjusted U-3 are different measures.
Do not substitute a latest available value for the specified period outside an
applicable fallback rule.

## Distinct timing fields

| Role | Kalshi | Polymarket US |
| --- | --- | --- |
| API trading cutoff / administrative end | `2026-12-09T18:59:00Z` | `2026-12-24T04:00:00Z` — not a cash-release promise |
| API expected expiration | `2026-12-09T19:05:00Z` | UNKNOWN equivalent field |
| API latest expiration | `2027-03-10T19:01:00Z` | UNKNOWN equivalent field |
| Actual reusable cash / withdrawal time | UNKNOWN | UNKNOWN |

Product settlement provisions are generally next day after expiration, with
review exceptions. API timing and generic product clocks require precedence
review. For Fed, Kalshi's generic last-trading time differs from the API cutoff;
for labor, February 5 in the API is not February 6 (three calendar months after
November 6). No account funding hold, maximum dispute duration or withdrawal SLA
was verified. Do not annualize against `endDate`.

## Supported route, collateral and current fee evidence

Only cash-funded Kalshi long NO plus US long YES is supported here. Each venue
must hold its own purchase costs and fees; no cross-venue netting, borrowed funds,
collateral offsets or sale proceeds reuse are credited. US synthetic NO means
short YES and remains unsupported. Account eligibility, funding availability and
payout precision are unreviewed. See [existing mechanics requirements](../SETTLEMENT_MECHANICS.md).

- [Kalshi fee packet](../../data/m5n/contracts/fed-cut25-kalshi-fees/review.json):
  advertised kind `quadratic_with_maker_fees`, multiplier `1`.
- [US fee packet](../../data/m5n/contracts/fed-cut25-polymarket_us-fees/review.json):
  advertised coefficient `0.0695`.

Both packets retain raw official fee sources and blank applicability forms.
Neither is approved. The Kalshi fee-schedule PDF remains a required supplemental
source for approval; this task did not download a new copy. Account-specific
precision, FCM charges, settlement fees, exceptions and future changes are not
inferred from advertised parameters.

## Human review record

Reviewer: **pending**. Source-bound decision: **pending**. Do not approve based
only on the scenario that matches. Record exact source passages and precedence
for every unresolved branch, then use the existing explicit registry workflow
if a complete review supports equivalence. This packet itself creates no registry
approval. A clarification request to a venue has not been sent.

| Combined commitment | Executable economic evaluation |
| --- | --- |
| $5 | BLOCKED: settlement, fees, mechanics and fresh synchronized books |
| $25 | BLOCKED: same prerequisites |
| $100 | BLOCKED: same prerequisites |
| $500 | BLOCKED: same prerequisites |

No fill is inferred from displayed quantity and no live-money order path is used.
