"""Explicit bounded polling and local fee/economics reports. No order APIs."""
from pathlib import Path
import time
from contextlib import closing

from .backups import readonly
from .fee_store import import_profile
from .fee_capture import capture, export_review
from .research import clock, export_csv, prune_details, scan_once, session, start_session, summary
from .store import connect
from .validation import dumps, load_json


def add_parser(subparsers):
    parser = subparsers.add_parser('research', help='read-only economics, polling and audit')
    commands = parser.add_subparsers(dest='research_cmd', required=True)
    for name in ('fees-capture', 'fees-review', 'fees-import', 'start', 'scan', 'summary', 'csv', 'prune'):
        command = commands.add_parser(name)
        command.add_argument('--db', default='data/research.sqlite3')
        if name == 'fees-capture':
            command.add_argument('venue', choices=('kalshi', 'polymarket_us'))
            command.add_argument('source_id')
            command.add_argument('--side', required=True, choices=('YES', 'NO'))
            command.add_argument('--output', required=True, help='new directory for unapproved review packet')
        elif name == 'fees-review':
            command.add_argument('capture_id', type=int)
            command.add_argument('--output', required=True, help='new directory; offline re-export at current clock')
        elif name == 'fees-import':
            command.add_argument('profile')
            command.add_argument('--attest-reviewed-fees', action='store_true')
        elif name == 'start':
            command.add_argument('--policy', required=True)
            command.add_argument('--interval', type=int, default=60)
        elif name in {'scan', 'summary', 'csv'}:
            command.add_argument('session_id', type=int)
            if name == 'scan':
                command.add_argument('--cycles', type=int, default=1)
                command.add_argument('--refresh', action='store_true', help='poll public books/details for currently approved pairs only')
            if name == 'csv':
                command.add_argument('--output', required=True)
        else:
            command.add_argument('--keep-days', type=int, default=31)
            command.add_argument('--apply', action='store_true', help='delete old derived details; retain summaries/raw evidence')


def run(args):
    context = closing(readonly(args.db)) if args.research_cmd in {'summary', 'csv', 'fees-review'} else connect(args.db)
    with context as con:
        if args.research_cmd == 'fees-capture':
            if Path(args.output).exists():
                raise ValueError('fee review output must be a new directory')
            capture_id = capture(con, args.venue, args.source_id, args.side, now=clock())
            result = export_review(con, capture_id, args.output, now=clock())
        elif args.research_cmd == 'fees-review':
            result = export_review(con, args.capture_id, args.output, now=clock())
        elif args.research_cmd == 'fees-import':
            path = Path(args.profile)
            result = {'fee_profile_id': import_profile(con, path.read_bytes(), base=path.parent, now=clock(),
                                                       attested=args.attest_reviewed_fees)}
        elif args.research_cmd == 'start':
            path = Path(args.policy)
            result = {'session_id': start_session(con, load_json(path.read_bytes()), interval_seconds=args.interval)}
        elif args.research_cmd == 'scan':
            current = session(con, args.session_id)
            if current['mode'] != 'LIVE_READ_ONLY':
                raise ValueError('CLI polling cannot run hypothetical sessions')
            if not 1 <= args.cycles <= 2678400 or args.cycles * current['interval_seconds'] > 2678400:
                raise ValueError('polling must be bounded to at most 31 days per invocation')
            for index in range(args.cycles):
                start = time.monotonic()
                result = scan_once(con, args.session_id, refresh=args.refresh)
                print(dumps(result), flush=True)
                if index + 1 < args.cycles:
                    time.sleep(max(0, current['interval_seconds'] - (time.monotonic() - start)))
            return 0
        elif args.research_cmd == 'summary':
            result = summary(con, args.session_id)
        elif args.research_cmd == 'csv':
            data = export_csv(con, args.session_id)
            # Never silently overwrite an earlier export.
            with Path(args.output).open('x', newline='') as output:
                output.write(data)
            result = {'output': args.output, 'trading_authorized': False}
        else:
            result = prune_details(con, keep_days=args.keep_days, apply=args.apply)
    print(dumps(result))
    return 0
