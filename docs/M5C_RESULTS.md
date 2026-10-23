# M5A Workstream C — fee capture and review

Implemented and verified on **2026-10-23 UTC**. C's tooling and live-source capture
checks passed. **Human fee applicability approval is still pending**, so C's
operator acceptance and overall M5A remain incomplete. D/E and M6 were not
implemented. No live fee profile, real pair decision, order or service activation
was created.

## What changed

- Public fee evidence capture for an exact venue/instrument/side, with raw archival,
  official source hashes and an unapproved review packet.
- Kalshi market/event/series identity, numeric fees, event overrides and both
  scheduled-change sources; US numeric per-market coefficient and official schedule.
- Explicit account/category/schedule review fields, required Kalshi PDF supplement,
  capture-bound imports and scanner use-time checks. Unknown fees never become zero.
- At most 24-hour validity, earlier scheduled-change cutoff, immutable evidence and
  failed/interrupted refresh invalidation before network I/O. Old capture reuse
  cannot restore a superseded approval.
- Offline re-export/revalidation, fixed documentation URLs, bounded public GETs,
  deterministic fixtures, tests and [operator instructions](FEE_REVIEW.md).

The existing exact fee arithmetic and hypothetical replay format are unchanged.
No schema migration was needed: schema 7's existing fee/raw tables retain the new
versioned evidence. Legacy live profiles without capture references fail closed.

## Executed verification

`.venv/bin/python -m unittest discover -s tests -v` executed **250 tests**, all
passing. [Full named test output](evidence/M5C_TESTS.txt) records exactly what ran.
This includes 19 new tests in `tests/test_fee_capture.py`: both real source replays,
missing/malformed fee fields, invalid prices, identity drift, event overrides,
scheduled changes and clearing overrides, partial event history, time boundaries,
source corruption, hypothetical human imports, import/profile mismatch, failed and
interrupted refreshes, PDF handling, bounded document transport, immutable exports
and CLI behavior. Existing economics tests continue to cover depth/partial-liquidity
and conservative fee rounding. No actual operator account terms were tested.

Executed smoke commands (all exit 0):

```bash
.venv/bin/predarb research fees-capture kalshi KXBTCD-26OCT2317-T83499.99 \
  --side YES --db data/m5c-live.sqlite3 --output data/m5c-review-kalshi
.venv/bin/predarb research fees-capture polymarket_us tec-mlb-champ-2026-09-27-mil \
  --side YES --db data/m5c-us-live.sqlite3 --output data/m5c-review-us
.venv/bin/predarb research fees-review 1 --db data/m5c-live.sqlite3 \
  --output data/m5c-review-kalshi-offline
.venv/bin/predarb research fees-review 1 --db data/m5c-us-live.sqlite3 \
  --output data/m5c-review-us-offline
.venv/bin/predarb demo --db data/m5c-smoke.sqlite3
.venv/bin/predarb report --db data/m5c-smoke.sqlite3
```

These paths already exist; use new output directories when repeating commands.
Both live packets reported `NEEDS_OPERATOR_REVIEW`, with **zero fee profiles and
zero approved pairs** in their isolated archives. [Machine-readable live evidence](evidence/M5C_LIVE_VALIDATION.json)
and [official source checks](evidence/M5C_API_CHECKS.json) preserve the details.

| Live sample | Observed fee data | Raw responses | Capture start (UTC) |
| --- | --- | --- | --- |
| Kalshi KXBTCD-26OCT2317-T83499.99 | quadratic, multiplier 1; no event override or returned changes | 7 | 2026-10-23 21:09:50 |
| US tec-mlb-champ-2026-09-27-mil | coefficient 0.0695, proposed standard model | 2 | 2026-10-23 21:09:59 |

No price/size/book comparison was made from those captures. They are unrelated
technical samples, not an equivalent pair; the Kalshi market had already closed.
No scheduled changes were observed live. Nonempty override/change paths were
verified using explicitly hypothetical mutations of the saved public fixtures.

## Supplied PDF and remaining operator work

The HTTP client received **429** for the official Kalshi PDF. The operator then
supplied `/home/chris/kalshi-fee-schedule.pdf`; `file` and `pdftotext -layout` verified
that it was a readable 12-page PDF. Its SHA-256 is
`c326a69f596a11e8f8be2620402d39a8d4823920c21cc97c93a114d862699601`.
It states effective July 7, 2026, gives the general 0.07 quadratic multiplier model
and states no settlement fee. Original bytes were preserved beside the local
Kalshi review packet and in `data/m5c-sources/`; the supplied original is unchanged.
The browser/file clock is recorded as filesystem evidence, not invented as a
verified venue retrieval timestamp. The operator must confirm actual retrieval
when completing the draft.

Local review drafts are `data/m5c-review-kalshi/profile.json` (PDF attached) and
`data/m5c-review-us/profile.json`. Both are deliberately unapproved. They expire
no later than October 24 at 21:09:50 and 21:09:59 UTC respectively, and are examples
for reviewing the workflow. Actual research needs fresh captures for the intended
real instruments in the research registry, human applicability decisions and
fresh books. A new profile does not approve a pair.

Outstanding: operator identity, exact category/scope and schedule applicability,
account precision/extra charges, explicit settlement costs, actual live profile
imports, and real pair equivalence review. A multiweek run will need repeated
captures and human fee renewals; no unattended approval renewal was added.
Workstream D settlement/collateral verification and E readiness reporting remain
unstarted. B's pre-rollout stream compatibility still expires October 29 UTC;
M4/M5 sustained-run evidence remains pending.
