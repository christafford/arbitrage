# Human pair review — M2

The registry records an operator's settlement-equivalence decision. It does not
place orders, normalize books, prove fills or authorize trading. Suggestions from
metadata or an LLM always start `UNVERIFIED`. Only a human should invoke approval
for real instruments after reviewing the official source material.

## Collect and archive evidence

Run both collectors as described in the README. Select the Kalshi market for
detail capture (`--book TICKER` or `--books N`) so its event/series sources and
contract-term URLs are included. M2 automatically versions contract evidence;
existing M1 archives are migrated and backfilled. Quote/volume/update-time changes
do not create a contract revision. Unknown additional metadata is fingerprinted
conservatively: changes may require re-review even if later found immaterial.

Import the original official contract/rule file **and** its exact UTF-8 text or
faithful extraction. Record the actual source retrieval time, not today's time for
an old file. Preserve all applicable clarifications, cancellation/void conditions,
resolution sources, definitions, thresholds and revision policies. Repeat for each
applicable document on each venue:

```bash
predarb pairs document --db data/research.sqlite3 \
  --venue kalshi --source-id KALSHI_TICKER \
  --url https://assets.kalshi.com/contract_terms/ACTUAL_CONTRACT.pdf \
  --source-file data/kalshi-original.pdf --text-file data/kalshi-exact-text.txt \
  --retrieved-at ACTUAL_ISO_UTC_TIMESTAMP --operator YOUR_NAME
predarb pairs document --db data/research.sqlite3 \
  --venue polymarket_us --source-id US_MARKET_SLUG \
  --url https://polymarket.us/ACTUAL_OFFICIAL_SOURCE \
  --source-file data/us-original.html --text-file data/us-exact-text.txt \
  --retrieved-at ACTUAL_ISO_UTC_TIMESTAMP --operator YOUR_NAME
```

Replace the uppercase placeholders with actual values. These examples do not
identify a verified equivalent pair or an actual Polymarket rule URL.

Each source and extracted text file must contain 1..2,000,000 bytes. Raw source
bytes and text bytes have independent SHA-256 hashes and immutable versions.
Imports use operator-supplied files: the registry does **not** independently fetch
them, authenticate the declared URL, or verify PDF extraction fidelity. Review
output marks this provenance explicitly. The URL must be HTTPS and belong to the
corresponding US venue (Kalshi domains/official public-document bucket, or US
Polymarket domains). International Polymarket sources are rejected. No credentials
or remote writes are involved. Provider data rights still apply.

## Suggest, propose and inspect

```bash
predarb pairs candidates --db data/research.sqlite3 --limit 20
predarb pairs propose --db data/research.sqlite3 \
  --kalshi KALSHI_TICKER --polymarket-us US_MARKET_SLUG --operator YOUR_NAME
predarb pairs review 1 --db data/research.sqlite3 --template-output data/pair-1-review.json
```

`candidates` compares title words from at most 500 available instruments per venue
and returns at most 100 suggestions. Its integer overlap score is a search aid,
not equivalence confidence; even a perfect title match is `UNVERIFIED`. Suggestions
do not write proposals or decisions. A manual proposal can use any collected IDs
from the two supported US venues. Duplicate current proposals/approvals fail.

`review` shows exact contract evidence, raw-observation provenance, event/series
sources, imported resolution text and both current and decision evidence hashes.
It writes a blank form only when `--template-output` is given and never overwrites
an existing file. The form starts with no reviewer, no expiry, false comparisons,
no leg mapping and no settlement scenarios. Viewing a form does not attest review.

## Complete the human review

A human must fill the JSON form. Keep its `pair_id`, `hypothetical` marker and
current `evidence_sha256`. Set a named `reviewer`, an explanation in `reason`,
`human_reviewed: true`, and an explicit UTC-aware `expires_at`.

Every comparison requires `equivalent: true` and a substantive `rationale`:

- Proposition and event definition, including the precise subject/event.
- Timezones, cutoffs and evaluation windows.
- Resolution sources and fallback sources.
- Threshold inclusivity, revisions and final-versus-first reports.
- Suspension, cancellation and void treatment.
- Payout semantics and settlement timing.

`comparisons` uses the keys `proposition`, `event_definition`, `timezone_cutoffs`,
`resolution_sources`, `thresholds_revisions`, `suspension_void_cancellation`,
`payout_semantics` and `settlement_timing`. An unresolved or different comparison
blocks approval; write a rejection reason instead of asserting equivalence.

`outcome_mapping` maps Kalshi `YES` and `NO` to Polymarket US `YES`/`NO`. It must be
bijective. `legs` explicitly selects `YES` or `NO` for each venue; those selected
legs must be complementary under the mapping. Same-proposition examples use
`{"YES":"YES","NO":"NO"}` with Kalshi YES / US NO. Inverse propositions need a
separately reviewed reversed mapping, not an inferred title negation. These are
abstract payoff labels, not an implementation of buy/short mechanics.

`settlement_scenarios` must cover `YES`, `NO`, `VOID`, `CANCELLED`, `SUSPENDED` and
`SOURCE_REVISION` (up to 30 entries for variants). Each object includes:

```json
{
  "case": "VOID",
  "condition": "Exact human-reviewed condition and source reference",
  "kalshi_payout": "0.50",
  "polymarket_us_payout": "0.50",
  "kalshi_settlement_at": "2030-07-04T12:00:00Z",
  "polymarket_us_settlement_at": "2030-07-04T12:00:00Z"
}
```

That is a **hypothetical format example**; it does not describe either venue's
actual void policy. Payouts must be exact decimal strings in [0,1], at most eight
decimal places, and sum to exactly $1 in each declared scenario. Normal YES/NO
payouts must agree with the outcome mapping and selected legs. Both settlement
times must be explicit future timestamps. Unknown, cost-dependent or variable
fair-price/refund payouts cannot be replaced with 0.50: leave the pair unverified
or reject it. The human must establish that all applicable cases are covered;
software cannot prove that the submitted scenarios exhaust the legal contract.

Approval requires fresh catalogue, supplemental and document evidence (24-hour
maximum age); expiry cannot outlive the earliest evidence freshness deadline or
24 hours from the decision. An expired cutoff, missing rule text, closed or
unavailable instrument, or a failed latest source run blocks live review approval.
Refreshing unchanged source bytes does not extend an existing decision's expiry.

Only after completing the human review:

```bash
predarb pairs approve 1 --db data/research.sqlite3 \
  --review-file data/pair-1-review.json --human-review
```

Both the form attestation and CLI flag are required. The operator name and human
attestation are local declarations, not authenticated identity or proof that an
LLM did not fill the form. This is a trusted local operator workflow, not an
access-control boundary. An LLM may suggest questions to review; it must not approve
real equivalence on the operator's behalf.

## Reject, revoke, expire and audit

```bash
predarb pairs reject 1 --db data/research.sqlite3 --operator YOUR_NAME --reason 'Different final-report policy'
predarb pairs revoke 2 --db data/research.sqlite3 --operator YOUR_NAME --reason 'Withdrawn pending clarification'
predarb pairs list --db data/research.sqlite3
predarb pairs audit --db data/research.sqlite3 --pair-id 2
```

Rejection applies to an unverified proposal; revocation applies to a current
proposal or approval. Both require identity and reason. Terminal decisions remain
terminal: restoring old rule text or refreshing data never resurrects an approval.
A new proposal and human review are required after revocation, rejection,
invalidation or expiry. Inspect the old pair first to evaluate an elapsed expiry.

Changed market terms, collected Kalshi event/series evidence, or imported document
bytes/text invalidate current approvals immediately. A failed/interrupted venue
collection invalidates all current cross-venue approvals conservatively, including
when schema drift prevents saving its first page. Expiry, stale/missing evidence
and cutoff checks run on `review`, `list`, approval checks and `predarb report`;
there is no background expiry daemon. Future consumers must call these validity
checks, never trust a cached `pairs.status` column by itself.

`pair_audit` is append-only under ordinary SQLite writes and records proposals,
imports, approvals with full evidence/form, rejections, revocations and system
invalidation/expiry. Rule, supplemental and document versions are immutable.
These guards do not protect against a privileged database owner dropping triggers
or editing files. No failed approval attempt is represented as a successful decision.

## Reproduce the offline acceptance demo

From the repository root, using a new empty database path:

```bash
.venv/bin/python scripts/m2_demo.py --db data/my-m2-demo.sqlite3
```

The script exercises the real CLI with explicitly hypothetical fixtures, including
simulated review attestations. It rejects identical titles with different report
semantics, approves/revokes a hypothetical pair, then invalidates a fresh approval
after a document amendment. It writes an exact CLI trace and review forms beside
the database. `pairs load-example` refuses a nonempty/live database; reserved
`HYPOTHETICAL-` identifiers and flags keep synthetic and live evidence separate.
No real pair is approved by the script or this milestone's validation.
