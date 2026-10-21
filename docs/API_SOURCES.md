# Source references — verify again before coding against them

Official sources checked October 2026:

- Kalshi public REST market data: https://docs.kalshi.com/getting_started/quick_start_market_data
- Kalshi API home: https://docs.kalshi.com/
- Kalshi API docs index: https://docs.kalshi.com/llms.txt
- Polymarket **US** read-only data guide: https://docs.polymarket.us/data-guide/overview
- Polymarket **US** docs index: https://docs.polymarket.us/llms.txt
- Polymarket **US** official SDK: https://github.com/Polymarket/polymarket-us-python
- Polymarket **US** fee schedule: https://docs.polymarket.us/fees

Important distinction: `polymarket.com` Gamma/CLOB APIs describe the **international** venue and may expose markets that are not tradable by a U.S. resident. Do not rely on international prices or liquidity for this project. Use `docs.polymarket.us` references and US endpoints only.

Kalshi public base URL as of check: `https://external-api.kalshi.com/trade-api/v2`. Markets: `/markets`; book: `/markets/{ticker}/orderbook`. `orderbook_fp` contains bid ladders, NOT direct ask ladders. Convert complements only after testing exact response schema and quantity semantics.

Polymarket US data guide names `/v1/refdata/instruments`, `/v1/refdata/symbols`, `/v1/refdata/metadata`, `/v1/orderbook/{symbol}/bbo`, `/v1/orderbook/{symbol}`. The exact host is configured separately; confirm the current production US public URL and schemas from official Quickstart/SDK before normalizing into tradeable prices. Starter captures raw data only.
