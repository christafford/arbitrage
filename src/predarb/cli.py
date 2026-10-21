import argparse
import sys
from decimal import Decimal
from .models import AskLevel
from .math import evaluate
from .store import connect, save_example, save_raw


def demo(db_path):
    # HYPOTHETICAL, not sourced from live market or an approved event pair.
    yes = [AskLevel(Decimal("0.42"), Decimal("100")), AskLevel(Decimal("0.43"), Decimal("300"))]
    no = [AskLevel(Decimal("0.53"), Decimal("200")), AskLevel(Decimal("0.54"), Decimal("200"))]
    result = evaluate(yes, no, max_pairs=Decimal("400"), fee_per_pair=Decimal("0.01"), reserve_per_pair=Decimal("0.005"))
    with connect(db_path) as db:
        save_example(db, result)
    print("HYPOTHETICAL EXAMPLE ONLY — not a trade signal or verified exchange quotes")
    print(f"pairs={result.contracts} required_capital=${result.capital} modeled_profit=${result.net_profit} ROI={result.roi:.3%}")


def report(db_path):
    with connect(db_path) as db:
        raw = db.execute("SELECT venue,COUNT(*) FROM raw_observations GROUP BY venue").fetchall()
        sims = db.execute("SELECT COUNT(*),COALESCE(SUM(CAST(profit AS REAL)),0) FROM opportunities").fetchone()
    print("Read-only archive counts:", dict(raw))
    print(f"Hypothetical evaluations: {sims[0]} (sum of *example modeled* profits, NOT realized P&L: ${sims[1]:.2f})")


def collect_kalshi(db_path, limit):
    from .kalshi import get_markets
    url, data = get_markets(limit)
    with connect(db_path) as db:
        save_raw(db, "kalshi", url, data)
    print(f"Archived {len(data['markets'])} Kalshi market records; no matching/trading performed")


def collect_poly(db_path):
    from .polymarket_us import get_reference_data
    url, data = get_reference_data()
    with connect(db_path) as db:
        save_raw(db, "polymarket_us", url, data)
    print("Archived raw Polymarket US reference response; schema normalization is an M1 task")


def main():
    p = argparse.ArgumentParser(description="Read-only US prediction market research")
    s = p.add_subparsers(dest="cmd", required=True)
    for name in ("demo", "report", "collect-kalshi", "collect-polymarket-us"):
        sp = s.add_parser(name)
        sp.add_argument("--db", default="data/research.sqlite3")
        if name == "collect-kalshi": sp.add_argument("--limit", type=int, default=20)
    args = p.parse_args()
    try:
        if args.cmd == "demo": demo(args.db)
        elif args.cmd == "report": report(args.db)
        elif args.cmd == "collect-kalshi": collect_kalshi(args.db, args.limit)
        elif args.cmd == "collect-polymarket-us": collect_poly(args.db)
    except (ValueError, OSError, TimeoutError) as exc:
        print(f"Collector/error: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
