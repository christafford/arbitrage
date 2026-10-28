# Charlotte–Detroit research review — October 28, 2026

**Status: UNVERIFIED. Do not advance this pair to economics on the current
evidence.** The ordinary game identity matches, but exceptional payouts are not
established as complementary. This is an assistant-prepared evidence comparison,
not a human equivalence decision or legal determination.

This is a bounded use of the existing M2/M3 review workflow. No application code,
approval policy, fee profile, research session, or execution functionality changed.
The full discovery archive was not modified by this capture.

## Captured evidence

Local packet: `data/charlotte-detroit-review-20261028/`.
The [verification manifest](evidence/CHARLOTTE_DETROIT_REVIEW.json) records source
hashes, response provenance, exact validation results, and local artifact hashes.

- Kalshi: `KXNBAGAME-26OCT28CHADET-CHA`, Charlotte wins.
- Polymarket US: `aec-nba-cha-det-2026-10-28`, Charlotte is the long side.
- Scheduled date in both rules: October 28. US specifies 23:00 UTC / 7 PM ET.
  Kalshi's occurrence field is not treated as its scheduled start time.
- Both scoped traversals completed at approximately **00:42 UTC October 28**:
  two Kalshi markets, one US market, one selected book per venue, nine archived
  HTTP responses. No credentials or embedding service were used.
- `evidence.sqlite3` contains raw responses, event/series enrichment, eight
  imported source documents, and **proposal 1, UNVERIFIED**. The proposal and
  imports identify `codex-research-assistant`, not the human operator.
- `pair-evidence.json` and `human-review-blank.json` contain the source bundle
  and untouched approval template. `human_reviewed` remains false; all comparison
  attestations remain false; no legs or settlement payouts were selected.

## Settlement comparison

| Case | Evidence and implication |
| --- | --- |
| Ordinary completed game | Both identify Charlotte winning this game. The Kalshi full-game definition includes overtime by default; US explicitly includes it. This supports identity, not approval. |
| Postponement | Kalshi uses a 48-hour commencement/resumption window. The US market description uses two days, but its general sports FAQ discusses rescheduling before expiration. US Rulebook §1.5 gives contract terms priority over product specifications and general rules. Verify the complete applicable terms; do not replace the market clause with the FAQ. |
| Cancellation or incomplete suspended game | Kalshi can use an exchange-determined fair price; US can use its own last fair market price. There is no evidence these prices coincide. Unknown payouts cannot be entered as 0.50 or assumed to total $1 across venues. This alone prevents the current fully hedged research model from admitting the pair. |
| Pre-game forfeit | Kalshi's full terms expressly prescribe fair-price settlement. The US sports FAQ says the awarded participant wins without the same pre-game distinction. Applicability needs clarification; do not assume a matching binary payout. |
| Source disputes and revisions | Kalshi specifies first official results, fallback sources, and a post-expiration revision limit. US documents fallback sources and an outcome-review process. These have not been established equivalent. |
| Cash availability | API deadlines differ: Kalshi October 30 at 23:00 UTC; US November 11 at 23:00 UTC. Neither field proves the time cash becomes reusable. No settlement-time or account-mechanics review was attested. |

Sources: [Kalshi contract terms](https://assets.kalshi.com/contract_terms/BASKETBALLGAMEWIN.pdf),
[US market detail](https://gateway.polymarket.us/v1/market/slug/aec-nba-cha-det-2026-10-28),
[US sports FAQ](https://docs.polymarket.us/faqs/sports-faqs),
[US Rulebook](https://polymarketexchange.com/files/legal/Polymarket%20US%20Rulebook%20(2026.09.30).pdf).
Original PDFs/Markdown and extracted PDF text are in the local packet, with URL,
UTC receipt time, and SHA-256 manifests. PDF extraction fidelity and applicability
remain human-review tasks. No claim is made that all later clarifications were captured.

## Book observations, not an economic comparison

The following are historical captures, not current executable quotes. No combined
cost, fee-adjusted edge, position size, or profit was evaluated.

| Book | Receipt UTC | Best normalized YES ask | Best normalized NO representation | At-capture quality |
| --- | --- | --- | --- | --- |
| Kalshi | 00:42:01.719019 | $0.3100, 30,774.08 contracts | $0.7000, 18.56 contracts | Rejected: UNKNOWN_SOURCE_TIME |
| US | 00:42:14.599079 | $0.3100, 36,204.7600 contracts | $0.7000, 449.3600 contracts | Passed at capture; source time 00:41:56.435930936 |

US NO is synthetic short-YES exposure and is unsupported by the cash-funded-long
research evaluator. Both snapshots became stale during review. The pair book
gate returned exit **2**, with comparison readiness false. No receipt or metadata
timestamp substituted for Kalshi's missing source timestamp.

## Verification and next action

- `python -m unittest discover -s tests -v`: **342 tests passed** in 11.397 seconds;
  exact names/results are in the packet's `unittest.log`.
- Both live collector smoke commands completed successfully; historical book
  inspection accepted the US snapshot and rejected Kalshi's missing source clock.
- All nine exact public response bodies were hash-checked and replayed through
  the existing venue schema validators. `public-response-fixture.json` is actual
  public evidence, explicitly not hypothetical; no new fixture values were invented.
- Current official embedded schemas are Kalshi **3.35.0** and US **1.0.0**.
  Captures retain the existing local validation contracts
  `kalshi-3.34.0/m1-v1` and `polymarket-us-marketservice-1.0.0/m1-v1`;
  the observed consumed fields passed those validators. This is not a claim of
  complete upstream-schema compatibility. Database schema remains 8.

Review the exceptional settlement differences before considering any approval.
On this evidence, keep the pair excluded from economics. A favorable ordinary-game
match or price difference would not resolve the fair-price mismatch. A human may
record a rejection after review; the assistant has left the proposal UNVERIFIED.
No approval command was run. M4/M5 sustained-run acceptance remains pending.

To inspect the saved proposal without starting another collection:

```bash
. .venv/bin/activate
predarb pairs review 1 --db data/charlotte-detroit-review-20261028/evidence.sqlite3
```

Executed collection smoke commands (both exit 0):

```bash
predarb collect-kalshi --db data/charlotte-detroit-review-20261028/evidence.sqlite3 \
  --event-ticker KXNBAGAME-26OCT28CHADET --limit 20 --max-pages 3 \
  --book KXNBAGAME-26OCT28CHADET-CHA
predarb collect-polymarket-us --db data/charlotte-detroit-review-20261028/evidence.sqlite3 \
  --slug aec-nba-cha-det-2026-10-28 --limit 20 --max-pages 3 \
  --book aec-nba-cha-det-2026-10-28
```
