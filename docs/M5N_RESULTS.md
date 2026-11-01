# M5N — US stream access and exceptional-payout screening

November 1, 2026 UTC. **Access diagnosis and candidate screening completed;
stream timeliness and strict settlement compatibility remain unverified.**
This is the operator-requested read-only follow-up to M5M. No production code,
model, index, eligibility policy or approval was changed.

## Streaming result

The documented US market-data stream is
`wss://api.polymarket.us/v1/ws/markets`. A single unauthenticated, fixed-origin
connection attempt at **15:27:37 UTC** returned **HTTP 401** in **145 ms** with
`unauthorized: valid API key authentication required`. That duration measures
handshake rejection, **not quote latency**. No subscription or account request
was sent. The known project credential directory contained Kalshi credentials
only; no US key was available to this task. An operator question requesting only
an existing credential's local path remains pending.

[Actual access result](evidence/M5N_STREAM_ACCESS.json) records UTC, monotonic
duration and the error-body hash. Original error bytes are in
`data/m5n/us-handshake.body`. TLS verification, no redirects, no proxy, a ten-second
open timeout and a two-second close timeout were used. No authentication headers
or secrets were recorded. This is not a completed streaming capture.

The current [US Markets WebSocket documentation](https://docs.polymarket.us/api-reference/websocket/markets)
requires API-key authentication. Its example provides book ladders and
`transactTime`, but no explicit sequence counter or server send-time watermark.
The [overview](https://docs.polymarket.us/api-reference/websocket/overview) uses
snake_case/numeric subscription examples, while the Markets page uses
camelCase/string enums. Both representations are documented; live acceptance of
either has not been tested. Ordered delivery prose does not establish detectable
gap continuity. The [authentication guide](https://docs.polymarket.us/api-reference/authentication)
documents Ed25519 signing of timestamp + GET + path. No signer or authenticated
US adapter was added without a usable credential.

M5M's cached REST results remain the best measured US book evidence. This task
does not relabel those responses as timely. US streaming source-to-receipt delay,
receive cadence, ping/pong behavior, unchanged-book validity, sequence continuity,
remote-clock quality and synchronized comparisons are **NOT MEASURED**.

## Five currently open pairs screened

All ten market definitions passed the existing adapters and reported active/open
when captured around **15:28 UTC**. These are assistant-prepared screens, not
independent human decisions. Coverage is five selected pairs in three event
families; it is not an exhaustive market search.

| Review packet | Exceptional behavior that aligns in a limited scenario | Remaining obstacle to strict classification |
| --- | --- | --- |
| [December Fed hold](m5n/fed-hold.md) | Outright cancellation: both hold YES pay $1 | Cancellation versus rescheduling interpretation; no-meeting branch; different expiration/revision cutoffs and review discretion |
| [December Fed cut 25 bps](m5n/fed-cut25.md) | Outright cancellation: both cut YES pay $0 | Same unresolved exceptions; exact versus rounded outcomes require directional payout review |
| [December Fed hike 25 bps](m5n/fed-hike25.md) | Outright cancellation: both hike YES pay $0 | Same unresolved exceptions; exact versus rounded outcomes require directional payout review |
| [October payrolls above zero](m5n/payrolls-zero.md) | Missing release: both can use previous-month data | Pre-expiration revisions, early cancellation and fallback deadlines can select different values |
| [October unemployment above 4.3%](m5n/unemployment-4pt3.md) | Missing release: both can use previous-month data | Same revision/cancellation/deadline problems; fallback data vintage not proven identical |

The Fed cancellation match is supported by both [Kalshi FEDDECISION](https://assets.kalshi.com/contract_terms/FEDDECISION.pdf)
and [US RDC](https://www.polymarketexchange.com/files/products/PMUS%20-%20RDC%20-%20%282026.04.06%29.pdf).
It is stronger evidence than matching event titles, but covers only that scenario.
The newer US RDCCUS filing was also inspected: it concerns **dissent counts**,
not rate decisions, and cannot replace RDC. Its cancellation fallback is fair
market price. The five-year Treasury product was inspected for further search;
it contains source-error and missing-data branches, but no fresh matching Kalshi
pair was established here. Neither extra product counts as a reviewed pair.

For binary YES payouts `K` and `U`, the supported cash-funded Kalshi NO + US YES
route pays `1 - K + U` dollars per matched unit. Equality is sufficient for a
fixed $1 payoff. A proven `U >= K` in **every** allowed scenario could also bound
the payout below by $1, but this task has not proved that condition. In particular,
US rounding alone can add upside on the 25-bps pairs; it is not, by itself, a
zero-payout counterexample. The packets distinguish that observation from actual
downside scenarios and unresolved interpretation. No new dominance rule was
added to the scanner.

Payroll and unemployment have a concrete hypothetical downside: an initial value
at/below the strike followed by a correction above it before Kalshi expiration
can make Kalshi YES pay $1 and US YES pay $0. The supported combination then pays
$0. US descriptions exclude subsequent revisions; Kalshi terms exclude revisions
only after expiration and define the value at expiration. These are hypothetical
settlement scenarios grounded in captured rules, not observed settlement events.

**Zero pairs are established as strictly compatible.** Human settlement, fee,
mechanics and capital-release review remains pending for all five. No budget
economics or displayed-depth fill inference was performed. The $5/$25/$100/$500
evaluations remain blocked by those gates.

## Evidence and verification

- [Source manifest](evidence/M5N_SOURCES.json): 15 current official documents/listing
  responses, raw hashes, UTC receipts and separate PDF-text hashes. Original files
  are retained under `data/m5n/sources/`.
- [Definitions](evidence/M5N_DEFINITIONS.json): ten exact public response bodies,
  source URLs, adapter schemas, timestamps and hashes. The isolated SQLite archive
  contains **58 VALID raw responses**, including series and fee evidence.
- [Fee packets](evidence/M5N_FEES.json): ten fresh, unapproved applicability packets.
  Advertised Kalshi multipliers and US coefficients do not establish account fees.
  Required human fee fields remain blank; no fee profile was installed.
- [Audit](evidence/M5N_AUDIT.json): all source/raw hashes checked, ten definitions
  replayed through existing adapters, zero hash failures; production database
  sizes/mtimes and expired-run file hashes match the preceding M5M audit.
- [Test log](evidence/M5N_TESTS.txt): **454 tests passed in 22.373 seconds**, using
  `.venv/bin/python -m unittest discover -s tests -v`. This
  evidence-only follow-up adds no runtime path or unit test. Source replay is an
  additional local smoke, not an independent legal adjudication.

`predarb report` and `predarb pairs list` also ran against the isolated archive:
43 Kalshi / 15 US raw observations, no pair decisions, book captures or economics.
The [validation manifest](evidence/M5N_VALIDATION.json) records the smoke outputs
and service state.

Local capture/audit scripts are preserved in `data/m5n/`; their paths and hashes
are recorded in the validation manifest. The archive is separate from production.
No M5I service was started, no inference occurred, and no historical data or
approval was renewed. The unrelated local `vnc-start.sh` is untouched.

## Next concrete step

The feed blocker is **US authenticated market-data access**. Once an existing
local key is supplied for read-only use, perform a short handshake/schema smoke,
then a separately archived bounded comparison using independent receive loops.
Record source/wall/monotonic clocks, heartbeat/connection generations, source and
depth transitions, errors and concurrent Kalshi observations. Keep the original
two-second gates; report unknown continuity explicitly. Do not call a quiet,
connected stream fresh without establishing its snapshot/update semantics.

For settlement, prioritize **December Fed hold** for a human source-bound review
of cancellation versus rescheduling and asymmetric rate-range changes. It has an
explicit shared cancellation payout and avoids the 25-bps rounding distinction.
Written venue clarification may be needed; no message was sent to either venue.
If the exception map remains unresolved, keep it residual-risk research. Only
after settlement, fee and mechanics review should fresh executable economics be
measured. No real-money implementation or execution is authorized.
