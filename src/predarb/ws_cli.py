"""Explicit bounded read-only capture; credentials are never command-line values."""
from pathlib import Path
import signal

from .kalshi_auth import Credentials
from .kalshi_ws import capture
from .store import connect
from .validation import dumps


def add_parser(subparsers):
    parser = subparsers.add_parser('stream-kalshi', help='bounded authenticated read-only orderbook capture')
    parser.add_argument('ticker')
    parser.add_argument('--db', default='data/research.sqlite3')
    parser.add_argument('--credentials-file', default='~/.config/predarb/kalshi-readonly.json')
    parser.add_argument('--seconds', type=int, default=60, help='duration budget, 1..3600 seconds')
    parser.add_argument('--max-messages', type=int, default=10000)
    parser.add_argument('--max-connections', type=int, default=10)
    parser.add_argument('--min-free-mb', type=int, default=1024)
    parser.add_argument('--research-session', type=int, help='optionally scan an existing live research session in this writer')


def run(args):
    credentials = Credentials.load(args.credentials_file)
    previous = signal.getsignal(signal.SIGTERM)
    def stop(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        with connect(args.db) as con:
            callback = None
            if args.research_session is not None:
                from .research import session, scan_once
                config = session(con, args.research_session)
                if config['mode'] != 'LIVE_READ_ONLY':
                    raise ValueError('a live stream cannot feed a hypothetical research session')
                last_scan = None
                def callback(db, observation_id, now):
                    nonlocal last_scan
                    if last_scan is None or (now - last_scan).total_seconds() >= config['interval_seconds']:
                        scan_once(db, args.research_session, now=now, refresh=False)
                        last_scan = now
            result = capture(con, args.ticker, credentials, seconds=args.seconds,
                             max_messages=args.max_messages, max_connections=args.max_connections,
                             min_free_bytes=args.min_free_mb * 1024**2,
                             directory=str(Path(args.db).resolve().parent), on_book=callback)
        print(dumps(result))
        return 0 if result['status'] == 'CAPTURED' else 2
    finally:
        signal.signal(signal.SIGTERM, previous)
