# Configuration

Initial CLI parameters are explicit and safe: read-only endpoints, `--db`, and Kalshi `--limit`. Optional `POLYMARKET_US_DATA_BASE` overrides the default US public data host (must be HTTPS). Verify official data hostname and access conditions before collector use. Do not add secrets or trading credentials here.

Future config: polling intervals, rate budgets, max response size, book age threshold, data retention, venue balances, fee schedule version, and **zero default trade permissions**.
