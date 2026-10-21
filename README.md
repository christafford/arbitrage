# Prediction Arbitrage Research (US Exchanges)

A **read-only, Codex-ready** starter for researching fully hedged binary prediction-market opportunities between **Kalshi** and **Polymarket US**. Designed for a modest always-on Linux server, a SQLite database, and an initial bankroll of **$0** during discovery, potentially **$200–$500** for separately authorized experiments, with a **$10,000 lifetime seed-deposit ceiling**.

**Current state:** M1 read-only collectors for **Kalshi and Polymarket US** are implemented and verified against real public responses. They paginate catalogues, preserve metadata and rule evidence, capture selected books, and archive raw bytes before strict validation. Offline fixtures, deterministic replay and SQLite migration tests are included. The opportunity demo remains hypothetical; live records are always `UNVERIFIED`. There is no contract matching, actionable book normalization, or trading capability. See [M1 acceptance results](docs/M1_RESULTS.md).

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

Replace those placeholders with real IDs from the catalogue. Use `--books N` for the first N markets, `--book SOURCE_ID` for explicit selections (repeatable, overrides `--books`), or `--books 0` for metadata only. Selection IDs must belong to the captured scope. `--max-age 60` flags stale book timestamps. Kalshi REST books have no source timestamp and are explicitly flagged unknown. All live evidence is `UNVERIFIED`.

Collectors use fixed verified US production origins, no credentials and no redirects. The previous arbitrary Polymarket base override is restricted to `https://gateway.polymarket.us`. Review [official API sources and data-use restrictions](docs/API_SOURCES.md) before ongoing collection. Sanitized provider fixtures remain subject to provider rights and are for local research.

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
