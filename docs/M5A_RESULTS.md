# M5A — Live research readiness: A/B only

Scope follows the operator's instruction: reuse Workstream A, implement B, then
stop. **M5A is incomplete. Workstream B's authenticated live acceptance is blocked.**
The operator explicitly confirmed no Kalshi credentials are configured and asked
that live validation be recorded as blocked. No credential was invented, requested
in chat, generated at the exchange or obtained from another account.

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

## Verification actually executed

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
exit statuses, public-response provenance and migration results. **Zero live
WebSocket connection attempts and zero live WebSocket messages** are recorded.
No service was activated and no continuous or multiweek run was launched.

## Acceptance and remaining work

| Criterion | Status |
| --- | --- |
| A: ranked real candidate queue with original sources | Existing partial-catalogue evidence reused; human decisions remain pending |
| B: authenticated read-only adapter and offline recovery tests | Implemented; executed checks recorded below |
| Actual authenticated Kalshi snapshot plus incremental live deltas | **BLOCKED: no configured credentials; zero live WS messages captured** |
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
