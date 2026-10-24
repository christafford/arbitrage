# Fed-cut human review — 2026-10-24 UTC

Kalshi `KXFEDCUT-31DEC28-31DEC26` and Polymarket US
`cbpac-usfed-2026-cut` are **REJECTED_FOR_ARBITRAGE** under the operator's
requirement for perfectly equivalent definitions. Main registry pair **1** is
terminally `REJECTED`, with the requested disposition in its reason. No human
equivalence attestation, fee/mechanics approval or trading authorization was made.
This completes a requested review, not a new roadmap milestone.

The local, self-contained evidence packet is
[`data/review-packets/fedcut-20261024/`](../data/review-packets/fedcut-20261024/README.md).
Its [comparison](../data/review-packets/fedcut-20261024/COMPARISON.md) and
[alternative search](../data/review-packets/fedcut-20261024/ALTERNATIVES.md) provide
the operator-readable findings and links to complete official evidence.
The packet and its ZIP archive are local research artifacts ignored by Git;
preserve them with research-data backups. This tracked summary and verification
record do not replace those source archives.

## Findings

Kalshi requires an announcement after issuance; the current market records
September 23, 2026 creation/opening. The complete US CBPAC product terms also
require an announcement after **their own** contract issuance. Earlier 2026 cuts
can therefore count for US only if announced after its own issuance; the contract
must not be described as covering all of 2026. US metadata records July 2, while
the certification says listing no earlier than July 6. The exact legal issuance
instant and a common September 23 window were not established.
Sources: [Kalshi exact market](https://external-api.kalshi.com/trade-api/v2/markets/KXFEDCUT-31DEC28-31DEC26),
[US exact market](https://gateway.polymarket.us/v1/market/slug/cbpac-usfed-2026-cut),
[US CBPAC terms, p.3](https://www.polymarketexchange.com/files/products/PMUS%20-%20CBPAC%20-%20%282026.07.01%29.pdf).

Both full definitions use announcement timing regardless of effective date.
There is no established announcement-versus-effective-date mismatch. US explicitly
uses the target range's upper bound; the captured Kalshi definition does not
resolve every asymmetric range-change scenario. Both stated event deadlines are
December 31, 2026 at 11:59 PM ET. Later administrative dates do not extend that
deadline; inconsistent Kalshi expected/latest expiration fields remain flagged.

Kalshi YES/NO and US YES have cash-funded long routes in this project. US NO is a
short of the same instrument, not a separately purchased NO asset. Official US
documentation specifies $1 gross collateral per contract, sale proceeds credited,
and buying-power reduction of $1 minus sale price. That short route remains
unsupported by the project. No account-specific collateral or fee applicability
was approved. Source: [US collateral documentation](https://docs.polymarket.us/market-structure/collateral-and-margin).

No perfectly equivalent replacement was established among 22 freshly fetched
US rate instruments and 533 open markets across 11 freshly traversed Kalshi
series. Alternatives differed or remained uncertain on observation windows,
unusual-size rounding, postponement/cancellation, or strict versus inclusive
thresholds. This bounded search is not proof that no equivalent listing exists
anywhere. The meeting-specific no-change contracts remain an unverified research
lead requiring official clarification.

## Evidence and validation

The packet preserves 68 source captures: 65 HTTP 200 responses, two redirects,
and one failed Kalshi rulebook-page request (429). Complete exact-market API
responses and contract-specific terms were obtained. The full Kalshi exchange
rulebook was not obtained, and binding US product attribution/exact legal issuance
remain explicitly unresolved. Every original-byte hash was verified.

Ten complete current documents were imported immutably into each database before
the pair was proposed and rejected. Both databases still have zero approved pairs,
zero fee profiles and zero research sessions. Main catalogue metadata was not
rewritten; fresh scoped captures reside in the packet database. Raw source and
decision hashes are preserved in the decision and registry audit records.

Executed `.venv/bin/python -m unittest discover -s tests -v`: **291 tests passed**.
Exact test names/results are in [the test log](evidence/FEDCUT_REVIEW_TESTS.txt).
CLI smoke checks `pairs review 1` and `pairs audit --pair-id 1` exited 0;
`research readiness --format json` exited 2 with `BLOCKED`, zero ready pairs and
`trading_authorized=false`. Both SQLite quick checks passed. See
[the validation record](evidence/FEDCUT_REVIEW_VALIDATION.json) for exact commands
and source/decision hashes. No production code or schema was changed.
