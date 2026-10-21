# Prediction Arbitrage Research (US Exchanges)

A **read-only, Codex-ready** starter for researching fully hedged binary prediction-market opportunities between **Kalshi** and **Polymarket US**. Designed for a modest always-on Linux server, a SQLite database, and an initial bankroll of **$0** during discovery, potentially **$200–$500** for separately authorized experiments, with a **$10,000 lifetime seed-deposit ceiling**.

**Current state:** Fixture-based opportunity scanner, conservative decimal arithmetic, unit tests, SQLite archival, basic Kalshi public REST collection, and raw Polymarket US endpoint collection. It does **not** automatically match live contracts, normalize live Polymarket US books, execute orders, or promise profits. Those are documented next tasks. **No trading code or credentials exist in this repository.**

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

These archive raw responses for schema inspection; **they do not imply the responses are tradable, equivalent, or cross-matched**. Failure to reach a provider is reported as an error, not silently replaced by fabricated data. Respect API rate limits and terms. Polymarket US base URL is configurable because venue hostnames/interfaces can change.

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
