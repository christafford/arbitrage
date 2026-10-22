import argparse
import json
import sys
import sqlite3
from contextlib import nullcontext
from decimal import Decimal
from .models import AskLevel
from .math import evaluate
from .store import connect, save_example


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
        runs = db.execute("SELECT id,venue,status,pages,records,unique_records,duplicates FROM collection_runs ORDER BY id DESC LIMIT 10").fetchall()
        books = db.execute("SELECT freshness,liquidity,COUNT(*) FROM book_captures GROUP BY freshness,liquidity").fetchall()
        profits = [Decimal(row[0]) for row in db.execute("SELECT profit FROM opportunities")]
        sims = (len(profits), sum(profits, Decimal("0")))
        from .registry import list_pairs
        list_pairs(db)  # Evaluate expiry/freshness; cached APPROVED rows alone are not authority.
        normalized = db.execute("SELECT data_usable,COUNT(*) FROM normalized_books GROUP BY data_usable").fetchall()
        pairs = db.execute("SELECT hypothetical,status,COUNT(*) FROM pairs GROUP BY hypothetical,status").fetchall()
    print("Read-only archive counts:", dict(raw))
    print("Collection runs (id, venue, status, pages, records, unique, duplicates):", runs)
    print("Book captures (freshness AT CAPTURE, liquidity, count):", books)
    print("All live catalogue entries and books are UNVERIFIED; no actionable signals")
    print("Normalized book assessments (data usable AT ASSESSMENT, count):", normalized)
    print("Pair decisions (hypothetical, status, count; no trading authority):", pairs)
    print(f"Hypothetical evaluations: {sims[0]} (sum of *example modeled* profits, NOT realized P&L: ${sims[1]:.2f})")


def collect_venue(args):
    from . import kalshi, polymarket_us
    from .collector import collect
    adapter = kalshi if args.cmd == "collect-kalshi" else polymarket_us
    with connect(args.db) as db:
        result = collect(db, adapter, page_size=args.limit, max_pages=args.max_pages,
                         scope=args.event_ticker if adapter is kalshi else args.slug,
                         books=args.books, selected=args.book, max_age=args.max_age)
    print(json.dumps(result.as_dict(), sort_keys=True))
    print("UNVERIFIED read-only evidence; no matching/trading performed")
    if result.status == "PARTIAL":
        print("Page budget reached: catalogue is incomplete; continuation recorded", file=sys.stderr)
        return 2
    return 0


def main():
    p = argparse.ArgumentParser(description="Read-only US prediction market research")
    s = p.add_subparsers(dest="cmd", required=True)
    for name in ("demo", "report", "collect-kalshi", "collect-polymarket-us"):
        sp = s.add_parser(name)
        sp.add_argument("--db", default="data/research.sqlite3")
        if name.startswith("collect-"):
            sp.add_argument("--limit", type=int, default=20, help="records per page (1..1000)")
            sp.add_argument("--max-pages", type=int, default=10)
            sp.add_argument("--books", type=int, default=1, help="capture details and books for first N markets")
            sp.add_argument("--book", action="append", default=[], help="explicit source ID in captured scope; repeatable")
            sp.add_argument("--max-age", type=int, default=60, help="book age threshold in seconds")
            sp.add_argument("--event-ticker" if name == "collect-kalshi" else "--slug")
    from . import registry_cli
    registry_cli.add_parser(s)
    from . import books_cli
    books_cli.add_parser(s)
    from . import research_cli
    research_cli.add_parser(s)
    from . import paper_cli, ops_cli, discovery_cli, ws_cli
    paper_cli.add_parser(s)
    ops_cli.add_parser(s)
    discovery_cli.add_parser(s)
    ws_cli.add_parser(s)
    args = p.parse_args()
    try:
        if args.cmd == 'ops': return ops_cli.run(args)
        from .runtime import writer_lock
        reader = (args.cmd == 'research' and args.research_cmd in {'summary', 'csv'}) or (args.cmd == 'paper' and args.paper_cmd == 'report') or (args.cmd == 'discovery' and args.discovery_cmd == 'queue')
        with (nullcontext() if reader else writer_lock(args.db)):
            if args.cmd == "demo": demo(args.db)
            elif args.cmd == "report": report(args.db)
            elif args.cmd == "discovery": return discovery_cli.run(args)
            elif args.cmd == "stream-kalshi": return ws_cli.run(args)
            elif args.cmd == "pairs": return registry_cli.run(args)
            elif args.cmd == "books": return books_cli.run(args)
            elif args.cmd == "research": return research_cli.run(args)
            elif args.cmd == "paper": return paper_cli.run(args)
            else: return collect_venue(args)
    except KeyboardInterrupt:
        print("Collection interrupted; archived evidence retained", file=sys.stderr)
        return 130
    except (ValueError, OSError, TimeoutError, sqlite3.Error) as exc:
        print(f"Collector/error: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
