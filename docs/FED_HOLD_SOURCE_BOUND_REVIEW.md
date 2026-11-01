# December 2026 Fed hold — source-bound review assistance

**Research decision: UNRESOLVED. Do not approve for strict arbitrage or live trading.**

Reviewed source set: `docs/M5N_FED_HOLD_REVIEW.md`, `docs/evidence/M5N_FED_HOLD_REVIEW.json`, `docs/evidence/M5N_FED_HOLD_REVIEW_SOURCES.json` in `arbitrage(7).zip`, plus current publicly accessible product terms on 2026-11-01. The market-specific API endpoints could not be independently retrieved by this review; rely on the ZIP's archived hashes for the exact captured versions and re-fetch them before any operator decision.

- Kalshi: `KXFEDDECISION-26DEC-H0`; product terms: https://assets.kalshi.com/contract_terms/FEDDECISION.pdf . Important passages: p.1 `Underlying`, `<action>`, `Payout Criterion`; pp.1–2 `Expiration`, `Contingencies`.
- Polymarket US: `rdc-usfed-fomc-2026-12-09-nochng`; product terms: https://www.polymarketexchange.com/files/products/PMUS%20-%20RDC%20-%20%282026.04.06%29.pdf . Important passages: pp.2–4 `Underlying`, `Payout Criterion`, `Delayed Meeting`, `Cancelled Meeting`, `No Meeting Held`, `Emergency Rate Decisions`, `Rounded Outcomes`, `Clarifications`.
- Kalshi specific market: https://external-api.kalshi.com/trade-api/v2/markets/KXFEDDECISION-26DEC-H0
- Polymarket US specific market: https://gateway.polymarket.us/v1/market/slug/rdc-usfed-fomc-2026-12-09-nochng

## Proposed funded hedge

Buy Kalshi NO and Polymarket US YES on the *same* no-change proposition. For binary settlement, denote Kalshi YES payout K and Polymarket US YES payout U. Combined selected-leg payout = 1 − K + U. It is $1 only if K=U for every applicable scenario. Fees, execution, and settlement timing are separate and not approved.

## Source-bound comparison

| Review item | Finding | Source | Operator decision |
|---|---|---|---|
| Applicability and precedence | Exact specific-market text and hierarchy relative to product terms must be confirmed. | Both specific API definitions; both product terms | UNKNOWN |
| Ordinary unchanged meeting | Both appear to award YES for no change at specified FOMC meeting. Baseline, date, and exact rule precedence still must be checked. | Kalshi FEDDECISION p1; US RDC pp2–3 | PROVISIONALLY ALIGNED, not approved |
| Ordinary rate change | Both appear to award NO for a qualifying change; Kalshi speaks of target *range*, US uses *upper bound*. | Kalshi p1; US p2 | PROVISIONALLY ALIGNED for change to both bounds only |
| Postponed/rescheduled meeting | US explicitly follows the rescheduled meeting. Kalshi expressly classifies *cancellation* as hold and does not establish the same postponed branch in generic terms. If Kalshi resolves hold YES while US resolves hold NO on a later changed-rate meeting, selected legs can pay $0. | Kalshi p1 Payout Criterion; US p3 Delayed/Cancelled Meeting | MATERIAL UNRESOLVED |
| No meeting/no designated replacement | US settles based on effective rate at expiration; Kalshi cancellation says hold YES. An intervening change could diverge. | Kalshi p1 Payout Criterion; US p3 No Meeting Held | MATERIAL UNRESOLVED |
| Upper/lower bounds | US explicitly measures upper bound. Kalshi defines change to range. A lower-bound-only change may yield unequal classifications. | Kalshi p1 Underlying/action; US p2 Underlying | MATERIAL UNRESOLVED |
| Revised announcement or timing | Both exclude post-expiration revisions, but expiry and evidence cutoffs differ. | Kalshi pp1–2; US pp2–3 | UNKNOWN |
| Review/source substitutions | Both allow outcomes reviews; US additionally permits new source/underlying/criterion under contingencies. No guaranteed common mapping of discretionary outcomes. | Kalshi p2 Contingencies; US pp3–4 Source agencies/Clarifications | MATERIAL UNRESOLVED |
| Fees and capital | Fee profiles remain unapproved; no exact account applicability or cash-release guarantees established. | Repository fee packets; venue fee documents | NOT REVIEWED |

## Recommended operator disposition

**UNRESOLVED — NOT APPROVED FOR STRICT ARBITRAGE.** Do not mark `equivalent: true`; do not import a completed approval form. This is a review-aid finding, not a binding human attestation. A conservative operator may choose `REJECTED` for strict arbitrage on present evidence, but should not interpret this as the venue ruling on hypothetical scenarios.

## Questions to send to both venues

For the exact December 9, 2026 instrument: (1) If the original meeting is postponed or canceled then formally rescheduled, is settlement determined at the replacement meeting or is no-change automatically deemed YES? (2) If the meeting is canceled without replacement but the upper bound changes due to an emergency decision, what is settlement? (3) If only one bound of the target range changes, what is the no-change outcome? (4) Which of the market-specific description, product terms, and rulebook governs in each case? Request written replies referencing the exact ticker/slug.

## Before any approval or economic run

Re-fetch both market definitions and PDFs, compare source hashes, validate contract-specific precedence, obtain written clarifications, finish fees and mechanics reviews, and collect fresh contemporaneous executable books. If any material payout branch remains unknown, retain `UNRESOLVED` or reject this pair and continue scanning other products.
