# Economics and recording (M4)

M4 adds a read-only research pipeline. It records modeled results and rejection
reasons, never orders or fills. Live evidence stays `UNVERIFIED`; every result
sets `trading_authorized=false`. The milestone's actual 30-day observation and
audit remain pending; see [results](M4_RESULTS.md).

## Start and resume

```bash
predarb research start --db data/research.sqlite3 \
  --policy examples/M4_RESEARCH_POLICY.json --interval 60
predarb research scan SESSION_ID --db data/research.sqlite3 --cycles 1
predarb research summary SESSION_ID --db data/research.sqlite3
predarb research csv SESSION_ID --db data/research.sqlite3 --output data/results.csv
```

Replace `SESSION_ID` with the integer returned by `start`. The supplied policy
has **zero venue budgets**, a positive explicit reserve and a contract limit. It
cannot produce a funded allocation. Budget changes require a new session/policy;
they are hypothetical research allocations, not account balances, deposit
instructions or trading authority. Combined configured budgets cannot exceed
$10,000. Actual cumulative seed deposits are not tracked in this read-only phase.

The policy has exactly five decimal-string fields: `max_contracts`,
`kalshi_budget`, `polymarket_us_budget`, `reserve_per_leg`, `min_profit`.
The reserve is dollars per contract **on each leg**, must be positive, and is
deducted as a cost. Venue budgets constrain quote cost, fee bound and reserve
independently. No transfers or cross-venue netting are assumed.

`scan` evaluates local archived evidence by default. `--refresh` explicitly polls
the existing public GET collectors for currently approved pairs only, then
rechecks approval and book validity. Kalshi event scopes have a ten-page cap;
US slug scopes have a two-page cap. Failed refreshes retain raw evidence and
invalidate approval through the existing registry. No unreviewed pair reaches
economic evaluation. Unapproved/revoked/expired pairs are recorded as rejections.

Use one scanner process/writer. The interval accepts 1..3600 seconds. Every
invocation is bounded to at most 31 days, with a default of one cycle. For example,
`--cycles 43201` with a 60-second session interval schedules approximately 30 days,
subject to collection latency and interruption. Reusing the session ID resumes
recording after restart. This command does not launch a service or silently keep
running after it exits. No unattended 30-day run was launched for this milestone.

Sessions record a 30-day target. Cycle-start attempts are committed before
processing; finished summaries and full evaluation details commit together.
Interrupted attempts remain visible as unfinished, with source archives preserved.
No missing cycles are backfilled. A 200 MiB free-space guard stops new cycles;
at most 50 registered pairs and 10,000 common quantity increments per evaluation
are supported. Larger scopes/searches fail explicitly. Sleep/clock scheduling
uses ordinary runtime clocks; money calculations use `Decimal`.

## Fee evidence and scope

There are **no automatically installed live fee profiles**. Importing one needs
an existing registry instrument, exact market/side identity and explicit operator
attestation of applicability:

```bash
predarb research fees-import path/to/reviewed-profile.json \
  --db data/research.sqlite3 --attest-reviewed-fees
```

The profile is a JSON object with these fields:

| Field | Meaning |
| --- | --- |
| `schema` | `taker-fees/m4-v1` |
| `venue`, `source_id`, `side` | Exact `kalshi` or `polymarket_us` instrument and YES/NO side |
| `version` | Explicit operator version for the reviewed applicability |
| `kind` | Kalshi documented quadratic type; US `standard` or `table_tennis` |
| `multiplier` | Required exact decimal string for Kalshi; never defaulted |
| `balance_precision` | Required Kalshi account precision: `0.0001` or `0.01` |
| `settlement_fee_per_contract` | Required verified decimal-string amount; absence never means zero |
| `effective_from`, `effective_until`, `expires_at` | UTC-aware applicability window and local expiry |
| `hypothetical`, `applicability_reviewed`, `operator` | Boolean separation, explicit review attestation and reviewer name |
| `documents` | Hypothetical: 1..10 source objects. Live: up to 10 supplemental sources with official HTTPS `url`, local `path`, `retrieved_at`; Kalshi schedule PDF required |
| `capture_id`, `capture_sha256` | Live only: latest successful M5A C capture and exact source manifest digest |
| `schedule_reviewed`, `category_reviewed` | Live only: nonempty human review explanations |

Live profiles additionally require nonempty `instrument_scope` and
`scheduled_changes_checked` explanations, and `account_fee_extras_checked` exactly
`NONE_CONFIRMED`. Additional account/FCM charges are currently unsupported. Review
must cover the exact instrument/category, account precision, settlement fees,
exceptions and scheduled changes; a general fee document alone does not establish
market-specific applicability. M5A C checks Kalshi series parameters, event overrides and both scheduled-change
sources, plus the US market coefficient. Capture proposes a model; the operator
confirms applicability. Start with [the fee capture/review workflow](FEE_REVIEW.md). US category distinctions include Table Tennis; combos and
unknown/flat schedules are unsupported. See [official sources](API_SOURCES.md).

Document paths resolve against the profile's directory. Original configuration
bytes are archived before parsing; imported source bytes and SHA-256 hashes are
retained separately. URLs are restricted to official US venue hosts; hypothetical
profiles require `HYPOTHETICAL-` IDs, matching hypothetical registry evidence and
`example.invalid` sources. Captured public sources are fetched over fixed-origin HTTPS and hash-bound to the
profile. Supplemental file source fidelity and all applicability decisions remain
operator-declared; a source fetch is not account verification. Maximum profile/source
size is 2 MB each.

Expiry cannot exceed 24 hours after capture/review or any source retrieval, or a
known scheduled fee change. Starting a new live capture supersedes the prior fee
approval before network I/O, even if the capture fails or is interrupted. Import new
reviewed profiles to renew them; do not extend old rows. The newest profile wins,
including when future-effective or expired. A failed refresh with a parseable
market/side identity also blocks fallback to an earlier profile. Missing,
superseded, stale or mismatched profiles fail closed. A new profile never approves
a contract pair. Fees are not automatically refreshed from web pages in the scanner.

## Exact formulas and conservative bounds

The implemented taker formulas use `coefficient × quantity × p × (1-p)`:
Kalshi coefficient `0.07 × explicitly reviewed series multiplier`; US standard
`0.0695` or Table Tennis `0.10`, valid only from the verified October 19 schedule.
No maker incentives or account-tier rebates are credited.

`fill_fees` calculates documented rounding for a **declared hypothetical fill
partition** of one buy order. Kalshi rounds model fees to $0.000001, aligns the
cost/fee balance change to declared account precision and carries rounding
overpayment through the order's capped rebate accumulator. US rounds half-even
to cents per fill with the documented cumulative order cap.

Public book levels hide the number of resting orders. Economic evaluation
therefore uses `quote_fee_bound`, not a claim about the eventual exact commission.
Kalshi's bound splits a level into minimum supported count units and credits no
rebate. US uses the rounded cumulative exact fee cap. Verified per-contract
settlement fees are added separately. These may overstate the fee and reject an
otherwise profitable quote; no unknown fee is replaced with zero. Future actual
fills would require reconciliation, which is outside this milestone.

## Evaluation and ranking

The production path first rechecks M2's current human approval, evidence hash,
expiry, reviewed legs, fixed combined payout and settlement scenarios. M3 checks
raw provenance, full depth, state, grids, freshness, identity and source/receipt
skew. It then selects exact fee profiles. Kalshi REST still lacks a source book
timestamp, so REST-only live comparisons are rejected. M5A B provides the separately
validated bounded streaming path; no timestamp is substituted.

Only long-buy legs with supported capital mechanics are evaluated. US synthetic
NO from a short YES is refused with
`SYNTHETIC_US_NO_UNSUPPORTED_CAPITAL_MECHANICS`. No short/margin/collateral workflow
is implemented. Inverse propositions can still use two reviewed YES long legs.

The solver walks full ladders for every supported common lot up to the requested
limit, checking depth, each venue's independent budget, fee bound and reserve.
It selects the highest positive conservative total profit; ties favor lower
capital. It does not stop at a smaller quantity that fails because of rounding.
It reports quantities tested and whether the depth boundary was reached.

Profit is the reviewed $1 combined payout times quantity minus quote costs,
fee bounds and reserves. This calculation is conditional on simultaneous full
fills and holding to reviewed settlement, explicitly labeled hypothetical.
M5A D uses the latest explicitly reviewed cash-availability assumption per venue
for locked capital-days, rather than equating settlement with usable cash. Funding
components and each scenario's cash payout/date are recorded separately. Quantities
requiring unknown sub-cent payout rounding are skipped; the search continues at
larger lots. See [mechanics scope and operator review](SETTLEMENT_MECHANICS.md). Summary
ranking uses profit per capital-day, without annualization.

Ranked results are independent alternatives sharing books and hypothetical
budgets, **not an additive portfolio**. Repeated observations are never summed as
realized profit. The original `predarb demo` remains a separate illustrative
calculation and does not feed the scanner.

## Records, sampling and retention

SQLite schema 4 retains earlier archives and adds versioned fee imports/documents,
profiles, research sessions/cycles/evaluations, detail payloads, immutable replay
inputs and append-only research audit. Details contain registry decisions, raw
book references or replay hashes, exact fee provenance, policy/session binding,
evaluation time and economic assumptions. Durable summaries retain a detail hash.
Back up the archive before upgrading; no historical scan evidence is invented.

Summary reports include cadence coverage, largest gap, unfinished attempts,
rejection counts and repeated equal-quote samples. Equal samples establish an
observed interval between matching quotes; they do **not** prove uninterrupted
book lifespan or that intervening quotes were unchanged. Gaps/stale/rejected
observations break that inference. A hypothetical replay never qualifies as
live observation. Even a 30-day window needs a reviewed evidence audit;
`thirty_day_acceptance` is not granted automatically by elapsed wall time.

```bash
predarb research prune --db data/research.sqlite3 --keep-days 31
predarb research prune --db data/research.sqlite3 --keep-days 31 --apply
```

The default is a dry run. Explicit application removes only old derived detail
payloads, retaining at least 31 days. Durable summaries, hashes, prune audit,
registry history, replay inputs and raw/fee source evidence remain. This does
not reclaim SQLite file space automatically. Source archives and summaries still
grow; raw-evidence deletion, vacuum scheduling, backup rotation and deployment
hardening require a separate policy. CSV exports retain rejected evaluations,
mode, hashes and exact decimal strings, escape spreadsheet formula prefixes,
and refuse to overwrite existing files.

For deterministic, entirely hypothetical end-to-end replay:

```bash
.venv/bin/python scripts/m4_demo.py --output data/my-m4-demo
```

Use a new empty directory. The demo archives synthetic inputs before decoding,
simulates a human review of inverse propositions and fee applicability in an
isolated database, records two fresh evaluations and a stale rejection, and
exports results. These are not real approvals, historical fills or 30-day evidence.

M5A follow-up: the [read-only Kalshi WebSocket adapter](KALSHI_WEBSOCKET.md) now
feeds the same M3/M4 gates, with an optional existing-session scan callback in
the capture writer. The bounded pre-rollout `sequence-v1` feed passed live recovery
checks; see [B evidence and October 29 cutoff](M5B_SEQUENCE_RESULTS.md).
[Workstream C](M5C_RESULTS.md) adds live fee capture/validation tooling; actual
operator fee approvals remain pending. US books still need fresh evidence.
