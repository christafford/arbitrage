# Live fee capture and operator review (M5A C)

`research fees-capture` archives public evidence for **one exact instrument and
side**, then exports an **unapproved** profile. It does not approve a contract
pair, verify the operator's account, create orders, or authorize trading.
The existing conservative fee engine is unchanged. Capture is read-only toward
venues and writes a local audit archive under the normal single-writer lock.

## Capture and inspect

Use the same database that holds the instrument registry and intended research
session. First choose a current instrument from discovery; example placeholders
below are not real markets or approved pair suggestions.

```bash
predarb research fees-capture kalshi REAL_TICKER --side YES \
  --db data/research.sqlite3 --output data/fee-review-kalshi-new
predarb research fees-capture polymarket_us REAL_SLUG --side YES \
  --db data/research.sqlite3 --output data/fee-review-us-new
```

Every output directory must be new. A successful command exits 0 with
`NEEDS_OPERATOR_REVIEW`, **not** an approved fee. `review.json` contains source
URLs, UTC receipt times, SHA-256 hashes, derived parameters, the next known
change and unresolved questions. `source-*.txt` preserves source bytes, including
JSON responses and official Markdown documents. `profile.json` deliberately has
blank reviewer, effective-from, account/settlement and review fields, with
`applicability_reviewed=false`. In particular, missing settlement costs never
become zero, and account balance precision is not guessed.

Kalshi captures market → event → series identity, the series fee type/multiplier,
optional paired event overrides, future series changes and event fee history,
plus the official series-model and rounding documentation. Present market fee
waivers, unsupported models and partial event histories are rejected. Event
history is bounded to one 1,000-row page; a nonempty cursor is an explicit failure,
not assumed completion. An event change clearing an override still caps validity.

Polymarket US captures the exact public gateway market and official US fee page.
The documented numeric `feeCoefficient` must match the supported standard
`0.0695` or Table Tennis `0.10` model. This numeric match is a proposed model,
not proof of category or single-contract applicability. The operator must check
that scope and any exceptions; combo fees remain unsupported. `comboEnabled` is
not interpreted as proof that an individual contract is a combo. Missing/null,
string, negative, unknown or zero US coefficients fail closed. An explicit numeric
zero Kalshi multiplier is retained as observed, never supplied as a default.

To re-export a stored capture without any network access or database mutation:

```bash
predarb research fees-review CAPTURE_ID --db data/research.sqlite3 \
  --output data/fee-review-copy-new
```

This reader can run beside the writer. It rechecks source hashes, identity,
schema, expiry and supersession at the current time. It is not a refresh and
cannot revive expired evidence. Original expired captures remain in SQLite for
audit; deterministic historical replay is exercised by offline fixture tests.

## Complete the human review

Review all captured sources against the exact instrument, category and side.
Fill in the blank profile fields described in [ECONOMICS.md](ECONOMICS.md):

- Your `operator` and `version`; `instrument_scope`, `category_reviewed`,
  `schedule_reviewed` and `scheduled_changes_checked` explanations. Include
  effective schedule dates, exceptions and why the proposed model applies.
- Explicit `settlement_fee_per_contract`. Additional account/FCM charges are
  unsupported: use `account_fee_extras_checked=NONE_CONFIRMED` only after checking.
- Kalshi `balance_precision` from actual direct/non-direct account status:
  `0.0001` or `0.01`. Public market data cannot establish account status.
- `effective_from` and the bounded end/expiry timestamps. Import requires
  `effective_from <= now < expires_at <= effective_until <= capture deadline`.
- For Kalshi, download the [official schedule PDF](https://kalshi.com/docs/kalshi-fee-schedule.pdf)
  and fill in its `documents` entry with local `path` and actual UTC `retrieved_at`.
  Relative paths resolve beside the profile. This supplemental file is explicitly
  operator supplied, not an authenticated fetch by the tool. The importer rejects
  missing/empty/oversized files and non-PDF error pages. A `%PDF-` signature check
  is not semantic PDF validation: the human must read the document.

Kalshi's PDF endpoint returned HTTP 429 from the agent's HTTP client during C
verification; no restriction was bypassed. The operator supplied
`/home/chris/kalshi-fee-schedule.pdf`. Its preserved copy is attached to the local
sample packet. Its file modification time is recorded separately, **not** asserted
to be the retrieval time; that field remains for the operator to confirm. The
readable July 7, 2026 PDF matches the general model and states no settlement fee,
but the sample draft still requires an explicit account/instrument review.

After completing the review, set `applicability_reviewed=true` and explicitly import:

```bash
predarb research fees-import data/fee-review-kalshi-new/profile.json \
  --db data/research.sqlite3 --attest-reviewed-fees
```

The instrument must already exist in the live registry. Fees do not create it or
approve a pair. Import checks the capture ID/digest, exact identity, model and
multiplier and copies immutable captured source bytes into the approved profile's
evidence. Operator-supplied documents are archived before format/freshness checks.
The scanner rechecks capture integrity/validity at use time. Legacy live profiles
without capture references are rejected; hypothetical M4 replay profiles retain
their existing format and isolation. SQLite schema remains 7: this work reuses
`fee_imports`, `fee_documents`, `fee_profiles` and `raw_observations`.

## Expiry, refresh and failures

Validity is at most **24 hours from capture start and every source receipt** and
ends earlier at a known scheduled change. The supplemental PDF also limits the
imported profile's expiry to 24 hours after its declared retrieval. Neither the
scanner nor this tool interprets unstructured prose as an automatically approved
schedule. A new schedule document must be reviewed even if the numeric API fee
has not changed. Discounts and account tier rebates are not assumed.

Starting a capture for the same venue/instrument/side immediately supersedes its
older approval, **before network I/O**. Network failure, schema rejection or
interruption leaves that identity blocked. A newer unsuccessful capture also
prevents reimporting a profile tied to an older successful capture. Complete a
fresh capture and human review to recover. A profile import that fails with a
parseable identity likewise blocks fallback. Other instruments/sides retain
only their own bounded validity; capture is not a venue-wide refresh.

Transport is public GET-only, fixed US origins/exact documentation URLs, TLS,
no redirects, bounded bytes, timeouts and existing rate/backoff limits. JSON is
archived before parsing and uses exact decimals. HTTP errors remain archived.
A partial capture cannot produce an approvable profile. Return code 1 reports
errors; interrupted CLI operations return 130. Original bytes remain in the
archive. Review/export filesystem errors do not undo captures; use `fees-review`
with a new directory once the filesystem issue is resolved.

A 24-hour review window is not proof that fees cannot change sooner. This workflow
requires regular source captures and operator reviews during a multiweek run;
there is no automatic fee-approval renewal. Fee validity alone does not satisfy
pair equivalence, fresh books, collateral/settlement mechanics, or sustained-run
acceptance. See [measured C evidence and remaining gaps](M5C_RESULTS.md).
