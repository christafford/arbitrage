# Paper stress and later-quote comparison (M5)

This is a zero-money research model. It has no order submission, cancellation,
credentials, positions or funding path. Every fill and cancel acknowledgment is
an explicit assumption, all evidence remains `UNVERIFIED`, and every result says
`trading_authorized=false`. M4's actual 30-day acceptance and M5's multiweek
acceptance remain open. See [M5 results](M5_RESULTS.md).

## Workflow

```bash
predarb paper create EVALUATION_ID --db data/research.sqlite3 \
  --policy examples/M5_PAPER_POLICY.json
predarb paper compare INTENT_ID --db data/research.sqlite3
predarb paper report --db data/research.sqlite3 --limit 100
```

Use integer IDs. Creation requires a positive, retained M4 evaluation no more than
60 seconds old, matching detail hash, currently approved unchanged settlement
review, current unchanged fee applicability and fresh usable initial books.
No unreviewed pair or rejected economics result can create an intent. The original
policy, registry, fee and source references are copied into immutable intent
evidence so M4 detail pruning does not erase its provenance. Creating the same
intent/policy twice returns the existing ID.

Comparison rechecks the review and fees, then obtains later archived books for
the same exact instruments. Both receipt and source clocks must advance beyond
the initial samples. Later receipt/source times must be causal at the evaluation
clock; missing source time, stale/partial/crossed/off-grid data, changed terms,
expired approval or uncertain fees produce `UNOBSERVABLE`, with fills unknown.
Such results preserve the planned quantity/capital and explicitly decline to
claim a current loss bound. They do not invent zero fills or zero exposure.

Kalshi REST still has no source book time. It cannot supply qualifying live M4
evaluations or M5 comparisons. No live feed/authentication was added. No real
paper intent was created during this milestone. The pipeline is implemented and
tested with visibly hypothetical timestamped replay, not live fill evidence.

## Policy and model

The example policy contains exactly these fields:

| Field | Meaning |
| --- | --- |
| `max_hedge_latency_ms` | Positive modeled deadline, at most 60000 ms |
| `cancel_after_ms` | Positive modeled cancel-request delay, at most 60000 ms |
| `cancel_ack_delay_ms` | Assumed acknowledgment delay, 0..60000 ms |
| `participation` | Explicit decimal-string fraction of each displayed level, greater than 0 and at most 1 |
| `max_price_drift` | Exact nonnegative dollar threshold added to the initial worst consumed price |

`arrival_ms` in results is **later quote receipt delay from intent creation**,
not measured exchange execution or network order latency. Reported hedge latency
is the difference between those receipt delays when both modeled legs fill.
These quantities test the policy's timing assumptions against quote samples.

For each leg, the model walks later asks up to the initial worst consumed price
plus the declared drift threshold, allocating at most the requested quantity and
flooring participation to supported lot increments. It records price changes,
partial quantities and consumed levels. US synthetic NO is unsupported because
short/collateral mechanics are outside scope. There is no rescue trade, leverage
or automatic rebalancing when a leg fails.

The modeled cancel request occurs at the earlier of the hedge deadline and
`cancel_after_ms`. A sample during the assumed acknowledgment window permits a
possible late fill and flags the race. Samples after that window assume effective
cancellation and no earlier fill. This is a conditional stress case: unseen
pre-sample fills remain possible, and **zero modeled fills do not prove zero
real-world exposure**. Fill probability is not estimated from a displayed book.

Conservative M4 fee bounds, verified settlement costs and explicit reserves are
applied to modeled filled quantities. Exact fees for the declared per-level fill
partition are shown separately. The model evaluates the actual unequal quantities
against every reviewed payout scenario, reporting worst/best conditional net
results, downside and unhedged contracts. Unhedged quantities, budget overruns and
excessive modeled hedge latency produce HIGH paper-risk events. These are expected
stress findings, not real operational loss incidents.

Every comparison is an **independent alternative scenario**, not a cumulative
position ledger. Repeated comparisons, quantities and modeled profit must not be
summed as real fills or realized P&L. The bounded report shows latest results for
at most 500 intents and explicitly reports truncation.

## Replay and validation

```bash
.venv/bin/python scripts/m5_demo.py --output data/my-m5-demo
```

Use a new empty directory. This archives the synthetic scenario file before
parsing, runs M4's isolated hypothetical approval/economics setup, archives each
later provider-shaped input before normalization, and records seven independent
cases. The generated SQLite database retains exact input bytes and hashes.

For manual replay in that isolated hypothetical database:

```bash
predarb paper ticks-import hypothetical-ticks.json --db isolated.sqlite3
predarb paper compare INTENT_ID --tick-input TICK_INPUT_ID --db isolated.sqlite3 \
  --at 2030-01-01T12:00:02Z
```

The importer accepts synthetic inputs only in storage without live observations
or live instruments. `--at` creation/comparison is restricted to hypothetical
mode. Imported JSON must declare `paper-ticks/m5-v1`, `hypothetical=true`, matching
synthetic IDs and explicit outage booleans. It includes complete provider-shaped
metadata/books, independent receipt clocks and provider timestamps; inspect the
demo's immutable input rows for the full format.

Exit codes: 0 for a recorded modeled case or descriptive report, 2 for a comparison
whose inputs are unobservable, 1 for invalid commands, missing intents or failed
creation/import. A successful case can still carry HIGH downside flags.

## Forward observation

The [monitor runner](OPERATIONS.md) can create intents from newly gated M4 edges
and compare earlier intents to later captured ticks. Unobservable inputs may be
retried for up to 180 seconds; completed modeled comparisons are not treated as
new positions. Each cycle processes at most 50 pending intents and records queue
saturation as incomplete coverage. Missing ticks, slow polling or expired reviews
remain visible; they cannot become verified fills.

The default 60-second research interval is much slower than the example policy's
one-second hedge deadline. Late samples will often fall beyond the assumed cancel
window. This is a measured limitation of polling resolution, not evidence of fast
execution. Live forward comparison, multiweek coverage, realistic policy tuning
and the incident audit remain pending, along with M4's live prerequisites.
