# Kalshi read-only WebSocket capture (M5A Workstream B)

The adapter is implemented and tested offline. **Authenticated live continuity
has not been demonstrated:** the operator confirmed no credentials are configured.
See [M5A results](M5A_RESULTS.md). Workstreams C–E and M6 are outside this change.

## Setup and bounded capture

Install the optional transport/signing dependencies; ordinary offline/REST use
still needs only the standard library:

```bash
.venv/bin/python -m pip install -e '.[kalshi-ws]'
```

Use a dedicated Kalshi read-only key. Store an operator-created JSON configuration
at `~/.config/predarb/kalshi-readonly.json` with `api_key_id` and `private_key_path`.
The latter points to the downloaded PEM (absolute, or relative to the configuration).
Both files must be regular, owner-owned, owner-only files, outside any Git checkout;
final-component symlinks are refused. An example of the **shape**, not credentials:

```json
{"api_key_id":"YOUR-API-KEY-UUID","private_key_path":"/private/location/kalshi.pem"}
```

Do not paste credentials into chat, CLI arguments, environment variables, source,
logs or database imports. Apply mode `0600` to both files and protect their parent
directory. Ed25519 and RSA-PSS/SHA-256 keys of at least 2048 bits are supported;
encrypted PEM files and other key algorithms are refused. Key permissions are
operator-managed; the adapter does not inspect the account or infer key scopes.
It can only sign the fixed WebSocket GET handshake and sends only a single-market
`orderbook_delta` subscription. There is no order or account command path.

Back up an existing database before its automatic schema-7 migration, then use
a real ticker from discovery:

```bash
predarb stream-kalshi KALSHI_TICKER --db data/research.sqlite3 \
  --seconds 60 --max-messages 10000 --max-connections 10
```

`--credentials-file` changes only the local configuration path. The production
origin is fixed to `wss://external-api-ws.kalshi.com/trade-api/ws/v2`. TLS certificate
checks remain enabled; redirects, proxies and compression are disabled. The
transport's private logger is disabled, including when application logging is
DEBUG. Header values, handshake/close error bodies and exception text are never
logged or archived. Signing follows the [official API-key contract](https://docs.kalshi.com/getting_started/api_keys).

Defaults: one market, 60 seconds, 10,000 messages, ten connection attempts,
1 GiB minimum free space (`--min-free-mb`, minimum 200 MiB). Allowed duration is
1..3600 seconds, messages 1..100000, attempts 1..120. Handshakes, metadata requests
and close operations have their own bounded timeouts and can extend wall-clock
runtime beyond the requested receive budget. No daemon is started.

Each generation fetches fresh public market detail through the existing paced,
GET-only REST adapter. It checks the returned ticker and updates the existing
registry evidence; it never creates a pair, approves equivalence or imports fees.
Event/series/legal evidence still requires the existing review workflow.

## Continuity and fail-closed behavior

The [documented protocol](https://docs.kalshi.com/websockets/orderbook-updates)
requires a snapshot before deltas. `KalshiBookStream` checks subscription ID,
contiguous subscription sequence, connection generation, market identity,
nonregressing market clock and send time. Clocks may repeat/skip on deltas;
post-snapshot deltas must exceed the snapshot clock. A new connection resets
frontiers, accommodating documented maintenance resets, and requires a fresh
snapshot. One market per subscription avoids confusing per-market and
subscription sequence numbers.

Only `sending_ts_ms` establishes source time, labeled `PROVIDER_SEND_TIME` rather
than mutation time. Receipt time, HTTP Date and market `updated_time` never fill
in a missing exchange timestamp. Existing M3 grid, exact quantity, crossing,
source/receipt/metadata age and market-status checks apply. Partial/empty books
remain unusable while valid sequential deltas can restore liquidity.

Disconnects, invalid/unknown messages, missing acknowledgments, sequence gaps or
freshness failures discard the generation. Reconnects use bounded exponential
backoff (up to 30 seconds) and fresh signed headers. Five seconds without a data
message triggers reconnect; ping/pong alone never refreshes a book. There is also
a forced new connection after 30 seconds or 1,000 messages, bounding replay and
refreshing metadata. Quiet markets may therefore generate repeated timeouts;
the adapter declines to assert fresh depth without new exchange evidence.

Wall-versus-monotonic divergence above one second and low disk space stop capture.
SIGINT/SIGTERM close the generation and preserve committed evidence. Abrupt process
loss cannot manufacture a final disconnect record; on inspection, a book with no
new message for **five seconds** fails the additional stream-liveness gate. This
is a bounded detection window, not instantaneous failure detection. A subsequent
writer invocation closes abandoned generations. These checks do not independently
measure NTP offset; keep the existing host time-synchronization controls.

## Archive, replay and research integration

Schema 7 preserves earlier tables and adds `ws_connections` and `ws_frames`.
Every message has its local UTC receipt time, connection generation, wire SHA-256,
archive kind and original-source endpoint. Public-shaped book/acknowledgment
messages retain exact wire bytes. The optional account `client_order_id` is
removed; the archive explicitly labels that transformation and retains the wire
hash separately. Unknown/private/malformed/oversized messages and secret echoes
retain a redacted marker and hash, not their unsafe contents. This small security
screen necessarily precedes archival; book validation and normalization follow
committed archival. Transport-rejected oversize frames may expose no body to the
application and are recorded as connection failures.

Raw frames, pending/rejected barriers and normalized books join the existing M3
`book_captures`/`normalized_books` path. Replay rechecks hashes, endpoints, schema,
metadata binding, receipt order, acknowledgment and every snapshot/delta. It does
not trust a saved `data_usable` flag. New invalid frames supersede previous depth;
ended generations cannot be used as current books. Historical `books inspect --at`
can reproduce a valid earlier frame, with the usual supersession/freshness checks.
Raw frame evidence is retained, so repeated runs grow the database; no automatic
source deletion was added.

The capture holds the existing single-writer lock. Existing M3 inspection and M4
consumers load this same archived path. To run M4 scans during capture in that same
writer, optionally pass `--research-session SESSION_ID` for an existing live
research session. Scans run at its configured interval after validated books,
with all pair, fee, freshness, skew and economic gates intact. No approval or
fee profile is installed. This option uses already archived US books: **it does
not schedule a second venue's polling**, so those books will expire. Do not run
the separate research monitor or another collector against this database while
capture holds the lock. Multi-market/coordinated continuous research operation
still requires further integration and field validation.

Exit 0 means the bounded run captured a valid snapshot and delta with usable
depth and no recorded failures. Exit 2 means incomplete evidence, including
snapshot-only runs or recovered failures; exit 1 is invalid configuration/setup,
and exit 130 is interruption. Counters describe capture-time observations,
not present-day book usability, sustained uptime, economic readiness or fills.
At normal exit the connection is closed and its books are no longer current.
