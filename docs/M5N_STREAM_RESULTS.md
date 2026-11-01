# M5N authenticated US stream continuation — November 1, 2026

**Authenticated Polymarket US market data works. Short-window NFL updates were
timely; the quiet Fed snapshot remained stale. Continuous freshness, US sequence
continuity and strict economic eligibility are not established.**

## Recovered work

The interrupted session had advanced beyond the committed [M5N report](M5N_RESULTS.md).
The operator supplied an existing local key, a 15:40 UTC handshake succeeded,
and the 15:42:44–15:43:14 UTC v1 smoke captured 11 books. The first prototype had
stopped on unfamiliar optional statistics; its redacted evidence remains in
`data/m5n/authenticated/smoke/`. The subsequent v1 smoke is preserved intact.
The original unauthenticated 401 is historical evidence, not the current blocker.

This continuation finishes protected fixed-path signing, public-shape screening,
bounded raw capture, per-market diagnostics, signal shutdown, meaningful exit
codes and deterministic replay. Crossed/locked/unsorted books are rejected;
missing requested markets are distinguished from completion of the time budget.
The new `market-data-ws` extra uses the same dependencies as `kalshi-ws`.

[Official sources](evidence/M5N_STREAM_API_CHECKS.json) were recaptured at 16:33 UTC.
The Markets page's camelCase/string-enum subscription was accepted live; the
overview's alternative spelling remains untested. Optional statistics are
documented in the MarketService 1.0.0 book schema. No sequence, remote send
watermark or quiet-book validity guarantee was inferred.

## Actual 120-second US capture

`data/m5n/authenticated/resumed-120s/` ran **16:38:03.349–16:40:03.385 UTC**.
The handshake took 179 ms. One connection archived **64 exact public frames /
444,870 bytes**, all replayed with matching hashes and decisions. No application
heartbeat was observed; automatic ping/pong worked, with last observed library
RTT **33.9 ms**. No invalid/private-enriched frames, clock-jump stops or source
regressions occurred in this window.

| Metric | Arizona–Dallas NFL | December Fed hold |
| --- | ---: | ---: |
| Book messages | 63 | 1 |
| Timestamp/depth diagnostic passes | 62 | 0 |
| Older-than-two-second observations | 1 | 1 |
| Source age at receipt: minimum / median / maximum | 28.8 / 92.2 / 7,318.5 ms | 108.628 s |
| Observed depth changes after first snapshot | 20 | 0 |
| Repeated depth after first snapshot | 42 | 0 |
| Largest interval between book messages | 7.873 s | UNKNOWN; no second message |
| Latest source age at capture finish | 0.318 s | 228.406 s |

Slugs: `aec-nfl-ari-dal-2026-11-01` and `rdc-usfed-fomc-2026-12-09-nochng`.
The stale NFL observation was its initial snapshot; all 62 later messages passed.
Repeated ladders show source timestamps can advance without a displayed-depth
change. Neither those repeats nor pongs establish validity across quiet intervals.
Passing message counts are not a time-coverage percentage.

These are source-to-application-receipt ages, not isolated network latency.
Local NTP synchronization was reported; post-capture clock evidence is in the
[validation manifest](evidence/M5N_STREAM_VALIDATION.json). Remote clock offset
is UNKNOWN. Displayed top levels do not prove all venue liquidity or fills.

## Concurrent Kalshi observation and remaining gaps

An independent process requested up to 90 seconds of the current `clocked`
Kalshi stream for `KXNFLGAME-26NOV01ARIDAL-ARI`, in a new isolated SQLite archive.
It captured **3 snapshots and 32 deltas**, with **35 usable book assessments**.
All **41 raw observations** passed stored SHA-256 checks.

The first generation timed out after five seconds without another message. The
next two ended at the unchanged periodic-resnapshot boundary. Its three-connection
budget was exhausted at **16:39:23 UTC**, so the command correctly returned **2 /
INCOMPLETE**, before its full duration. Sequenced delivery and recovery were
observed, but complete overlap coverage was not established. No source-skew or
economic eligibility claim is made from these two independent archives.

US sequence continuity remains **UNKNOWN**. The single US generation did not
exercise reconnect recovery; silent missed updates cannot be detected using a
sequence field absent from this consumed protocol. The Fed still fails freshness.
Longer representative capture, quiet-stream semantics and validated cross-venue
comparison remain open.

The [five exceptional-payout screens](M5N_RESULTS.md) remain unchanged: none has
a complete independently reviewed settlement map, fee applicability or mechanics
approval. No numerical executable arbitrage was established. Production models,
indices, expired runs and economic gates remain unchanged; no services were
restarted and no account/order requests were made.

## Verification

See [setup, failure behavior and replay](US_WEBSOCKET.md). The genuine
[four-frame fixture](../tests/fixtures/us-stream-live.json) preserves original v1
bytes, hashes and clocks. Hypothetical tests cover signing, privacy, malformed or
missing fields, invalid prices/quantities, partial/stale/future/regressing/crossed
books, clock jumps, deadlines, resources, errors, interrupts, CLI and tampering.

The recovered baseline passed **464 tests** after removing sandbox restrictions;
the sandboxed attempt had six permission-related errors. An interrupted rerun
was not counted as passing. The final command
`.venv/bin/python -m unittest discover -s tests -v` passed **472 tests in
20.063 seconds**, including 18 US-probe tests. Full output is preserved in
[M5N_STREAM_TESTS.txt](evidence/M5N_STREAM_TESTS.txt).
Additional commands executed: reader `--help`, live 120-second capture, replay
of all 64 frames, independent Kalshi capture, `pip check`, and `predarb demo`,
`report` and `pairs list` against new isolated archives. The demo is explicitly
hypothetical. The Kalshi archive contains zero pair decisions, fee profiles,
research sessions and paper intents. M5N acceptance remains partial.
