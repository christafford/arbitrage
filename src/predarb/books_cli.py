"""Inspect archived normalized depth; commands make no network requests or trading decisions."""
from datetime import datetime, timezone
from .book_store import inspect_book, inspect_pair
from .store import connect
from .validation import dumps, utc_time


def add_parser(subparsers):
    root = subparsers.add_parser('books', help='read-only normalized book inspection')
    commands = root.add_subparsers(dest='book_cmd', required=True)
    for command in ('list', 'inspect', 'pair'):
        parser = commands.add_parser(command)
        parser.add_argument('--db', default='data/research.sqlite3')
        parser.add_argument('--at', help='explicit historical UTC clock for offline replay; not a current quote')
        parser.add_argument('--max-age', type=int, default=60)
        if command == 'inspect':
            parser.add_argument('observation_id', type=int)
            parser.add_argument('--side', choices=('YES', 'NO'))
            parser.add_argument('--quantity', help='hypothetical depth coverage, in exact contracts')
        elif command == 'pair':
            parser.add_argument('pair_id', type=int)
            parser.add_argument('--kalshi-observation', type=int, required=True)
            parser.add_argument('--us-observation', type=int, required=True)
            parser.add_argument('--max-skew-ms', type=int, default=2000)
        else:
            parser.add_argument('--limit', type=int, default=20)


def run(args):
    if not 1 <= args.max_age <= 3600:
        raise ValueError('max_age must be 1..3600 seconds')
    now = utc_time(args.at) if args.at else datetime.now(timezone.utc)
    with connect(args.db) as con:
        if args.book_cmd == 'list':
            if not 1 <= args.limit <= 100:
                raise ValueError('limit must be 1..100')
            rows = con.execute('''SELECT b.observation_id,r.venue,b.source_id,r.ts_utc FROM book_captures b
                JOIN raw_observations r ON r.id=b.observation_id ORDER BY b.observation_id DESC LIMIT ?''', (args.limit,)).fetchall()
            result = []
            for observation_id, venue, source_id, received_at in rows:
                try:
                    inspected = inspect_book(con, observation_id, now=now, max_age=args.max_age)
                    result.append({key: inspected[key] for key in ('observation_id', 'venue', 'source_id', 'data_usable', 'rejections')})
                except ValueError as exc:
                    result.append({'observation_id': observation_id, 'venue': venue, 'source_id': source_id,
                                   'data_usable': False, 'rejections': ['INVALID_ARCHIVE: ' + str(exc)]})
        elif args.book_cmd == 'inspect':
            result = inspect_book(con, args.observation_id, now=now, max_age=args.max_age,
                                  side=args.side, quantity=args.quantity)
        else:
            result = inspect_pair(con, args.pair_id, args.kalshi_observation, args.us_observation,
                                  now=now, max_age=args.max_age, max_skew_ms=args.max_skew_ms)
    print(dumps({'historical_replay': bool(args.at), 'evaluated_at': now.isoformat(), 'result': result,
                 'verification': 'UNVERIFIED', 'trading_authorized': False}))
    # List is descriptive. A specifically requested invalid book/pair returns 2, never silent success.
    if isinstance(result, dict) and not result.get('data_usable', result.get('comparison_ready', False)):
        return 2
    return 0
