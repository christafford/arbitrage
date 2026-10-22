# Prediction Arbitrage Research (US Exchanges)

A **read-only, Codex-ready** starter for researching fully hedged binary prediction-market opportunities between **Kalshi** and **Polymarket US**. Designed for a modest always-on Linux server, a SQLite database, and an initial bankroll of **$0** during discovery, potentially **$200–$500** for separately authorized experiments, with a **$10,000 lifetime seed-deposit ceiling**.

**Current state:** M1–M3 are complete. M4 economics/recording and M5 paper/operations are implemented and tested; **M4's actual 30-day run and M5's actual multiweek run remain pending**. Research includes versioned fees, depth/budget/reserve evaluation, paper downside scenarios, later-quote comparisons, local health/metrics, verified backups and deployment templates. All live evidence remains `UNVERIFIED`; no real pair or fee profile is approved. Kalshi REST lacks source time and fails freshness checks. No live trading or service activation exists. See [M5 results and gaps](docs/M5_RESULTS.md), [paper model](docs/PAPER_EXECUTION.md), [operations](docs/OPERATIONS.md) and [M4 results](docs/M4_RESULTS.md).

**M5A A/B:** discovery is implemented. The read-only Kalshi WebSocket adapter is
implemented with offline tests; **actual authenticated continuity remains blocked
by missing credentials**. Workstreams C–E have not been started. See
[M5A results](docs/M5A_RESULTS.md) and [WebSocket setup](docs/KALSHI_WEBSOCKET.md).

## Quick start (Python 3.11+; no external dependencies)

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
predarb demo --db data/research.sqlite3
predarb report --db data/research.sqlite3
python -m unittest discover -s tests -v
```

For a short **read-only public API** collection pass (internet access required):

```bash
predarb collect-kalshi --db data/research.sqlite3 --limit 20
predarb collect-polymarket-us --db data/research.sqlite3
```

Each collector defaults to 20 records per page, at most 10 pages and one selected book plus details. A capped traversal reports `PARTIAL` and exits **2**; terminal pagination exits **0**; failure exits **1**. Raw evidence is retained after errors. A venue-wide catalogue can exceed the default budget.

For a bounded scope that can reach its terminal page:

```bash
predarb collect-kalshi --db data/research.sqlite3 --event-ticker EVENT_TICKER --limit 20 --max-pages 10
predarb collect-polymarket-us --db data/research.sqlite3 --slug MARKET_SLUG --limit 20 --max-pages 10
```

Replace those placeholders with real IDs from the catalogue. Use `--books N` for the first N markets, `--book SOURCE_ID` for explicit selections (repeatable, overrides `--books`), or `--books 0` for metadata only. Selection IDs must belong to the captured scope. `--max-age 60` flags stale book timestamps (allowed range 1..3600 seconds). Kalshi REST books have no source timestamp and are explicitly flagged unknown. All live evidence is `UNVERIFIED`.

Collectors use fixed verified US production origins, no credentials and no redirects. The previous arbitrary Polymarket base override is restricted to `https://gateway.polymarket.us`. Review [official API sources and data-use restrictions](docs/API_SOURCES.md) before ongoing collection. Sanitized provider fixtures remain subject to provider rights and are for local research.

## Market discovery

```bash
predarb discovery refresh --db data/research.sqlite3 --limit 100
predarb discovery queue --db data/research.sqlite3 --limit 20
```

Refresh both active US catalogues with paced pagination, rank metadata candidates,
and archive details/books for the top candidates. The review queue exposes
matching reasons, conflicts, liquidity uncertainty and official definition links.
All suggestions remain `UNVERIFIED`. See [discovery](docs/DISCOVERY.md) for coverage,
exit codes, offline use and the hourly timer templates.

## Pair review (M2)

```bash
predarb pairs candidates --db data/research.sqlite3
predarb pairs list --db data/research.sqlite3
predarb pairs --help
```

These suggestions do not approve contracts. Follow the [human review workflow](docs/PAIR_REVIEW.md) to archive complete official sources, propose a pair, inspect a blank review form, and make an explicit human decision. Approval is local research metadata and grants no trading permission.

To exercise the complete CLI safely offline with labeled hypothetical contracts, run from the repository root with a new empty database path:

```bash
.venv/bin/python scripts/m2_demo.py --db data/my-m2-demo.sqlite3
```

The demo asserts same-title semantic rejection, simulated approval/revocation and rule-change invalidation. It never approves a real pair.

## Book inspection (M3)

```bash
predarb books list --db data/research.sqlite3
predarb books inspect OBSERVATION_ID --db data/research.sqlite3
predarb books inspect OBSERVATION_ID --db data/research.sqlite3 --side YES --quantity 1
.venv/bin/python scripts/m3_demo.py --output data/my-m3-demo
```

Replace `OBSERVATION_ID` with an integer from the list. Inspection recomputes
quality at the current time; `--at ISO_TIMESTAMP` is explicitly historical replay.
Both ladders and known fresh source time are required. US NO depth is labeled
synthetic short-YES exposure. Quote costs exclude fees and do not imply fills.
The offline demo requires a new empty output directory and shows hypothetical
depth exhaustion, staleness and sequence/reconnect recovery. See the
[book guide](docs/BOOKS.md) for rejection reasons, exit codes and comparison gates.

## Economics and recording (M4, acceptance pending)

```bash
predarb research start --db data/research.sqlite3 --policy examples/M4_RESEARCH_POLICY.json
predarb research scan SESSION_ID --db data/research.sqlite3
predarb research summary SESSION_ID --db data/research.sqlite3
.venv/bin/python scripts/m4_demo.py --output data/my-m4-demo
```

Use the integer session ID returned by `start`. The sample policy has zero venue
budgets. Live calculations require current human-approved contracts, fresh books
and explicitly reviewed fee applicability; unknown costs are rejected. The demo
uses an isolated hypothetical replay. See the [economics guide](docs/ECONOMICS.md)
for fee imports, bounded polling/resume, assumptions, exports and retention.

## Paper and operations (M5, acceptance pending)

```bash
.venv/bin/python scripts/m5_demo.py --output data/my-m5-demo
predarb paper report --db data/research.sqlite3
predarb ops health SESSION_ID --db data/research.sqlite3
predarb ops backup --db data/research.sqlite3 --output data/backups/research-NEW.sqlite3
```

Use a new empty demo directory, an existing integer session ID and a new backup
destination. Paper fills/cancel acknowledgments are assumed, with explicit
one-leg downside and unknown-data rejection. The monitor cannot place orders.
See [paper workflow](docs/PAPER_EXECUTION.md) and [deployment/restore guide](docs/OPERATIONS.md).

Before a multiweek run, inspect health **after the first completed cycle**.
`ready=true` describes host readiness; the `research.status` field separately
shows empty, data-gated or recent economic observations. The monitor warns when
refresh is disabled (as in the one-cycle example). Even with refresh enabled,
the current approval, fee and Kalshi source-time gaps must be resolved before
the run can provide useful cross-venue economics. See the
[M5 hardening verification](docs/M5_HARDENING.md) for changes and remaining limits.

## Read in this order

1. [AGENTS.md](AGENTS.md) — binding development instructions for Codex.
2. [docs/PRODUCT.md](docs/PRODUCT.md) — scope and acceptance criteria.
3. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, schemas, and data path.
4. [docs/RISK.md](docs/RISK.md) — trading, settlement, and capital safeguards.
5. [docs/ROADMAP.md](docs/ROADMAP.md) — sequential tickets Codex should execute.
6. [docs/API_SOURCES.md](docs/API_SOURCES.md) — authoritative provider docs to verify.
7. [docs/CODEX_PROMPTS.md](docs/CODEX_PROMPTS.md) — first prompt and follow-up pattern.

## Non-negotiable constraints

- Never treat a similar title as proof of identical settlement.
- Never treat best quotes as a fill guarantee.
- Never claim an arbitrage is risk-free in the real world.
- No leverage, automatic deposits, international Polymarket API, or live orders in the initial development stages.
- No order placement without a distinct, reviewed implementation milestone and explicit operator approval.
- In finance code use `Decimal`, exact quantities, realistic fees, and a bounded executable price-depth simulation.

## Expected hardware

One low-power Linux machine with reliable fiber and substantial local disk. Python + SQLite suffice initially; optimize or migrate only after profiling. Internet bandwidth will not eliminate market latency, quote staleness, API limits, or leg risk.

## License

MIT (see LICENSE). Educational/research software; not investment advice. Check local eligibility, exchange terms, taxes, and regulations before any eventual trading.
