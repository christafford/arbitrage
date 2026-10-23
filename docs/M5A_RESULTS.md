# M5A — Live research readiness: A/B only

Scope follows the operator's instruction: reuse Workstream A, implement B, then
stop. **M5A is incomplete. Workstream B's live continuity acceptance is blocked.**
Replacement RSA credentials authenticated on **2026-10-23 UTC**. Three real
snapshots were archived with exchange send timestamps, but each lacks `msg.clock`
and is correctly rejected. See the RSA follow-up below for current evidence.

**Latest follow-up:** a two-market diagnostic also received 26 deltas and explicit
snapshot-request responses, all missing the required clock. The validator now
reports the specific failure and explicitly requests the supported price convention.
**224 tests passed**; live acceptance remains blocked. See the
[protocol discrepancy report](KALSHI_PROTOCOL_DISCREPANCY.md) for fresh source
checks, actual capture evidence and remaining work.

Earlier authentication history:
Credentials were initially unavailable. On **2026-10-23 UTC**, operator-provided
OpenSSH Ed25519 credentials loaded after a format-support fix, but live handshakes
returned HTTP 401. A diagnostic identified `INCORRECT_API_KEY_SIGNATURE`; host NTP
reported synchronized and local time was within one second of the server Date.
The operator also reported a venue location-verification warning; a connection
between that warning and the API error has not been established. Later retries
were explicitly requested by the operator, who subsequently reported location
confirmation and supplied replacement RSA credentials. No credential contents
were exposed. No exchange key registration or account change was performed by the agent.

## Workstream A — existing evidence reused

The prior discovery extension implements bounded active catalogues, metadata
matching, liquidity hints, source links and a human-review queue. Its measured
archive contains 100,338 Kalshi and 50,000 US market records; coverage is partial,
and all 20 saved suggestions remain UNVERIFIED. Existing source/receipt freshness
still expires. No new broad collection or matching pass was run for this task.
See [discovery results](DISCOVERY_RESULTS.md) and the local
`data/discovery-review-queue.json`. No real pair is agent-approved.

## Workstream B — implemented, live proof pending

Implemented fixed-origin authenticated read-only transport, Ed25519/RSA signing
from protected external files, credential-safe errors/logging, explicit redirect
refusal, bounded ping/pong/reconnect behavior, periodic fresh metadata/snapshots,
disk/time/message/connection budgets and signal cleanup.

Reused `KalshiBookStream` for snapshot/delta validation, subscription sequence,
generation, market clock, price/quantity and exchange send-time checks. Added
schema-7 frame/connection provenance, raw or explicitly sanitized archival,
deterministic bounded replay and integration with existing M3/M4 book gates.
Invalid frames and ended generations cannot resurrect earlier depth. No receipt
timestamp substitutes for exchange source time. Setup and operational limits:
[Kalshi WebSocket guide](KALSHI_WEBSOCKET.md).

The official source manifest records URLs, retrieval times and document hashes:
[M5A API checks](evidence/M5A_API_CHECKS.json). Exact source Markdown is retained
locally under `data/m5a-api-sources/`. The new acknowledgment fixture and generated
stream tests are explicitly hypothetical, based on the documented protocol and
existing M3 snapshot fixture. They are **not actual authenticated messages**.

## Initial verification actually executed

- Installed the optional dependencies in the project virtual environment:
  websockets 17.3 and cryptography 50.0.2.
- Ran `.venv/bin/python -m unittest discover -s tests -v`: **217 tests passed**,
  including all 196 existing tests and 21 new signing, transport, privacy,
  archival/replay, recovery, migration and research-callback tests. Full output:
  [M5A tests](evidence/M5A_TESTS.txt). No tests were skipped in this run.
- Ran CLI help, expected missing-credential failure (exit 1), book listing,
  schema-7 backup/verification, demo/report, compilation and Git whitespace checks.
- Migrated a preserved copy of the small schema-6
  `data/discovery-cli-demo.sqlite3` archive to schema 7. Every row in all 30
  existing tables remained identical; both new tables were empty and foreign-key
  checks passed. The source stayed schema 6.
- Captured actual public Kalshi market detail and REST book for
  `KXFEDCUT-31DEC28-31DEC26` at **16:55:45–16:55:46 UTC, 2026-10-22** in
  `data/m5a-validation/public-evidence.sqlite3`. Both raw bodies were archived
  with endpoint, receipt time, SHA-256 and schema. The REST book correctly retained
  `UNKNOWN_SOURCE_TIME`; it did not become a timestamped WebSocket book.

[Machine-readable evidence](evidence/M5A_VALIDATION.json) contains exact commands,
exit statuses, public-response provenance and migration results. That initial run recorded **zero live WebSocket connection attempts and messages**;
the subsequent credential follow-up below records actual handshake attempts.
No service was activated and no continuous or multiweek run was launched.

## Credential-format follow-up — 2026-10-23 UTC

Added OpenSSH private-key loading through the cryptography library while retaining
Ed25519/RSA restrictions, owner-only external files, in-memory signing, and fixed
read-only endpoint behavior. The `.pem` filename does not determine the encoding.
The operator says the OpenSSH file was downloaded directly from Kalshi; it was a
valid key in a format the original loader did not handle.

The bounded live command attempted three connections and exited 2 with zero
received frames. Two additional fixed-endpoint handshake diagnostics returned
HTTP 401; the second identified the fixed error category above. Diagnostics retain
only status/category/time checks, never headers or free-text response bodies.
Public market metadata remains archived in
`data/m5a-authenticated-20261023T013700Z/capture.sqlite3`.

Full suite: **219 tests passed**, including generated hypothetical OpenSSH
Ed25519/RSA signature checks, unchanged-file assertions, and encrypted/corrupt/
unsupported-key rejection. See [test output](evidence/M5A_CREDENTIAL_TESTS.txt)
and [sanitized diagnostics](evidence/M5A_CREDENTIAL_VALIDATION.json). Live
snapshots, deltas and reconnect continuity remain unproven. No orders, real pair
approvals, fees, C–E work or service activation were added.

## RSA credential follow-up — 2026-10-23 UTC

The operator supplied a new 2048-bit RSA private key and API key ID. The file
named `rsa.pub` contained the ID, not a cryptographic public key. Validated both
locally, restricted source/destination files to 0600 and directories to 0700,
installed the private key outside Git, backed up the prior configuration in the
protected credential directory, and atomically selected the new key/ID. Neither
credential contents nor signed headers were logged or archived.

The authentication-only handshake succeeded at **03:03:55 UTC**. The subsequent
bounded CLI run authenticated and subscribed on three connections, archiving
three acknowledgments and three snapshots as exact wire bytes with local UTC
receipt times and hashes. Each snapshot has `sending_ts_ms` but lacks `msg.clock`,
which the [current official protocol](https://docs.kalshi.com/websockets/orderbook-updates)
documents. Historical replay independently confirmed all three missing-clock
rejections. The CLI exited 2 with `INVALID_STREAM_FRAME` on each connection,
zero accepted snapshots/deltas and zero usable books. No clocks were invented,
and source-time or continuity requirements were not relaxed.

[Sanitized RSA evidence](evidence/M5A_RSA_VALIDATION.json) records the command,
UTC times, connection outcomes, replay checks and verified frame hashes. The raw
archive is `data/m5a-rsa-live-20261023T030355Z/capture.sqlite3`; SQLite integrity
and foreign-key checks passed. The full unittest suite was rerun: **219 tests
passed**, with the output path/hash recorded in the RSA evidence. Authentication
and reception are demonstrated;
validated book continuity is not. Earlier Ed25519 failures do not establish a
general incompatibility with that algorithm. C–E and M6 remain untouched.

## Acceptance and remaining work

| Criterion | Status |
| --- | --- |
| A: ranked real candidate queue with original sources | Existing partial-catalogue evidence reused; human decisions remain pending |
| B: authenticated read-only adapter and offline recovery tests | Implemented; executed checks recorded below |
| Actual authenticated Kalshi snapshot plus incremental live deltas | **PARTIAL: RSA authentication and three timestamped snapshots captured; snapshots rejected for missing market clocks; no accepted deltas** |
| Live disconnect/reconnect continuity | **NOT DEMONSTRATED**; only deterministic hypothetical recovery tests |
| Three M5 blockers resolved | **No**: human pair decisions, validated live fees and live WS proof remain open |
| C: live fee validation | **Not started**, per stop-after-B instruction |
| D: payout/collateral mechanics verification | **Not started**; existing unsupported-short rejection preserved |
| E: research-readiness dashboard | **Not started** |
| Real pair approval by agent / actual orders | None / none |
| M4 30-day / M5 multiweek / M6 | Still pending / still pending / not started |

Live acceptance must later capture real authenticated snapshots and sequential
deltas with source timestamps, inspect archived provenance, and demonstrate a
fresh generation after an actual reconnect. Offline tests, public REST metadata,
or installing dependencies do not satisfy that requirement. No readiness or
milestone completion is inferred from implemented code.
