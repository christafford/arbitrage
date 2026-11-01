# Polymarket US read-only stream diagnostics (M5N)

This opt-in probe reads `wss://api.polymarket.us/v1/ws/markets`, using the existing
operator-supplied key solely to sign that market-data handshake. It subscribes to
one or two exact slugs. It does not read accounts, place orders, approve contracts,
write production databases, or change economic freshness gates.

## Setup and capture

The public REST collectors remain credential-free. For this separate authenticated
probe, install the optional transport dependencies (the existing `kalshi-ws` extra
installs the same pinned versions):

```bash
.venv/bin/python -m pip install -e '.[market-data-ws]'
.venv/bin/python scripts/m5n_us_stream.py --help
.venv/bin/python scripts/m5n_us_stream.py \
  --credentials ~/polymarket-us.api \
  --output data/NEW-us-stream \
  --slug CURRENT_US_MARKET_SLUG --seconds 30
```

Use an existing owner-only regular credential file outside any Git checkout.
The two literal `NAME=value` entries are `POLYMARKET_API_KEY_ID` and
`POLYMARKET_API_SECRET_KEY`. The earlier operator file's spelling
`POLYMARKET_API_SECDRET_KEY` is also accepted, but both aliases together are rejected.
The value is base64 Ed25519 key material: a 32-byte seed or a 64-byte seed/public-key
pair with matching public half. This is a local file format, not a venue API schema.
The file is parsed without shell execution. Do not pass secret values on the CLI.

The directory must be new. Duration is 1–600 seconds, with a single connection,
at most 5,000 frames, a 16 MiB raw-frame budget, and a 1 GiB free-space floor.
The byte guard reserves room for a maximum 1 MB frame before receiving it;
JSONL metadata is additional but bounded by the frame count. TLS verification is
enabled; redirects, proxies and transport debug logging are disabled. Handshake
and shutdown may add up to their bounded 10-second and 2-second timeouts.
SIGINT/SIGTERM closes the connection and writes a partial report. No automatic
reconnection or renewal occurs.

## Evidence and interpretation

`results.json` records counts, stop reason, exact endpoint/schema, wall/monotonic
start, one connection generation, missing requested markets, per-market timestamp
ages/depth changes, and last observed library ping/pong RTT when available.
`timing.jsonl` binds application receive clocks, decisions and hashes to numbered
frame files. Receive time is application dequeue time, not kernel packet arrival.
Pong RTT is a transport measurement; it does not refresh a quiet order book.

Recognized public frames retain their exact bytes before semantic validation.
Unknown/error/private-enriched frames retain only a SHA-256 wire digest and an
explicit redaction marker, then stop capture. Neither authentication headers nor
exception bodies are archived. Missing/invalid prices, quantities, currencies,
timestamps or identities stop validation; no missing values are invented.
Optional market statistics are privacy-screened but are not economic inputs.

The local `polymarket-us-markets-ws/m5n-probe-v2` contract uses the documented
camelCase full-market-data subscription and the existing MarketService 1.0.0 book
validator. It treats each message's displayed ladders independently. Crossed,
locked, unsorted, partial, closed, future, regressing and older-than-two-second
observations fail its diagnostic check. Price comparisons use Decimal. Timestamp
duration metrics use seconds; original nanosecond timestamp strings are retained,
while Python datetime comparisons have microsecond precision.

Exit **0** for capture means its duration completed and every requested market
provided at least one structurally valid book. It does **not** mean every book
was fresh, any continuous interval was verified, or any opportunity was actionable.
Exit **2** means incomplete/interrupted/resource-limited/failed capture; exit **1**
means invalid input or unreadable/invalid archive. A heartbeat-only capture reports
all requested markets missing. Always inspect rejection counts and end-of-capture
source ages, including when the command exits 0.

Sequence continuity and remote clock accuracy remain UNKNOWN. The official stream
does not supply a consumed sequence counter or send-time watermark; a recent
`transactTime` is not proof that no updates were missed. Passing observations
remain `economic_eligibility=false`. Metadata grids, settlement, fees, collateral
and simultaneous cross-venue execution are outside this diagnostic's acceptance.

## Offline verification

```bash
.venv/bin/python scripts/m5n_us_stream.py --replay data/NEW-us-stream
.venv/bin/python -m unittest discover -s tests -p test_us_stream_probe.py -v
.venv/bin/python -m unittest discover -s tests -v
```

Replay needs no credentials or network. It verifies endpoint/schema, frame counts,
numbered paths, archived hashes/public shapes, and recomputes assessments and market
summaries using the original receive clocks. It rejects tampered source bytes and
decisions. Exit 0 means archive verification succeeded, including for a faithfully
recorded failed capture; check its `capture_complete` separately. The old v1 smoke
remains unchanged and is covered by a genuine four-frame regression fixture, not
silently relabeled v2. Hypothetical failure tests are explicitly labeled.

See [current official source receipts](evidence/M5N_STREAM_API_CHECKS.json),
[measured results](M5N_STREAM_RESULTS.md), and [original settlement screens](M5N_RESULTS.md).
