# Configuration

Read-only collection parameters:

- `--db`: SQLite path (default `data/research.sqlite3`). Existing starter databases migrate automatically to schema version 3 (M1 archive, M2 registry, M3 books); back up a working archive before upgrading.
- `--limit`: records per page, 1..1000 (default 20).
- `--max-pages`: 1..10000 (default 10); exceeding the budget produces `PARTIAL` and exit 2.
- `--event-ticker`: Kalshi event filter; `--slug`: Polymarket US market filter.
- `--books`: number of discovered markets for detail/book capture, 0..100 (default 1).
- `--book`: explicit ID in captured scope, repeatable; overrides `--books` and removes duplicate selections.
- `--max-age`: book age threshold in seconds, integer 1..3600 (default 60).

Transport defaults: verified HTTPS origins, GET only, no redirects/credentials,
12-second socket timeout, three attempts, 0.25-second minimum request interval
(at most 4 requests/s per client). Backoff honors `Retry-After`; delays above 60
seconds stop with an error instead of retrying early. Multiple processes sharing
an IP also share venue rate budgets; run one collector per venue at a time.

`POLYMARKET_US_DATA_BASE` may only equal `https://gateway.polymarket.us` (optional
trailing slash). Any other value fails closed. The starter's arbitrary host
override and unverified institutional URL are no longer supported.

Commands are explicit one-shot collections. They do not poll forever or resume a
saved cursor automatically. Inspect run status in `predarb report`; rerun with a
fresh scope/budget after an error. The report's freshness classifications describe
the capture time. Stored evidence is never a current quote or approved contract
pair. Retention, disk monitoring and a scheduler remain later milestones.

See [API sources and data rights](../docs/API_SOURCES.md),
[M1 verification](../docs/M1_RESULTS.md) and each command's `--help`.

M2 `pairs` commands also use `--db`. Approval freshness/expiry is capped at 24 hours
from the earliest catalogue, supplemental or imported-source observation. Review
payouts are exact decimal strings with up to eight places. Each imported source
and text file is capped at 2 MB. Candidate defaults inspect at most 500 instruments
per venue and return at most 20 metadata suggestions; all suggestions are unverified.
Use `predarb pairs --help` and the [operator guide](../docs/PAIR_REVIEW.md).

M3 `books` commands also use `--db` and `--max-age`. `--at` supplies an explicit
historical clock, never a current quote. Normalized inspection checks source,
receipt and metadata age, with five seconds of future-clock tolerance. `books pair`
defaults to a 2000 ms maximum source/receipt skew (`--max-skew-ms`, 0..60000).
`books list --limit` accepts 1..100, default 20. `books inspect --side` requires
`--quantity` as an exact decimal string. No fees or profit are calculated. See
[book inspection](../docs/BOOKS.md) for supported increments and fail-closed gates.
