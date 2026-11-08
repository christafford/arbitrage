# M5Q economic signal validation

The operator requested `M5Q_ECONOMIC_SIGNAL_VALIDATION.md` on November 8 UTC.
This authorizes offline reconstruction, source review, and one new 900-second
read-only observation of one suitable pair. It does not authorize M6, funds,
orders, new credentials, inference, model/index changes or automatic approvals.
All previous run deadlines remain expired.

The fixed selection plan is `data/m5q/run-20261108/plan.json`. Historical election
and NBA instruments are not standing activity guarantees. Three freshly open
sports pairs are selected from bounded public NBA/NFL hints, with exact ordinary
identity, metadata/grid and two-sided-depth checks. One 300-second screen requires
60% sample/full-wall/each-half coverage, five observed US depth changes, successful
replay and no worker errors. This supplies current quality evidence; volume alone
cannot qualify. Rank by minimum half coverage, full coverage, then stable ID.
Freeze one qualifying pair, refresh its sources/depth, and run the sole 900-second
observation. No qualifier means the live phase remains blocked, without an
automatic repeat, substituted candidate or longer run.

The existing collector has an explicit `--scope M5Q` option allowing exactly one
pair for exactly 900 seconds. The M5P default still requires two or three pairs.
It uses the same raw-first storage, WAL/FULL, atomic finalization, in-band recovery,
metadata validation, host clock checks and two-second source/receipt/skew gates.
Capture configuration binds the original deadline and launch source hashes.
Replay callbacks are read-only analysis hooks; they run only after each recorded
sample matches raw/event reconstruction. Failed worker audits quarantine their
analysis output. No production schema or approval path changes.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/m5p_select.py \
  --proposals data/m5q/run-20261108/proposals.json --output NEW_SELECTION
.venv/bin/python scripts/m5p_observe.py run \
  --candidates NEW_SELECTION/candidates.json --output NEW_SCREEN \
  --seconds 300 --kalshi-recovery-policy inband-snapshot
# Only after the registered screen passes and fresh frozen-pair checks:
.venv/bin/python scripts/m5p_observe.py run \
  --scope M5Q --candidates FROZEN_ONE_PAIR.json --output NEW_OBSERVATION \
  --seconds 900 --kalshi-recovery-policy inband-snapshot
```

These commands describe the authorized single-use plan, not permission to renew it.
Use the recorded paths/results before any further operational work.

## Reconstruction

```bash
.venv/bin/python scripts/m5q_reconstruct.py --output NEW_OFFLINE_DIRECTORY
# A single completed window, including the M5Q observation:
.venv/bin/python scripts/m5q_reconstruct.py \
  --source COMPLETED_WINDOW --output NEW_REPLAY_DIRECTORY
```

The default inventory includes all original M5O/M5P observation configurations,
including development smokes. M5O v2 raw hashes are newly checked and every
historically passing sample is recomputed from original raw data and committed
reader frontiers. Rejected M5O samples retain their historical classifications;
their previous full segment audits are hash-bound, not falsely claimed as newly
replayed. The earlier v1 development format lacks commit visibility and is
quarantined. M5P replays all raw events, samples and local-state intervals.
Failed development evidence stays failed and is excluded from economic rankings.

`observations.jsonl` contains every accepted quality-passing quote reconstruction,
including nonpositive cases and $5/$25/$100/$500 pre-fee quote budgets. Output
preserves classifications. DISCOVERY arithmetic explicitly assumes a hypothetical
one-dollar combined ordinary payout and remains a quote discrepancy, not an
arbitrage opportunity. No assistant configuration can confer STRICT status.

Both directions are accounted for: Kalshi NO plus US long YES is modeled;
Kalshi YES plus US synthetic NO remains blocked by the existing mechanics model.
Displayed depth walks show exact Decimal prices/quantities, quote purchase costs,
maximum matched quantity and gross edge. Fees, all-in buying power, additional
collateral, net profitability and cash release stay UNKNOWN without review.
One-leg maximum loss before fees is that leg's purchase cost. Unequal hypothetical
fills leave the quantity difference unhedged. No observed quote is an actual fill.

Episodes contain consecutive positive recorded samples with gaps at most two
seconds, split by intervening rejected/nonpositive samples, source versions,
classification and archive boundaries. Full combined depth hashes deduplicate
unchanged quotes independently of source timestamp refreshes. Distinct source
states, distinct depth states, sample counts and episodes are separate measures;
none is a count of independent statistical opportunities. Sample span is not
continuous opportunity duration. M5P wall coverage comes from the original event
engine; M5O wall coverage remains unknown.

Ranks use maximum available gross dollars under the four budgets, then matched
quantity and sampled span. Every row exposes settlement uncertainty; no numerical
risk score or sum of repeated hypothetical profits is invented. Development and
operational windows must be reported separately when drawing conclusions.
