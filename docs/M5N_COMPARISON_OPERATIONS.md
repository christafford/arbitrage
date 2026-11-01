# M5N independent stream comparison

This is a bounded, read-only diagnostic. Two child processes receive Kalshi and
Polymarket US data independently. A supervisor records approximately one actual
UTC/monotonic sample each second; it does not block a receiver on the other venue's
network calls. Capture and analysis use new archives, without production database,
model, approval, fee or settlement changes.

## Capture and replay

```bash
.venv/bin/python scripts/m5n_compare.py --help
.venv/bin/python scripts/m5n_compare.py \
  --output data/NEW-stream-comparison \
  --ticker CURRENT_KALSHI_TICKER \
  --slug MATCHING_US_SLUG --slug OPTIONAL_QUIET_US_SLUG \
  --seconds 900
.venv/bin/python scripts/m5n_compare_audit.py data/NEW-stream-comparison \
  --output data/NEW-comparison-audit.json
```

Replace placeholders with selected open markets. The **first US slug** is the
cross-venue transport comparison; the optional second is a separate quiet-market
observation, never combined with the first's Kalshi book. Current metadata is
captured before launch; event identity requires separate inspection and is not
automatically approved. Defaults use the existing protected credentials at
`~/polymarket-us.api` and `~/.config/predarb/kalshi-readonly.json`.
The optional `market-data-ws` dependencies are required.

Duration is 1–900 seconds. A fixed UTC/monotonic deadline is written after
preflight, with capture-code hashes. US segments last at most 300 seconds, require
a new snapshot, and are capped at 20 connections. A transport error without HTTP
rejection may retry after two seconds; schema/privacy/resource failures and HTTP
rejections stop the coordinator. Kalshi retains its existing five-second message
timeout, thirty-second resnapshot, clocked protocol, retry policy and a maximum
120 connections / 100,000 messages. Neither receiver extends the original budget.

The coordinator requires NTP synchronization, checks wall/monotonic divergence,
maintains a 1 GiB free-space floor and checks a 512 MiB total archive limit every
ten samples. Storage can exceed the limit by data received between checks.
SIGINT/SIGTERM stops both children. At the deadline it terminates remaining owned
children, allows each up to 15 seconds for cleanup, then force-kills if necessary.
Forced cleanup is recorded as incomplete. Kalshi exit 130 at the supervisor's
deadline is expected graceful interruption, not a claim of a lost source sequence.
Natural periodic resnapshots and quiet-message timeouts remain visible.

Capture exit 0 means the supervisor reached its duration; **it does not mean
continuous feed coverage or successful quote comparisons**. Exit 2 reports an
early stop/resource failure. Exceptions and failed preflight exit nonzero. An
existing directory is refused. Starting a worker or exhausting a message budget
does not complete acceptance. There is no autonomous restart after the run ends.

## Artifacts and interpretation

- `config.json`, `status.json`, `samples.jsonl`: original deadline, actual sample
  clocks, US segment association, process status and cleanup outcomes.
- `metadata.sqlite3`, `metadata.json`: raw current open-state preflight evidence.
- `kalshi.sqlite3`: the independent single-writer raw/normalized stream archive.
- `us-NNN/`: bounded raw US captures with their own source/receipt clocks,
  redaction records, hashes and summaries. Prior generations are never reused.
- `clock-before.json`, `clock-after.json`: local synchronization evidence.
- `*.stdout`, `*.stderr`: local command results; no authentication headers.

The offline auditor opens SQLite read-only, checks all Kalshi raw hashes and every
US segment's hashes/decisions, then reconstructs the latest available books at
each **recorded historical sample**. It excludes future frames, disconnected
generations, rejected newer frames and missing US segments. Clock disagreement or
failed before/after NTP checks prevents positive overlap results. It does not
invent samples during gaps.

`timestamp_depth_overlap` requires each observed source/receipt age and both
cross-venue timestamp skews to lie within two seconds, plus existing Kalshi book
validation and US displayed-depth validation. This is an isolated diagnostic, not
the production economic gate. The US probe does not validate instrument tick/lot
metadata, and sequence continuity remains UNKNOWN. A recent snapshot or pong does
not prove no updates were missed. `economic_eligibility` always remains false.

Report passes over actual samples, expected one-second samples, measured sample
gaps, connection boundaries and rejected observations separately. A percentage of
passing samples is not a percentage of continuously verified time. Stale source
clocks, even on unchanged books, are retained as rejections. Unknown remote clock
offset is not corrected using local NTP measurements.

## Quiet-market guidance

The current official [US Markets WebSocket](https://docs.polymarket.us/api-reference/websocket/markets)
describes displayed snapshots; the [overview](https://docs.polymarket.us/api-reference/websocket/overview)
describes heartbeats and ordered delivery. Neither checked page supplies a
consumed sequence counter, source watermark or explicit assurance that heartbeats
revalidate an unchanged snapshot. [Current raw sources](evidence/M5N_OVERLAP_API_CHECKS.json)
record precisely what was checked. This is a limitation of the checked contract,
not proof that the venue has no other supported interface.

Keep quiet Fed books rejected. Before proposing a different freshness policy,
obtain documented meanings for `transactTime`, initial-snapshot validity, silent
update-loss detection, heartbeat semantics and resubscription guarantees. A venue
clarification could resolve these questions; no message was sent in this task.
The [Fed-hold review packet](M5N_FED_HOLD_REVIEW.md) keeps settlement review separate.
