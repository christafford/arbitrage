# Sports discovery correction — 2026-10-25 UTC

The main research queue now contains **eight same-event sports candidates** from
a bounded live refresh: seven NBA games and Kansas City–Seattle. All remain
`UNVERIFIED`, with `equivalence_verified=false`. The existing Fed pair remains
terminally `REJECTED`. No other pair decision or live-trading permission was made.

## What changed

The old generic matcher could drop Lakers–Jazz because `Los Angeles L` and `LA
Lakers` had little word overlap, and Kalshi's occurrence clock crossed UTC midnight
while the US start clock did not. It also admitted soccer both-teams-to-score
versus college-football quarter-scoring false matches.

`discovery-v2-sports` uses an explicit NBA/NFL full-game identity key: league,
both teams, selected team and the scheduled calendar date in the rules. US
long/short instrument-side identities must agree with the description. The
matcher keeps timestamp roles separate and rejects unsupported or ambiguous
recognized sports from generic retrieval. It does not convert a game identity
into a settlement-equivalence finding. See [matching rules and limits](DISCOVERY.md).

The current dedicated scope is NBA/NFL game winners. Other leagues, player props,
spreads, totals and partial-game contracts require further explicit support.
Non-sports generic matching remains heuristic; this change does not claim to
eliminate all discovery false positives or find every available sports market.

## Current review shortlist

These are October 25 scheduled games in the archived seed set. Both venues'
selected current market details and books were refreshed, along with Kalshi
event/series evidence. Market status and book freshness can change after capture.

| League | Game | Selected proposition matched |
| --- | --- | --- |
| NBA | Detroit–Philadelphia | Detroit wins |
| NBA | Indiana–Brooklyn | Indiana wins |
| NBA | Clippers–Oklahoma City | Clippers win |
| NBA | Lakers–Utah | Lakers win |
| NBA | Memphis–Sacramento | Memphis wins |
| NBA | Orlando–New York | Orlando wins |
| NBA | Toronto–Minnesota | Toronto wins |
| NFL | Kansas City–Seattle | Kansas City wins |

Every NBA example still needs review of **48 hours versus two calendar days**,
actual start versus rescheduling conditions, cancellation/fair-price payouts and
the complete governing terms. The NFL example explicitly differs on **48 hours
versus two weeks** and is not an equivalent arbitrage pair based on the captured
summaries. No approval recommendation was generated for these records. Synthetic
US NO exposure remains unsupported by the project's capital model.

The eight candidates have an 8000 ranking score under the current heuristic.
That is not an 80% equivalence probability, and does not override any warning.
Current REST depth can be stale; Kalshi REST still has unknown source time.
Discovery ranking is not an executable quote or a fee-adjusted profit calculation.

Inspect the current queue with:

```bash
predarb discovery queue --sports-only --db data/research.sqlite3 --limit 20
```

The main archive now has 16 additional successful scoped collection runs and 72
new raw responses for these eight games. Existing full-catalogue timestamps remain
October 24: **no market-wide refresh was claimed**. The prior queue was preserved
locally in `data/sports-discovery-20261025/previous-queue.json`; fresh selections,
collection reports and queue snapshots are in the same directory. Exact IDs,
warnings, commands and audit checks are in
[the validation record](evidence/SPORTS_DISCOVERY_VALIDATION.json). The selected
raw evidence remains in `data/research.sqlite3` under the recorded run IDs.

## Measured activity

A separate 90-second Lakers–Jazz collection-only test ran from approximately
**21:24:55 through 21:26:25 UTC**, using the existing explicit `sequence-v1`
protocol. Its archive is `data/sports-discovery-20261025/lakers-90s/`.

| Measurement | Observed result |
| --- | ---: |
| Kalshi snapshots | 4 |
| Kalshi deltas | 2,579 |
| Usable US book polls | 8 of 8 |
| Recorded failures | 0 |
| Samples with both feeds fresh | 7 of 8 |
| Samples meeting two-second timestamp alignment | 0 |
| Verified backups | 2 |

The command exited 0 with `COMPLETED` and `OBSERVATIONS_RECORDED`. That describes
collection, not arbitrage readiness. This was substantially more active than the
quiet Fed test, but **none of the sampled books met the strict cross-venue timing
requirement**. Polling/receipt delays and US source-clock age still need evaluation;
the freshness/skew gates were not relaxed. Sample fractions are not continuous
uptime measurements. A 90-second run cannot establish sustained sports-feed quality.

All 2,607 raw hashes and SQLite quick check passed for that activity archive;
both backups passed file/logical verification. The ongoing Fed 24-hour process
was still `RUNNING` after six hours when checked, with its original PID. It was
not restarted or switched to a different game.

## Tests and remaining work

Executed `.venv/bin/python -m unittest discover -s tests -v`: **319 tests passed**.
Exact names/results are in [the test log](evidence/SPORTS_DISCOVERY_TESTS.txt).
New tests cover actual positive/negative sports fixtures, aliases, midnight date
differences, wrong leagues/opponents/selections, missing/invalid/conflicting
dates and side metadata, unsupported types, unresolved postponement windows,
indexed retrieval, CLI sports filtering, expiry and preserved rejection history.
Existing invalid-price, stale/partial-liquidity, non-sports discovery and
readiness tests also ran. Compilation, CLI help and queue smoke checks passed.

The full raw/schema provenance is described in [API sources](API_SOURCES.md) and
[the document manifest](evidence/SPORTS_DISCOVERY_API_CHECKS.json). Live bodies
and excerpt representation are preserved in
[the regression fixture](../tests/fixtures/sports-discovery-live.json); altered
test inputs and simulated registry decisions are explicitly hypothetical.

Outstanding: complete payout-rule review, fee/mechanics applicability, fresh
synchronized quotes, broader sports-format support, renewed full catalogues and
sustained useful research observations. No M4/M5/M5A sustained-run acceptance
or clocked-protocol live acceptance is claimed by this correction.
