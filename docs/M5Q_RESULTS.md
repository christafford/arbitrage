# M5Q — economic signal validation

**M5Q acceptance is incomplete.** Offline reconstruction and the official-source
continuity review were executed. The new five-minute selection screen failed on
all three candidates, including under the existing 50% quality target, so the
requested one-pair 15-minute observation was **not started**. No failed candidate
was promoted, run extended, service renewed, contract approved or money spent.

The operator requested [the M5Q plan](M5Q_ECONOMIC_SIGNAL_VALIDATION.md). Execution
used `data/m5q/run-20261108/`, the saved `plan.json`, and the existing collectors.
[Operations and exact reproduction commands](M5Q_OPERATIONS.md) describe the
bounded selection, explicit one-pair scope, failure behavior and read-only replay.
The production model/index and all economic approval gates remain unchanged.

## Offline economic reconstruction

The [complete inventory](evidence/M5Q_INVENTORY.json) contains **14 historical
windows, 132,751 archived channel-observations and 4,229 recorded quality-pass
claims**. Audit admits **132,517 observations and 4,221 passing samples** for
reconstruction. Fifteen development workers/segments are quarantined: eleven M5O
v1 segments lacking committed-reader frontiers, two already-failed M5O v2 smoke
segments, and two M5P smoke workers with journal-hash failures. Their **234 samples,
including eight recorded pass claims**, are excluded rather than repaired into
usable evidence. These are acceptance gaps, not silently dropped observations.

Every one of the original M5O run's **385 passing samples** was newly rebuilt
using raw data and historical reader visibility; all **1,224,595 raw hashes** across
its **653 segments** matched. Historical rejected samples retain their original
classifications and hash-bound full-segment audits; this does not claim a new full
semantic replay of all 116,593 samples. The 23 accepted historical M5P workers
received full replay: **87,459 events, 15,718 channel-samples, every interval,
41,611 SQLite raw records and 9,427 US frames** verified.

| Accepted historical scope | Observations | Quality passes | Gross-positive samples | Sample episodes |
| --- | ---: | ---: | ---: | ---: |
| M5O operational / REST | 116,593 | 385 | 4 | 4 |
| M5P operational / stream | 7,759 | 3,775 | 192 | 69 |
| M5P operational / REST comparison | 7,759 | 28 | 0 | 0 |
| Accepted development / stream | 100 | 33 | 5 | 2 |
| Accepted development / REST | 306 | 0 | 0 | 0 |

There are **196 operational gross-positive samples**, plus five development
samples reported separately. The three gas DISCOVERY discrepancies and later M5P
DISCOVERY signals were previously suppressed by the conditional-only calculator;
M5Q adds isolated price arithmetic without upgrading their classification.
The [economic evidence](evidence/M5Q_ECONOMICS.json) includes every pair/budget,
nonpositive results, exact depth walks, source timing and quarantine details.
Full per-sample data and all episodes are in
`data/m5q/run-20261108/offline/{observations.jsonl,report.json}`; their hashes are
bound by the evidence. The current screen has a separate `screen-economics/` output.

### Ranked historical quote discrepancies

This table ranks available gross dollars under the $500 quote budget. It exposes
liquidity, sampled duration and settlement uncertainty rather than treating the
highest price discrepancy as the best arbitrage. The Senate conditional series
has stronger repetition evidence than Brooklyn's single observation.

| Rank / pair | Preserved class | Best gross / quote debit | Matched quantity at that quote | Positive samples / distinct depth states | Longest sampled episode | Main unresolved risk |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1. Brooklyn–Indiana | CONDITIONAL | $5.050500 / $499.999500 | 505.05 | 1 / 1 | 0s; single point | Independent exceptional sports payouts |
| 2. Senate Republican control, original validation | CONDITIONAL | $5.0500 / $499.9500 | 505 | 118 / 103 | 5.079393s | Control attribution, media-call and fallback rules differ |
| 3. Georgia Republican governor | DISCOVERY | $5.0500 / $499.9500 | 505 | 5 / 4 | 2.005289s | Officeholder/inauguration versus election-winner determination |
| 4. Senate control, later screen/holdout | DISCOVERY | $0.5000 / $499.5000 | 500 | 69 / 67 | 15.076404s | Same unresolved election settlement; no promotion |
| 5. Gas above $4.60 | DISCOVERY | $0.16160000 / $7.85840000 | 8.02 | 3 / 3 | 0s; three isolated points | Different observation windows, not a confirmed ordinary proposition |

The gas quote's best positive quantity is only 8.02 units; deeper matched depth
exists but does not improve gross gain. Its [source-bound review](m5m/gas-high.md)
identifies Kalshi's earlier issuance-to-year-end interval versus the US
September 9–December 31 interval. A qualifying price only in the earlier interval
can make both selected legs lose. Its apparent two-cent spread is not evidence
of a hedge. Georgia's [selection evidence](M5P_SECOND_CANDIDATE.md) retains the
inauguration/election-winner distinction and unadjudicated exceptions.

### Four capital scenarios: strongest repeated conditional series

At the preserved November 3 Senate observation, displayed Kalshi NO was **$0.74**
and US long YES **$0.25**, giving **$0.01 gross per matched unit** under ordinary
complementary payouts. Both displayed levels cover all quantities below. Total
matched ladder depth was 1,404,456 units, but that is not depth entirely at these
prices, a budget allowance, or a fill guarantee.

| Quote budget | Matched quantity | Kalshi debit / one-leg downside | US debit / one-leg downside | Combined quote debit | Gross gain | Reviewed net |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| $5 | 5 | $3.70 | $1.25 | $4.95 | $0.05 | UNKNOWN |
| $25 | 25 | $18.50 | $6.25 | $24.75 | $0.25 | UNKNOWN |
| $100 | 101 | $74.74 | $25.25 | $99.99 | $1.01 | UNKNOWN |
| $500 | 505 | $373.70 | $126.25 | $499.95 | $5.05 | UNKNOWN |

The gross return on quote cost is approximately 1.01%, **not a net or annualized
return**. A hypothetical combined one-cent-per-unit fee consumes the whole edge;
two cents produces a $5.05 loss in the $500 scenario before other costs. These are
sensitivity assumptions, not reviewed venue fee rates. Later Senate quotes had
only $0.001 gross per unit and similarly unknown net economics.

For this Senate sample, Kalshi's expected expiration was about **89.94 days** away;
US supplied an administrative date, not an equivalent settlement expectation.
The local clock-only validity bound was only **1.616812 seconds** after the sample,
and a pending frame or other loss could end it sooner. Combined settlement and
reusable capital timing remain UNKNOWN. The Brooklyn point had about 2.22 hours
to Kalshi's expectation and at most 1.055670 seconds to its clock-only bound;
neither number proves a continuous opportunity or cash-release time.


The reconstruction evaluates Kalshi NO plus US long YES at $5, $25, $100 and $500
combined **pre-fee quote-cost** budgets. The other direction, Kalshi YES plus US
synthetic NO, remains explicitly blocked by unsupported short collateral mechanics.
There is no guessed reverse-direction capital or proceeds reuse.

STRICT, CONDITIONAL and DISCOVERY remain distinct. There are zero approved STRICT
pairs in these archives. DISCOVERY calculations are price discrepancies under an
explicit hypothetical one-dollar ordinary-payout premise; they do not establish
that the selected legs are complementary in every settlement case. Existing
historical sample results are not changed by the separate M5Q calculation.

Episodes break on an intervening rejected/nonpositive sample, a gap exceeding two
seconds, source-definition/classification changes, or an archive boundary. Distinct
full-depth states are counted separately from refreshed source timestamps and
repeated samples. Episode/sample counts are not independent statistical trials.
Sample spans do not establish continuous quote validity, executable fills, or
cumulative profit. Positive repeated observations must never be summed as revenue.
M5O did not journal every availability transition, so its wall coverage is UNKNOWN.

## Current live selection — no qualifying pair

The historical Senate/House election instruments and November 4 NBA games were
not reused as current active selections. Two bounded public Kalshi catalogue
responses contained 70 NBA and 56 NFL markets. Highest-activity distinct event
hints supplied Las Vegas–San Francisco, Cincinnati–Atlanta and Lakers–Detroit.
Volume only prioritized candidates; it was not a quality pass or venue-wide claim.
Twelve public detail/book responses checked exact ordinary sports identities,
open state, supported ticks/lots and two-sided depth. All remained DISCOVERY /
UNVERIFIED. A second fresh selection pass preceded the capture; six immediate
preflight definition checks matched its exact contract fingerprints.

The sole screen ran **November 8, 06:23:55.859543–06:28:55.859543 UTC**
(**01:23:55–01:28:55 EST**). All three workers reached that original deadline,
exited 0 and passed automatic and separate raw/event/sample/interval replay.
Supervisor cleanup finished at 06:28:58.158320 UTC and did not extend eligibility.

| Pair / selected YES | Passing stream samples | Full-window valid wall | First / second half wall | Selection |
| --- | ---: | ---: | ---: | --- |
| Lakers–Detroit / Lakers | 130/299 = 43.48% | 123.802199s / 300 = 41.27% | 57.12% / 25.42% | FAIL |
| Cincinnati–Atlanta / Cincinnati | 116/299 = 38.80% | 111.218708s / 300 = 37.07% | 39.32% / 34.82% | FAIL |
| Las Vegas–San Francisco / Las Vegas | 32/299 = 10.70% | 30.468174s / 300 = 10.16% | 3.31% / 17.00% | FAIL |

Each pair missed one planned one-second sample slot. Planned-denominator rates
are 43.33%, 38.67% and 10.67%; wall coverage includes the entire fixed window.
The preregistered screen required 60% sample, full-wall and each-half coverage,
at least five US depth changes, no worker errors and passing replay. Every pair
also failed the existing 50% rule, so choosing 60% did not determine the stop.
There was no eligible frozen pair for Phase B, and no 900-second configuration
was created. Phase C therefore has no independent 15-minute result to report.

The screen had **278 passing stream samples and one passing REST comparison**.
Separate economic replay of all 279 passes found **zero positive gross signals**
at all four budgets. These selection data are not relabeled as a 15-minute holdout.
They do not establish that all markets or other times lack opportunities.
[Full screen decisions](evidence/M5Q_SCREEN.json) retain every failed criterion.

## Data integrity and continuity

The screen audits verified **2,257 journal events, 1,794 channel-samples, every
wall interval, 1,282 worker SQLite raw records and 375 US frames**. Another **32**
public raw responses in catalogue, selection and preflight archives passed hash
verification. All **68/68** requested Kalshi in-band snapshots returned. There
were no worker errors, early receivers, Kalshi capture failures or failed US
segments. Source/receipt/skew checks stayed at two seconds; raw-first commits,
WAL/FULL, atomic finalization, metadata/grid validation and bounded recovery stayed
intact. Host checks passed; they do not measure exchange-clock alignment.
[Operational audit](evidence/M5Q_OPERATIONAL_AUDIT.json).

The current [US continuity investigation](M5Q_CONTINUITY.md) found no documented
consumed gap counter, recoverable sequence cursor or per-market no-change watermark.
Ordered delivery and heartbeat advice do not make unchanged resting books current.
Existing instrumentation already separates source, receipt, snapshot availability,
local observed mutation, authenticated activity and continuity loss. No alternative
freshness policy or historical strict-result rewrite was introduced.

## Fees, funding, hypothetical fills and settlement

Every budget result preserves actual displayed price/quantity walks and quote
purchase cost per venue. A book is not an executed fill: neither simultaneous
access to displayed size, priority in the queue, cancellation latency nor eventual
fill price is observed. Fee rounding can depend on fill fragmentation. No account
request or fee approval was made. **Historical fee-adjusted profitability is
UNKNOWN**, not zero; gross fee sensitivity is explicitly hypothetical.

The cash-long research model requires the displayed purchase debit per venue.
The current US collateral source describes no additional long margin, but these
instrument/account mechanics have not been independently reviewed. The reports
therefore leave all-in buying power, actual collateral requirements and net returns
UNKNOWN. The $5/$25/$100/$500 labels are quote budgets, not funded balances or
claims that fees fit inside those amounts. No offsets or sale-proceeds reuse are
credited. External funding spent in this task is $0; the $10,000 lifetime seed
ceiling is unchanged.

If only one modeled long leg fills, it can lose its entire purchase cost plus
unknown fees; that amount is included separately for each venue in every case.
If quantities differ, `abs(q_k - q_us)` units remain directionally exposed.
Exceptional mismatched payouts can lose both purchase debits. The model makes
no claim that a later hedge or liquidation is available.

Election gross signals retain material definition differences: Kalshi's early
media-call determination and February 1 officeholder fallback differ from US
majority, independent-caucus, January 4 and chamber-organization rules. The
[original source-bound findings](M5P_RESULTS.md) and exact reconstruction provenance
remain available. These differences can defeat complementary payouts.

Fresh sports definitions identify the same ordinary winner but retain independent
fair-price determinations after cancellation/postponement. Kalshi uses a 48-hour
start condition; US wording refers to rescheduling within two days and its last
fair market price. Matching tie terms in the NFL pair do not settle every branch.
The Las Vegas US description also states 4:05 p.m. ET while its `gameStartTime`
metadata says 21:25 UTC; those fields are preserved, not silently reconciled.
The [genuine public fixture](../tests/fixtures/m5q-selection-live.json) binds these
texts, exact response hashes, schemas and receipt clocks. No equivalence decision
or registry approval was made.

Kalshi's `expected_expiration_time` is a venue expectation, not guaranteed capital
release. The US `endDate` is an administrative deadline and cannot replace an
unknown settlement time. The economic evidence includes source-bound metadata
clocks and signed time from each best sample, while combined expected settlement
and cash release remain UNKNOWN. No capital-days or annualized ROI is fabricated.

## Recommendation and remaining acceptance

**Positive gross discrepancies are reproducible; no verified positive net
arbitrage opportunity was established.** Repetition supports a narrow follow-up
on fee applicability and settlement interpretation, especially the historical
Senate pattern. It does not support funded experimentation, a broad unattended
capture, or assuming that expired election signals are available now.

Further research is economically justified only as a limited, source-bound
review plus selection during a demonstrably active window. The repeated usable
spread is small enough for modest costs to erase it; the larger per-unit gas
signal has a known proposition-window mismatch. Resolve those issues before
spending more effort on broad discovery or extended observation. The new screen's
zero gross signals and failed coverage are explicit negative evidence for this
purposive overnight sample, not proof of market-wide impossibility.

M5Q remains incomplete until a freshly eligible single pair supports the authorized
independent 15-minute measurement. Source-backed fee, mechanics, exceptional-payout
and cash-release reviews remain pending. No repeated screen, new capture, longer
run, trading experiment or M6 is automatically authorized by these results.

## Verification actually executed

- Baseline `.venv/bin/python -m unittest discover -s tests -v`: **581 passed**.
- Pre-capture full suite: **590 passed in 25.660s**. [Exact names/output](evidence/M5Q_TESTS_PRECAPTURE.txt).
- Final `.venv/bin/python -m unittest discover -s tests -v`: **593 passed in 26.639s**. [Exact names/output](evidence/M5Q_TESTS.txt).
- `scripts/m5q_reconstruct.py --help`, `scripts/m5p_observe.py --help`, and
  `predarb demo` / `predarb report` in a new isolated database passed. Demo output
  is explicitly hypothetical. Local command/output log: `data/m5q/run-20261108/smoke.txt`.
- The reconstruction CLI smoke on `data/m5p/smoke-02` passed. Full historical
  reconstruction and the new screen's economic replay are recorded separately.
- Fresh selection, one 300-second screen, three automatic and three independent
  cadence audits, followed by three economic-replay audits completed.
- All **848** protected historical configuration/status files and every launch
  source hash remained unchanged. Six historical M5I units remained disabled,
  with none loaded. No inference or production-index mutation was requested.
- `git diff --check` passed.

The 15-minute observation was not run; no test or report claims that it passed.
