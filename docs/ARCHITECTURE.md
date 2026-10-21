# Architecture

```text
Kalshi REST/WS          Polymarket US REST/gRPC
      |                           |
raw response capture -> normalized instrument / quotes
                       |
              reviewed pair registry
                       |
          depth-aware hedge evaluator
                       |
        opportunities / rejection reasons
                       |
              SQLite + reports
                       |
         future paper execution replay

           NO LIVE ORDER PATH IN MVP
```

## Components

- `src/predarb/provider.py`: bounded HTTP GET, no credentials, failure is explicit. Extend with proper rate limits and paging.
- `src/predarb/kalshi.py`: Kalshi public market catalogue + book capture; `orderbook_fp` format requires complementary price conversion from YES and NO bids before normalizing **asks**.
- `src/predarb/polymarket_us.py`: **US-only** refdata and book capture. Do not confuse with Gamma/CLOB international endpoints. Adapter currently stores raw payload pending versioned schema verification.
- `src/predarb/models.py`, `math.py`: pure Decimal-based sizing and opportunity evaluation for **operator-approved** hypothetical equivalents.
- `src/predarb/store.py`: WAL SQLite storage, provider observations and computed opportunities.
- `src/predarb/cli.py`: simulation, report, raw provider collectors.

## Assumptions / unknowns

- A binary YES/NO pair pays $1 collectively **only** if their legal settlement outcomes are complementary and each venue pays as expected. Settlement terms, void/cancellation, timing, rounding, outage risk must be reviewed.
- NO is not automatically available as a long-buy instrument on every venue in identical form. Map the documented venue mechanics explicitly. A quote might be bid, ask, or implied from complements; document direction.
- Two API responses are **not synchronous**. Timestamps need source and receipt time; stale or crossed books must be rejected.
- Execution and post-trade settlement involve fees and capital tied up. Fees can depend on price/contract type, trade direction, and current schedule.
- No guaranteed simultaneous fills across venues; actual realized P&L can differ substantially from quoted theory.

## Data storage plan

Starter tables:

- `raw_observations`: venue, endpoint, retrieval timestamp, response JSON.
- `opportunities`: simulation timestamp, pair tag, contracts, cost, fee assumption, modeled profit and provenance `hypothetical=true`.

Later migrations: `instruments`, `rules_versions`, `pair_approvals`, `book_snapshots`, `book_levels`, `fee_schedules`, `candidate_opportunities`, `execution_simulations`, `audit_events`.

Storage: SQLite WAL, indexes by venue/time, short transactions, compression/partitioning or rollups after profiling. Keep backup and retention policies; 1 TB disk is not a reason to store unlimited uncompressed snapshots at millisecond cadence.

## Deployment

Dedicated non-root Linux user, systemd service with restart/backoff, localhost-only dashboard (later), secrets external to repo (later). Backup the database regularly. Start with polling and small selected markets; only graduate to streaming after snapshot correctness and missed-update recovery are tested.
