# December Fed hold — operator review packet

**Decision pending.** This worksheet is source-bound research assistance, not an
approval form accepted by the registry. Both instruments were open when rechecked
at **2026-11-01 17:12 UTC**. The supported research route is cash-funded **Kalshi
long NO + Polymarket US long YES**. Trading remains unauthorized.

## Read these four sources

| Source | Review focus |
| --- | --- |
| [Kalshi market definition](https://external-api.kalshi.com/trade-api/v2/markets/KXFEDDECISION-26DEC-H0) | `rules_primary` and `rules_secondary`, particularly the scheduled-date cancellation language |
| [Kalshi FEDDECISION terms](https://assets.kalshi.com/contract_terms/FEDDECISION.pdf) | Page 1: underlying and payout; page 2: expiration, revisions and contingencies |
| [US market definition](https://gateway.polymarket.us/v1/market/slug/rdc-usfed-fomc-2026-12-09-nochng) | Upper-bound selection and rounding language |
| [US RDC terms](https://www.polymarketexchange.com/files/products/PMUS%20-%20RDC%20-%20%282026.04.06%29.pdf) | Pages 2–4: underlying, special circumstances, source hierarchy and review |

The [source manifest](evidence/M5N_FED_HOLD_REVIEW_SOURCES.json) binds exact original
files to URLs, receipt times and SHA-256 hashes. The [blank worksheet](evidence/M5N_FED_HOLD_REVIEW.json)
copies those hashes; fresh source changes require a new review. Complete local
copies are under `data/m5n/fed-hold-review/`. Confirm RDC's applicability and the
precedence of market-specific language over generic terms before judging payouts.

## Scenario worksheet

Let `K` and `U` be each venue's YES payout in integer cents. For the supported
route, combined settlement is **100 − K + U**. The examples below are hypothetical
interpretations, not observed settlements or approved equivalence labels.

| Scenario | Candidate interpretation | Reviewer task |
| --- | --- | --- |
| Ordinary unchanged range | K=100, U=100; combined 100 | Confirm the same December meeting and rate baseline |
| Ordinary change to both bounds | K=0, U=0; combined 100 | Confirm each selects the same event decision |
| Outright cancellation | Both terms provide hold-YES treatment | Confirm this branch's definition and precedence |
| Original date canceled; replacement meeting changes rates | If K=100 but U=0, combined settlement is **0** | Resolve cancellation versus postponement classifications; this downside is conditional |
| No meeting, no replacement, but intervening rate action | UNKNOWN | Reconcile cancellation and effective-rate fallback branches |
| Lower bound changes while upper bound stays fixed | US hold wording selects the upper bound; K needs interpretation | Resolve range versus upper-bound wording; do not mislabel possible extra payout as downside |
| Correction, source outage, successor benchmark or disputed outcome | UNKNOWN | Determine applicable data vintage, source substitution and review outcomes on both venues |

The Kalshi terms exclude post-expiration revisions and retain discretionary
contingencies. US terms distinguish delayed, canceled and no-meeting cases and
include source-substitution and review provisions. These differences require
source-bound resolution; shared ordinary outcomes alone do not complete review.

## Timing, fees and mechanics still pending

Current API clocks are separate from cash release: Kalshi cutoff **December 9,
18:59 UTC**, expected expiration **19:05 UTC**, latest expiration **March 10,
2027, 19:01 UTC**; US administrative end **December 24, 04:00 UTC**. Generic
product clocks differ and need precedence review. Actual reusable cash timing
and review delays remain UNKNOWN.

The existing [Kalshi fee packet](../data/m5n/contracts/fed-hold-kalshi-fees/review.json)
and [US fee packet](../data/m5n/contracts/fed-hold-polymarket_us-fees/review.json)
are unapproved. The refreshed US definition advertises coefficient 0.0695; that
does not establish account applicability. Independently review fees, cash funding,
fractional payout rules and settlement costs. No collateral offsets or borrowed
funding are supported. Fresh synchronized Fed books are also still required.

## Record your finding

For each unresolved scenario, record a conclusion, exact source/page/field,
reasoning and any written clarification. Leave uncertain cases UNKNOWN. The
worksheet's reviewer, decision, reviewed-at and all scenario decisions start null.
Defer or reject strict classification if material branches remain unresolved.
Only a completed review should proceed through the existing [registry workflow](PAIR_REVIEW.md).

Suggested clarification to prepare for each venue: “For this exact market, if the
December 9 meeting is canceled and replaced by a later meeting, which rule applies?
What if no replacement is designated and rates change before expiration? Which
published terms take precedence?” This is a draft; no inquiry has been sent.
