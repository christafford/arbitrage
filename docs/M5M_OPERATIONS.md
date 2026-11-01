# M5M read-only diagnostics and review

M5M uses new archives under `data/m5m/`. It does not write the production source or
semantic databases, call inference, modify a fee/settlement gate, or renew approvals.
The Qwen3-Embedding-8B Q6_K configuration, pooling, batch 16 and production identity
remain unchanged. No trading path exists in these commands.

## Capture

```bash
.venv/bin/python scripts/m5m_capture.py --help
.venv/bin/python scripts/m5m_capture.py \
  --output data/NEW-m5m-capture \
  --kalshi-ticker CURRENT_OPEN_TICKER --us-slug CURRENT_OPEN_US_SLUG \
  --seconds 3600
```

Verify that both selected instruments are currently open and describe the same
event before selecting them as a transport fixture. This does not approve
settlement. The actual M5M hour used Arizona–Dallas on November 1, after fresh
open-status checks. The earlier Atlanta smoke was already closed and remains a
rejected technical archive, not an eligible observation.

The output directory must be new. Credentials are loaded only from the existing
protected Kalshi **read-only market-data** file. No credential creation, account
request, trading method, US authentication implementation or exposed server is
added. TLS and fixed-origin checks remain intact.

The runner reuses `soak.run`: five-second post-completion US polling delay,
one-second inter-request pacing, three-second HTTP timeout, one attempt per poll,
300-second capture segments, unchanged five-second Kalshi message-liveness timeout
and 30-second resnapshot bound. SIGINT/SIGTERM stops cleanly. The original
monotonic deadline, NTP prerequisite, wall-clock-jump, disk/storage and backup
guards remain. A delayed request can overshoot the deadline by its bounded work
and shutdown time; it does not authorize a restart or deadline extension.

The 4 GiB configured storage guard covers the inner `capture/` directory; the
outer timing log is additional. Inspect total outer-directory usage as well. The
one-hour run is bounded; this is not an unlimited production logger. A failed
telemetry write fails the research capture rather than silently dropping evidence.
The runtime emits a status heartbeat every ten seconds, while diagnostics samples
at approximately one-second intervals when the cooperative loop is available.
HTTP, resubscriptions and backup pauses create longer gaps. This is sampled
observation quality, not a continuous opportunity-duration estimate.

Files:

- `capture/capture.sqlite3`: raw source bodies before conversion, normalized books,
  stream generations, collection status and existing operational events.
- `capture/config.json`, `capture/status.json`, `capture/backups/`: bounded-run
  state and verified snapshots; source/index run configurations remain separate.
- `timing.jsonl`: `quote-synchronization/m5m-v1` local telemetry. HTTP start,
  headers, body receipt, archive/validation completion, source association,
  application WebSocket receive clocks, sampled comparisons and depth changes.
- `clock-before.json`, `clock-after.json`: actual timedatectl responses.
- `results.json`: simple summary generated at stop. Use the audit below for
  raw-hash verification, clock/sequence checks and sampled independent replay.

WebSocket receipt is the time the application obtains a frame from the library,
not kernel packet arrival. The library can queue frames while HTTP blocks the
single writer. Ping acknowledgment is observed nonblockingly; its duration is an
upper bound including scheduling, not an exact network RTT. Only the fixed
telemetry fields are exposed to the callback; no authentication headers or raw
frame body enter the timing log.

## Replay and policy boundaries

```bash
.venv/bin/python scripts/m5m_analyze.py data/m5m/nfl-hour \
  --output data/NEW-m5m-audit.json
.venv/bin/python -m unittest discover -s tests -v
```

The analyzer requires a completed fixed-duration capture, opens SQLite `mode=ro`,
verifies every raw body hash and transport association, audits sequence/clock
progression within each generation, and reconstructs a systematic sample from
original bytes at the recorded historical assessment times. It refuses an
existing report output. A completed ten-second smoke is still ten seconds; the
configured/actual duration is visible and must be checked separately.

`strict_observation_valid` means both unchanged book-quality checks and both
existing two-second timestamp comparisons passed at that sample. It does **not**
mean the contracts, fees, mechanics, fill or capital release are approved.

`recent-response-sensitivity/m5m-v1` is an additional experimental metric. It
requires both application receipts within two seconds and retains other book
rejections, but omits cross-source timestamp skew and US `STALE_SOURCE` alone.
It never feeds economics. `continuous_us_book_validity` stays UNVERIFIED even
when this response-only metric passes. HTTP 200, a pong or repeated depth cannot
establish an uncached, uninterrupted US order book. Do not promote this metric
into the economic gate based on these results.

Depth hashes include both normalized ladders. The first snapshot and every Kalshi
reconnect reset the observation window; the preceding change time is unknown.
For repeated US snapshots, the elapsed interval describes repeated observed depth,
not proof that no intervening change occurred. Exchange event time, send time,
transaction time, local wall receive time and monotonic receive time remain
separate. HTTP Date is not a matching-engine clock correction.

## Review preparation

```bash
.venv/bin/python scripts/m5m_packets.py --output data/NEW-m5m-non-sports
.venv/bin/python scripts/m5m_review_packets.py \
  --source data/NEW-m5m-non-sports \
  --documents PATH_TO_CURRENT_HASHED_DOCUMENT_MANIFEST.json \
  --output data/NEW-m5m-forms
```

The first command is explicitly bounded to the five identified CPI/gas pairs.
It uses scoped public catalogue/detail/book collection and existing fee capture
in one new isolated research DB; it does not scan or reindex production. Changed,
closed, partial or invalid responses remain visible. The second verifies fresh
source documents and definitions, imports evidence, proposes unapproved pairs,
and exports blank forms. The supplied manifest must contain actual original
receipt times and matching raw/text hashes. Do not recast an old document as new.
Current fee-capture provenance and instrument/side identity are rechecked.
Existing proposal/output directories are refused instead of being overwritten.

The prepared [human review guide](M5M_REVIEW_GUIDE.md) links the actual packets.
Their assistant screens exclude strict eligibility, while formal human decisions
remain pending. Neither script imports an approved fee profile or calls
`registry.approve`. Any future approved candidate must use the existing guarded
research evaluator and fresh books at $5/$25/$100/$500; no economic shortcut is
provided. Displayed depth never establishes a fill.

The separate 16-request cache-header diagnostic is retained as
`data/m5m/cache_probe.py`, with raw archive and request/response timing in
`data/m5m/cache-probe/`. It alternated request order across eight pairs, used only
the documented public book URL and a standard `Cache-Control: no-cache` request
header, and made no production client change. This is a small descriptive test,
not proof of cache-layer behavior or continuous liquidity.
