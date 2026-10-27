# Active-market discovery and review queue

Discovery is a read-only extension of M1/M2. It finds review candidates across
Kalshi and **Polymarket US**, never approves equivalence or authorizes trading.
The existing [pair review requirements](PAIR_REVIEW.md) remain mandatory.

## Run a bounded refresh

```bash
predarb discovery refresh --db data/research.sqlite3 \
  --page-size 200 --max-pages 1000 --books 10 --limit 100
predarb discovery queue --db data/research.sqlite3 --limit 20
predarb discovery queue --db data/research.sqlite3 --sports-only --limit 20
predarb pairs candidates --db data/research.sqlite3 --limit 20
```

`refresh` traverses both active catalogues, archives responses before validation,
then collects market/event/series details and books for the first `--books` ranked
pairs (unique instruments are deduplicated). Finally it rechecks those candidate
identities and persists a ranked review queue, avoiding a second full-catalogue
match after book capture. Newly discovered or changed candidates outside this
shortlist enter on the next broad refresh. Public requests are sequential, paced at one request/second per venue by
default, with the existing bounded retries, exponential backoff and Retry-After
handling. `--request-interval` accepts .25..60 seconds. It is a per-process budget;
other applications sharing the source IP still consume provider limits.

Pagination follows Kalshi cursors and US offsets through a terminal page. Page
caps are explicit: exit **0** means all attempted traversals completed, **2** means
at least one reached its page budget, and **1** means an error occurred. Failure
on one venue still permits collection of the other, but removes that venue from
fresh candidate ranking. `coverage` shows stored/eligible counts, the latest full
catalogue run, status and completion time. Terminal paging is not an atomic
remote snapshot. A capped cycle starts from the first page next time; increase
the budget until the venue reaches terminal pagination to avoid repeated prefix
coverage. There is no claim that a partial run is a complete market census.

`--books 0` collects catalogue metadata only. A selected Kalshi market is refreshed
using its event scope, because that is the documented catalogue filter. Set
`--offline` to rebuild the queue without network access. Collection and queue refresh hold the existing database writer lock; these must
run between research-monitor sessions using the same database. A lock conflict
fails clearly instead of starting another writer. `discovery queue` uses a
consistent read-only SQLite snapshot and remains available beside the writer;
it never migrates an archive or alters approval state.

The default free-space guard is 1 GiB (`--min-free-mb`), checked before the cycle
and before each catalogue/detail/book request. Raw evidence is
retained and accumulates across cycles; it is not pruned by discovery. Monitor
disk usage and preserve backups. Back up existing databases before the automatic
schema-6 migration. Queue snapshots are replaced atomically and bounded to 1,000
rows; immutable source evidence and human decisions are preserved.

## Interpret the queue

`pairs candidates` retains its JSON-list interface and performs no queue or pair
writes. It now searches **all fresh available instruments** by default; optional
`--max-instruments` is an explicit diagnostic cap. `discovery queue` returns a
coverage envelope and recomputes ranking/eligibility for persisted queue members
at read time, along with the
last persisted refresh time. Its `coverage.scope=queued_instruments` labels
eligibility counts for queue members; `stored` still counts the whole venue.
`catalogue_coverage_at_refresh` preserves coverage from the preceding broad scan. The saved queue is a derived snapshot, not approval
authority. Both commands return at most the requested 1..1,000 suggestions.

Every result contains:

- Subject and normalized description overlap, extracted dates and numeric
  thresholds, an integer heuristic score and explicit conflicts/unknowns.
- Links to both official market-definition API responses, collected Kalshi
  event/series/contract-term sources, official US-venue rule links declared in
  archived descriptions, and imported official rule documents. Declared links
  are not independently fetched or authenticated by discovery.
- The immutable rule-version IDs, source IDs, hypothetical marker and previous
  human decisions, including rejections. Refresh never erases or reverses decisions.
- Recent displayed book depth, raw observation IDs, source/receipt timestamps and
  quality. Missing and stale quantities remain null; observed empty/one-sided
  depth is zero. Liquidity breaks ties after semantic score.

## Sports discovery (v2)

`discovery-v2-sports` adds a dedicated matcher for **NBA and NFL full-game winner**
contracts. It uses a league-scoped team alias table and requires both participants,
the selected team, the full-game market type, and the original scheduled calendar
date to agree. US long-side team metadata must agree with the rule description;
the other side must identify the opponent in the same instrument. It does not
assume that the first side, home team or opponent is the YES/long selection.

The date comes from the explicit scheduled-date phrase in the rules (including
verified abbreviated month forms). An NBA game scheduled for October 25 Eastern
can have a US start clock and Kalshi occurrence clock on different UTC dates.
Those different fields do not establish different games. Neither clock is
rewritten, and no fixed three-hour adjustment is invented. Missing, conflicting
or unrecognized rule dates stay unsupported rather than being guessed from a
ticker or settlement timestamp.

Candidates are labeled `match_basis=SPORTS_EVENT_IDENTITY`, `UNVERIFIED`, and
`equivalence_verified=false`. The legacy `equivalence_score_bps` field is a
**ranking heuristic, not an equivalence probability**. An 8000 score can still
include a known postponement conflict. Identity is sufficient to recommend
reviewing two definitions, never to approve their payout mapping.

Postponement-window differences remain explicit. Forty-eight hours versus two
weeks is a conflict; forty-eight hours versus two calendar days requires
interpretation. Missing windows, cancellations, fair-price payouts, overtime,
ties and other exceptions still require complete source-bound human review.
This matcher does not determine that any exceptional payout is equivalent.

Recognized unsupported sports formats cannot fall back to generic text similarity.
This excludes the observed soccer both-teams-to-score / college-football quarter
scoring false match. Props, spreads, totals, periods, other leagues, ambiguous
teams and unknown schema/type variants are currently outside this dedicated
matcher. `sports_coverage` reports recognized/supported counts and reasons for
unsupported records within the current eligible scope. It is not a complete
sports-market census, and generic unrecognized prose can still produce errors.

Use `--sports-only` with either `refresh` or `queue`. A queue read filters only
persisted members; it cannot discover omitted matches. Rebuild a fresh archive's
queue after upgrading:

```bash
predarb discovery refresh --offline --sports-only --db data/research.sqlite3 --limit 100
predarb discovery queue --sports-only --db data/research.sqlite3 --limit 20
```

Offline refresh does not renew stale catalogues. Without `--offline`, a sports-only
refresh still traverses both complete venue catalogues; the flag filters matching
and selected book captures, not the venue download scope. Existing freshness,
full-catalogue membership and failed-run gates are unchanged. All-scope discovery
also uses the sports matcher, while retaining generic matching for non-sports.

The October 25 live verification refreshed a **bounded eight-game seed set** from
the archived schedule and rebuilt the main queue. It did not traverse all current
markets. See [results and current shortlist](SPORTS_DISCOVERY_RESULTS.md).

## Generic matching and liquidity

Normalization handles Unicode, a small explicit alias set (BTC/Bitcoin,
ETH/Ethereum, CPI/consumer price index, Fed/federal reserve), ISO and full English
month dates, participant subtitles and US long-side descriptions/team names,
and common greater/less-than thresholds with inclusivity, dollar,
percent, points, basis points, C/F temperature units and magnitude markers.
Equal numeric values with unspecified units receive only partial credit and an
explicit warning; unknown units are not treated as confirmed equal. Outside the
dedicated sports path, documented `occurrence_datetime`/`gameStartTime`
provide UTC event dates when present. Close/end timestamps remain separate
cutoffs, never inferred event dates. Unknown date formats, abbreviated names,
ranges, unexpressed units and inverse propositions require human interpretation.
An inverted subject index avoids comparing every possible pair; generic format,
unit and scheduling words such as “vs”, “total” and “points” cannot by themselves
join unrelated participants. Description-only
retrieval uses up to three rare terms and requires two shared terms when available;
common boilerplate is excluded. A score upper bound skips detailed comparisons
that cannot enter the requested result set while preserving score ties. This heuristic can miss genuine matches
and return false positives. It is not a calibrated probability or legal analysis.

Explicit core-goods/core-services/core/headline CPI labels and monthly/annual
change periods are separate subject facets. Conflicts receive a strong penalty
and a `SUBJECT_METRIC_CONFLICT` or `SUBJECT_PERIOD_CONFLICT` warning; missing
qualifiers stay unknown. This is a small conservative facet set, not general
semantic understanding.

Conflicting dates, thresholds, first/final/revision/negation language and cutoffs
lower ranking and surface review warnings. A perfect score still says
`UNVERIFIED`. Available instruments require receipt evidence within 24 hours and
an unexpired known cutoff; failed/interrupted/running venue refreshes are gated.
A complete full catalogue excludes instruments absent from that sweep. A scoped
refresh does not falsely retire markets in unrelated scopes.

The liquidity proxy is the minimum total displayed quantity across both captured
sides and venues, using exact Decimal arithmetic. It has **no price bound** and
is not an executable hedge quantity. Kalshi REST lacks source book time and is
explicitly `UNKNOWN_SOURCE_TIME`, even when its receipt is recent. US NO exposure
still has its existing synthetic-short limitations. Stale receipts/source times,
invalid prices, non-open US book states and unknown quantities are never promoted to fresh executable
liquidity. Economic and approval gates are unchanged.

## Human review and periodic operation

Select source IDs from the queue and use `pairs propose`, `pairs document` and
`pairs review` as documented in [PAIR_REVIEW.md](PAIR_REVIEW.md). Discovery does
not generate approval attestations, choose complementary legs or fill review
rationales. A prior rejection remains visible even if the candidate reappears.

`deploy/predarb-discovery.service` and `.timer` provide an hourly periodic refresh
with two minutes of jitter, a two-hour execution bound, a 2 GiB memory ceiling,
SIGINT shutdown and the
existing dedicated-user deployment layout (`/opt/predarb`, `/var/lib/predarb`).
They are templates, not activated by the CLI. After installing the package and
creating the dedicated account as described in [operations](OPERATIONS.md), copy
the units into `/etc/systemd/system`, review paths/budgets, then enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now predarb-discovery.timer
journalctl -u predarb-discovery.service
```

Inspect each refresh's exit status and `coverage`. A partial traversal is recorded
as a failed oneshot invocation, which is intentional visibility; the timer retries
on its next scheduled invocation. Stop with `systemctl stop predarb-discovery.timer`
and, if a cycle is running, `systemctl stop predarb-discovery.service`.
No service was installed or activated during implementation.

## Missing US catalogue update timestamp (2026-10-24 fix)

Polymarket US documents `Market.updatedAt` as optional/nullable. Newly observed
markets can omit it. The collector now retains a missing/null metadata update
clock as SQL `NULL`; it does not substitute creation time or retrieval time.
Present values must still be nonempty, timezone-aware timestamps. `createdAt`,
`endDate`, identity, status, side and price checks retain their existing requirements.
Book `transactTime` remains mandatory and independent of metadata update time.
Discovery's existing catalogue retrieval-age checks and human approval requirements
are unchanged. All suggestions remain `UNVERIFIED`.

A prior failed US collection remains failed; `--offline` alone cannot recover it.
If Kalshi already completed successfully and its observations are still within
the 24-hour retrieval window, refresh only the failed venue and then rebuild the
queue from both archived catalogues:

```bash
predarb collect-polymarket-us --db data/research.sqlite3 --limit 200 --max-pages 1000 --books 0
predarb discovery refresh --offline --db data/research.sqlite3 --limit 100
```

The first command starts a new US traversal from offset zero; it does not resume
or rewrite the failed run. Inspect its exit/status before ranking: exit 0 means
terminal pagination, 2 means the page budget ended with partial coverage, and 1
means failure. Failed runs remain ineligible. If Kalshi is stale, rerun the normal
two-venue `discovery refresh` instead. Offline ranking does not fetch fresh books
or details, approve candidates, or establish research readiness.

`discovery --limit` bounds the **candidate queue**, not the number of downloaded
markets. A refresh may therefore traverse hundreds of pages per venue despite
`--limit 100`. `--max-pages` bounds traversal at the cost of explicitly partial
coverage. In `collect-polymarket-us`, `--limit` instead controls page size.
See [verification and recovery limits](DISCOVERY_UPDATED_AT_RESULTS.md).

## Optional private embedding retrieval

Set `PREDARB_EMBEDDING_URL` to enable llama.cpp retrieval during a refresh. The
client probes the served model and dimensions, batches/caches public market text,
and falls back to this deterministic matcher on inference failure. Use
`discovery embeddings-check` before deployment; `refresh --cached-catalogues`
allows inference against fresh archived metadata without venue downloads.
`--offline`, `queue` and `pairs candidates` never initiate inference. Schema 8
requires a pre-upgrade backup. All semantic suggestions remain `UNVERIFIED`.
See [setup, bounds and benchmarking](EMBEDDINGS.md) and [live acceptance results](EMBEDDING_RESULTS.md).
