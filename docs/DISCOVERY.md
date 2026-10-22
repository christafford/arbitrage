# Active-market discovery and review queue

Discovery is a read-only extension of M1/M2. It finds review candidates across
Kalshi and **Polymarket US**, never approves equivalence or authorizes trading.
The existing [pair review requirements](PAIR_REVIEW.md) remain mandatory.

## Run a bounded refresh

```bash
predarb discovery refresh --db data/research.sqlite3 \
  --page-size 200 --max-pages 1000 --books 10 --limit 100
predarb discovery queue --db data/research.sqlite3 --limit 20
predarb pairs candidates --db data/research.sqlite3 --limit 20
```

`refresh` traverses both active catalogues, archives responses before validation,
then collects market/event/series details and books for the first `--books` ranked
pairs (unique instruments are deduplicated). Finally it persists a ranked review
queue. Public requests are sequential, paced at one request/second per venue by
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
`--offline` to rebuild the queue without network access. All commands hold the
existing database writer lock; discovery must run between research-monitor
sessions using the same database. A lock conflict fails clearly instead of
starting another writer.

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
last persisted refresh time. The saved queue is a derived snapshot, not approval
authority. Both commands return at most the requested 1..1,000 suggestions.

Every result contains:

- Subject and normalized description overlap, extracted dates and numeric
  thresholds, an integer heuristic score and explicit conflicts/unknowns.
- Links to both official market-definition API responses, collected Kalshi
  event/series/contract-term sources, and imported official rule documents.
- The immutable rule-version IDs, source IDs, hypothetical marker and previous
  human decisions, including rejections. Refresh never erases or reverses decisions.
- Recent displayed book depth, raw observation IDs, source/receipt timestamps and
  quality. Missing and stale quantities remain null; observed empty/one-sided
  depth is zero. Liquidity breaks ties after semantic score.

Normalization handles Unicode, a small explicit alias set (BTC/Bitcoin,
ETH/Ethereum, CPI/consumer price index, Fed/federal reserve), ISO and full English
month dates, participant subtitles and US long-side descriptions/team names,
and common greater/less-than thresholds with inclusivity, dollar,
percent, points, basis points, C/F temperature units and magnitude markers.
Equal numeric values with unspecified units receive only partial credit and an
explicit warning; unknown units are not treated as confirmed equal. Documented `occurrence_datetime`/`gameStartTime`
provide UTC event dates when present. Close/end timestamps remain separate
cutoffs, never inferred event dates. Unknown date formats, abbreviated names,
ranges, unexpressed units and inverse propositions require human interpretation.
An inverted subject index avoids comparing every possible pair. Description-only
retrieval uses up to three rare terms and requires two shared terms when available;
common boilerplate is excluded. A score upper bound skips detailed comparisons
that cannot enter the requested result set while preserving score ties. This heuristic can miss genuine matches
and return false positives. It is not a calibrated probability or legal analysis.

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
invalid prices and unknown quantities are never promoted to fresh executable
liquidity. Economic and approval gates are unchanged.

## Human review and periodic operation

Select source IDs from the queue and use `pairs propose`, `pairs document` and
`pairs review` as documented in [PAIR_REVIEW.md](PAIR_REVIEW.md). Discovery does
not generate approval attestations, choose complementary legs or fill review
rationales. A prior rejection remains visible even if the candidate reappears.

`deploy/predarb-discovery.service` and `.timer` provide an hourly periodic refresh
with two minutes of jitter, a two-hour execution bound, SIGINT shutdown and the
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
