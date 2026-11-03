# M5P market-data quality recovery

The operator authorized the [M5P plan](M5P_MARKET_DATA_QUALITY_RECOVERY.md), including
one new 15-minute read-only validation after repairs and tests. This does not
authorize a full-day run, renewal, orders, funds, automatic approvals or M6.
The 50% quality target is an engineering goal for deliberately selected active
markets, not an exchange requirement or a profitability claim.

## Components and unchanged gates

`quality_recovery.py` reads historical M5O archives using SQLite `mode=ro` and
reconstructs primary/additional rejections, five terminal failure sequences and
the Brooklyn observation. It hashes every raw response. It distinguishes the
original 653 segment replay results from the three newly executed Brooklyn sample
replays. Error samples did not assess both venues: their additional failures are
UNKNOWN, not inferred from later books. Historical rejects never become passes.

`quality_capture.py` keeps independent Kalshi, US WebSocket and US REST receivers
per pair, with separate single-writer SQLite/raw-file archives. Existing protected
keys sign only the existing fixed market-data handshakes. No private subscription
or account request exists. US full frames reuse the existing metadata/grid/lot
normalizer in this isolated research module. They never enter production books
or the approved economic evaluator. US sequence continuity remains UNKNOWN.

Source and receipt age, source and receipt skew remain at **two seconds**. Existing
60-second metadata, price/quantity grids, market state, Kalshi sequence, connection
generation and freshness checks remain. Kalshi's five-second message timeout and
30-second/1,000-frame resnapshot policy are unchanged. Missing snapshot ladders
use the already tested omission correction; partial/empty books remain unusable.
No experimental freshness exemption is implemented.

Each receiver records local availability only **after** archival/validation.
The Kalshi callback records a pending barrier after raw archival, validated books,
and disconnects. It does not repeatedly replay an entire generation in the live
sampler; offline audit rebuilds the raw sequence. All raw bytes still precede
derived evidence. Privacy-redacted messages retain original wire hashes and
markers, and cannot supply an admitted book.

## Time accounting

The event journal tracks these clocks separately:

| Clock | Meaning and limitation |
| --- | --- |
| Last observed depth mutation | Local receipt when displayed depth changed; first observations and generation boundaries are left-censored; exchange mutation time is UNKNOWN |
| Last verified snapshot | Local availability after full snapshot validation; not a replacement source timestamp |
| Last authenticated validated activity | Receipt of a validated book or US heartbeat; heartbeats do not refresh depth or restore disconnected books |
| Last continuity loss | Local invalidation/disconnection; pending processing barriers are also separately visible |
| Local receipt | Original receipt of the selected book |
| Source timestamp | Kalshi provider send time or US `transactTime`, retaining their distinct meanings |
| REST request/response interval | Request start and body receipt, in UTC and monotonic time; separate from pacing and persistence |

One-second samples include the exact journal event frontier. Both stream and REST
comparisons use the same Kalshi state. The REST column sampled at one second is
not an apples-to-apples substitute for M5O's poll-completion sampling; this
difference is explicit in results.

**Valid local market-state coverage** integrates the intervals between journal
availability events. An interval is cut at every source/receipt expiry, metadata
expiry, market close, pending barrier, invalidation, disconnect and clock check.
Coverage is divided by the entire fixed run window for each pair, including
startup, reconnects and any worker downtime. The calculation uses exact Decimal
seconds from UTC microseconds. It neither multiplies passing samples by the
polling cadence nor bridges a restart. Simultaneous rejection-seconds overlap and
must not be summed into total downtime.

This measures how long the **locally known state** satisfies the unchanged checks.
It does not prove an unchanging exchange book, uninterrupted delivery, executable
fills or US sequence continuity. The historical M5O sample frontiers do not record
every state-availability transition, so its corresponding wall-time coverage is
UNKNOWN. We do not manufacture a retrospective baseline by multiplying 385 by
five seconds.

## Fixed scope and failure handling

The CLI requires two or three distinct pairs and 10..900 seconds. Each output
directory is new. Public definition/open-state checks occur immediately before the
window; changed source fingerprints stop launch. Every pair has separate archives,
but shares the same fixed UTC deadline. Wall/monotonic divergence greater than one
second or failed synchronization checks stop observation. NTP status is checked
before, every 30 seconds and after the run; it does not prove exchange-clock offset.

Receivers have bounded request timeouts, rate pacing, connection/frame/byte budgets,
a 2 GiB free-space floor and a 2 GiB per-pair storage guard checked every 30 seconds.
In-flight overshoot is possible. US connection segments last at most 450 seconds,
retain explicit close/reconnect gaps, and allow at most 20 generations. An error,
frame/byte limit or exhausted budget stays reason-coded. No silent service restart
occurs. Existing expired services remain off.

SIGINT/SIGTERM stops owned receivers. Shutdown allows 15 seconds per receiver and
60 seconds per child for shutdown/audit; forced stops are incomplete. Collection
cannot continue past the fixed deadline. Raw evidence may finish writing during
cleanup; it cannot add post-deadline samples. An early receiver ending is recorded
even when its parent worker continues recording missing data. Unexplained stops
must be separated from documented timeout/budget/clock/resource causes.

## Commands actually used

```bash
.venv/bin/python scripts/m5p_analyze.py \
  --source data/m5o/run-20261101 --output data/m5p/history
.venv/bin/python scripts/m5p_select.py --output data/m5p/selection-02
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m5p_observe.py run \
  --candidates data/m5p/selection-02/candidates.json \
  --output data/m5p/smoke-02 --seconds 20
.venv/bin/python scripts/m5p_observe.py run \
  --candidates data/m5p/selection-02/candidates.json \
  --output data/m5p/validation-20261103 --seconds 900
```

These paths are historical evidence and cannot be reused. The initial selection
attempt hit a US TLS timeout and remains in `selection-final/`. The first smoke
failed both event-journal hash audits due to float/Decimal canonicalization; its
failed evidence remains in `smoke-01/`. The corrected second smoke passed both
audits. Smoke failures are not concealed or counted as successful validation.

Offline replay needs neither credentials nor network:

```bash
.venv/bin/python scripts/m5p_observe.py replay \
  --config data/m5p/validation-20261103/config.json \
  --pair house-dem --output data/m5p/validation-20261103/house-dem
```

Replay verifies wire/archive hashes, raw-first provenance, journal hash chaining,
generation/sequence reconstruction, source-version bindings, sample visibility and
all coverage intervals. Results and audits are derived files; original raw source
files remain retained. Genuine fixtures preserve full public bytes, schemas and
receipt times. Fault injection and synthetic book tests are labeled hypothetical.

Any optional one-hour validation is a **separate proposal** after the initial
engineering targets pass. This CLI cannot launch it and no automatic continuation
is authorized. [Results](M5P_RESULTS.md) list acceptance gaps.
