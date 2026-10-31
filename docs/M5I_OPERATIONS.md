# M5I persistent discovery operations

M5I adds a separate SQLite semantic index. All output remains `UNVERIFIED`.
`discovery refresh` now collects with resumable page budgets and uses the persistent
index without calling inference. The original in-memory embedding helper remains
only for the explicitly synthetic benchmark and compatibility tests. Its 512 cap
is not used by the production worker or persistent retrieval.

Back up a source archive before its next writer opens it. Schema 9 adds durable
catalogue page checkpoints and lookup indexes; it preserves all existing evidence
and reviews. Workers can read an unchanged schema-8 source. The sidecar initializes
its own versioned derived tables and raw inference archive. It is bound to the
source's absolute path. To relocate/rebuild it, use a new sidecar, never silently
point an existing sidecar at another source.

```bash
. .venv/bin/activate
# Collection has no AI dependency. Repeat each until COMPLETE; exit 2 is PARTIAL.
predarb discovery catalogue-walk --db data/research.sqlite3 --venue kalshi --max-pages 20
predarb discovery catalogue-walk --db data/research.sqlite3 --venue polymarket_us --max-pages 20
# Bounded metadata backfill; repeat until scan_complete. Later scans renew only
# copied source receipts and prioritize new/modified versions, not local clocks.
predarb discovery index-sync --db data/research.sqlite3 --budget 10000
export PREDARB_EMBEDDING_URL=https://cachyos.tail2be75f.ts.net/v1/embeddings
predarb discovery index-work --db data/research.sqlite3 --kalshi-budget 256 --us-budget 256 --seconds 120
predarb discovery index-retrieve --db data/research.sqlite3 --query-budget 500 --limit 20
predarb discovery index-coverage --db data/research.sqlite3
```

`--index-db` overrides the default `SOURCE.semantic.sqlite3`. Each command is
restartable. Workers take only the sidecar lock. They never take the source
collector lock. The optional systemd service/timer runs synchronization, inference
and retrieval separately from the collector; units are templates, not activated.
Exit 2 from inference denotes fallback and preserves committed vectors. Missing
configuration is an error. `index-retrieve --deterministic-only` needs no AI service.
For a sustained run, `index-work --expected-identity SHA256` pins a previously
validated model namespace. It makes at most three exact probes within the existing
HTTP budget. A mismatch returns `FALLBACK` without switching the active namespace
or embedding market text. Close probe vectors are never merged or relabeled.
`refresh --cached-catalogues --books 0` synchronizes a bounded metadata batch and
publishes the source review queue without network requests. `discovery queue`
revalidates its saved source versions, receipts, snapshot expiry and liquidity.
The sidecar retrieval command maintains its own candidate reservoir; the next
refresh publishes it to the main queue. Reports identify which path was used.

## Bounds and checkpoints

- Catalogue: 1–1,000 records/page, 1–1,000 pages/invocation, one venue per walk;
  default 200 records × 20 pages. Existing provider transport allows three attempts
  per request, 10 MB responses, one request/second and bounded Retry-After/backoff.
  Maximum attempts are three times the page budget. No book/detail requests in a walk.
- Complete means terminal pagination across the resumed run, not an atomic venue
  snapshot. Offset movement can omit/duplicate records; periodic complete passes
  are still needed. Changed cursor/page-size or no progress fails explicitly.
  `--restart` starts a new traversal after provider cursor invalidation; old evidence
  remains. Raw responses and entries precede an atomic accepted-page checkpoint.
- Synchronization streams source rows, defaults to 10,000 records, maximum 100,000.
  Up to 75% goes to newly observed rule versions, with at least 25% rotating through
  the existing catalogue. Checkpoint/documents/FTS changes commit together. No
  unlimited in-memory task list is created. Existing definitions use stable hashed
  scheduling, not provider page order, for inference.
- Inference: one HTTP request at a time, default 16 texts/batch, max 100 attempts
  per invocation, default five-second socket timeout and two retries. Per-venue
  budgets are 0–10,000; default 256 each. Venues alternate batches. Default worker
  time is 120 seconds (1–3,600 configurable), throughput ceiling eight texts/second
  (up to 100 configurable). The time budget stops between batches, so one bounded
  request/retry sequence can finish after the deadline. Successful batches survive
  interruption. New/modified work has priority; every fourth batch reserves
  backfill. No vector is mixed across model identities or changed text.
- Memory: one inference batch, one streamed metadata row, at most 2 × candidate-cap
  candidate documents per query, and a 1,000-event reservoir. Per-query vector
  prefilter uses 16 indexed hash bands with at most candidate-cap+1 hits per band;
  exact cosine reranks at most candidate-cap vectors (default 256, max 1,024).
  Float arithmetic is limited to retrieval. Money and quantities remain Decimal.
  The deployment template has a 256 MB memory ceiling. The field run reports
  observed process RSS; this is not a universal memory guarantee for adversarial text.
- Derived vector retention is 250,000 rows; inactive identities are evicted first.
  Current vectors removed by this bound return to backlog. Cached vectors expire
  after 30 days. Raw source/inference evidence is retained, never silently pruned.
  A 1 GiB free-space guard runs before inference batches; CLI commands also check
  their configured startup threshold. Monitor and back up the sidecar separately.

Metadata is eligible only while the authoritative source is fresh (24 hours),
available, in the latest complete catalogue when present, and not blocked by a
failed/interrupted/running collection. Unsupported sports and side mappings stay
excluded. Missing metadata categories are `UNKNOWN`; no category is guessed from
an event ticker. Horizons use documented administrative deadlines; these are not
verified settlement or cash-release times. Exact side/price/quantity/fee/collateral
review remains in the existing research gates. Fresh observed two-sided book
liquidity is a tie-breaker, never assumed from metadata volume or an absent quote.

## Retrieval and evaluation limits

SQLite FTS5 keyword retrieval, supported NBA/NFL identity, and a persistent
multi-probe sparse-hyperplane vector index contribute candidates. Cosine uses full
validated vectors for the bounded candidate set. This is approximate retrieval;
`bucket_saturations` reports capped probes and recall must be measured at the
intended scale. No first-512 comparison pool remains. Generic queries advance a
persisted hash-order checkpoint; the bounded event reservoir merges prior windows
only after source revalidation. `window_complete=false` is partial query coverage.

Material text contradictions rank below contradiction-free suggestions regardless
of cosine. Unsupported sports cannot enter through vectors. Administrative
non-sports deadlines over 90 days apart are filtered; this is a conservative
retrieval heuristic that can cause false negatives, not a settlement finding.
One Kalshi event contributes at most one review candidate, preventing threshold
ladders from filling the queue. Sports fair-price, postponement, forfeit and
revision issues remain explicit even when ordinary event identity is exact.

The October 29 [proposition-guard correction](M5I_CORRECTIONS.md) rechecks amounts,
inequalities, observation windows, recognized proposition types and rounding on
read, including existing sidecar/main-queue snapshots. No embedding rebuild is
needed. Unknown units and unsupported language remain unverified.

```bash
python scripts/m5i_evaluate.py --directory data/new-m5i-offline --output data/m5i-offline.json
python scripts/m5i_evaluate.py --live --directory data/new-m5i-live --output data/m5i-live.json
python -m unittest discover -s tests -v
```

The committed corpus is genuine archived public material, not synthetic text.
It is purposively selected, assistant-labeled, small and not independently
adjudicated or held out. All unlisted cross-pairs in that narrow corpus are
negative proposition labels. Precision is among returned candidates, not precision
at a fixed 20 padded slots. Recall@20/@100 use per-query proposition labels;
event diversity intentionally reduces the number of returned thresholds.
Historical replay fixes the evaluation clock and never renews source timestamps.
A live inference evaluation refuses a stale corpus. Model identity, inference
throughput, raw archival evidence, false-negative categories and index coverage
are separate outputs. See [measured results](M5I_RESULTS.md).

If the sidecar writer is busy, retrieval can use a consistent read-only snapshot;
that invocation reports `sidecar_writable=false` and does not advance its checkpoint.
Initial partial synchronization also retains the bounded, revalidated established
deterministic source queue. An AI outage or an empty new sidecar therefore cannot
silently replace known valid deterministic candidates with an empty queue.
Unknown sidecar schema/source bindings are errors. Corrupt vectors are refused;
use a new sidecar to rebuild derived data while preserving the original evidence.
Diversity caps both Kalshi event identity and the US scheduled event/normalized
question group; generic question titles retain their explicit selection title.

## Authorized 24-hour run, October 28–29

The operator authorized ongoing collection and backfill on October 28. The
[run record](M5I_RUN_20261028.md) distinguishes startup evidence from completed
acceptance. `scripts/m5i_run.py` supervises two independent local services using
existing CLI commands; its fixed UTC deadline survives process and host restarts.
Public catalogue collection has no inference dependency and captures no books.

Collection alternates 20-page invocations, 200 records/page, until both walks are
complete. It waits six hours after completion before the next refresh. A traversal
has a 2,000-page ceiling per venue. Semantic work waits for complete catalogues,
syncs the full metadata scan in 10,000-row invocations (maximum 100), then runs
600-second inference batches followed by 250-query retrieval and coverage reports.
Each inference invocation allows up to 1,536 definitions per venue, with the
existing 100-HTTP-attempt and eight-texts/second ceilings. A fallback still runs
retrieval, then backs off five minutes. Other command failures get two retries
after 60/120 seconds, then stop that service. Neither service stops its peer.

Each service is limited to 256 MiB memory plus 64 MiB swap and 16 tasks. The runner
requires 5 GiB free space and stops when source/index files plus their WAL files
reach 80 GiB. Each child has a 900-second ceiling, shortened by the run deadline;
shutdown sends SIGINT, allows 30 seconds for cleanup, then terminates a stuck
child. Successful batches and page checkpoints remain resumable. Raw evidence
is retained. These bounds can leave an unfinished backfill at the deadline.

The installed units are enabled in the existing user's systemd manager. User
lingering was enabled so logout does not end the run. Both services exit at the
fixed deadline even after reboot; no timer schedules an indefinite future run.
After the run, disabling the units prevents later boot-time no-op starts.

```bash
systemctl --user status predarb-m5i-collection-20261028.service predarb-m5i-semantic-20261028.service
cat data/m5i/run-20261028/collection-status.json
cat data/m5i/run-20261028/semantic-status.json
predarb discovery index-coverage --db data/research.sqlite3 --index-db data/m5i/index.sqlite3

# Gracefully stop and disable this run if needed; checkpoints remain.
systemctl --user disable --now predarb-m5i-collection-20261028.service predarb-m5i-semantic-20261028.service
```

Exact configuration, installed unit copies, command outputs/stderr, supervisor
checkpoints, pre-migration backups and manifests are retained under
`data/m5i/run-20261028/`. Services log status changes to the user journal. A
`BATCH_COMPLETE` report is progress, not evidence that the whole run has finished.


## Separate-namespace recovery run, October 29–30

The operator authorized a physically separate sidecar after verifying the restored
runtime. Use `--index-db data/m5i/qwen-8f1b.semantic.sqlite3` for this run; the old
`data/m5i/index.sqlite3` is preserved and is not this run's active sidecar. Do not
combine coverage or vectors across namespaces. The [run record](M5I_RUN_20261029.md)
lists services, bounds, exact pin, partial startup measurements and stop commands.
Its fixed deadline is October 30 11:20:39 UTC (07:20:39 EDT). Inspect status files
and existing writer services before issuing manual work. The old October 28
configuration and deadline remain unchanged; its units remain disabled.


The October 29–30 separate-namespace run has now stopped and its units are disabled.
Use the [final audit](M5I_RUN_20261029_RESULTS.md), rather than startup counts,
for measured results and remaining backlog/quality issues. Its fixed deadline and
checkpoints remain intact; do not extend the expired configuration implicitly.


## Read-only retrieval profiling and v2 guards — October 30

`scripts/m5i_profile.py` profiles a bounded historical query window against the
source and sidecar opened read-only. It requires an explicit assessment clock,
checks sidecar/source binding, never advances checkpoints and makes no inference
or venue calls. Apply production resource limits; see the exact command and
[measured results](M5I_CORRECTIONS_20261030.md). An expired assessment clock is
only for replay; its candidates must not be represented as live.

The runner now reuses the coverage already returned by `index-retrieve`, avoiding
a second full catalogue scan after each worker batch. `BATCH_COMPLETE.coverage_at`
is the retrieval coverage assessment time; the status receipt can be later.
Initial post-sync coverage and explicit `index-coverage` remain available.
Versioned v2 proposition guards revalidate old metadata and saved candidates on
read, without reembedding. Unknown fields remain unknown, and material conflicts
cannot be overridden by semantic similarity. These changes do not restart either
expired run or change its deadline/model pin.
