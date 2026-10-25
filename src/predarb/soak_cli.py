"""Local bounded collection run/report commands; no economics or account actions."""
import signal
import threading

from .book_stream import PROTOCOLS
from .kalshi_auth import Credentials
from . import soak
from .validation import dumps


def add_parser(subparsers):
    parser = subparsers.add_parser('soak', help='bounded collection-only operational test')
    commands = parser.add_subparsers(dest='soak_cmd', required=True)
    run = commands.add_parser('run', help='create a new isolated archive and collect selected instruments')
    run.add_argument('--output', required=True, help='new directory; existing paths are refused')
    run.add_argument('--kalshi-ticker', required=True)
    run.add_argument('--us-slug', required=True)
    run.add_argument('--credentials-file', default='~/.config/predarb/kalshi-readonly.json')
    run.add_argument('--seconds', type=int, default=300, help='10..86400; default five-minute smoke')
    run.add_argument('--poll-seconds', type=int, default=10)
    run.add_argument('--segment-seconds', type=int, default=60)
    run.add_argument('--backup-seconds', type=int, default=21600)
    run.add_argument('--min-free-mb', type=int, default=1024)
    run.add_argument('--max-storage-mb', type=int, default=4096, help='total run directory including backups')
    run.add_argument('--protocol', choices=PROTOCOLS, default='clocked')
    report = commands.add_parser('report', help='read status and detect a stale writer heartbeat')
    report.add_argument('directory')


def run(args):
    if args.soak_cmd == 'report':
        result = soak.read_report(args.directory)
    else:
        keys = ('kalshi_ticker', 'us_slug', 'seconds', 'poll_seconds', 'segment_seconds',
                'backup_seconds', 'min_free_mb', 'max_storage_mb', 'protocol')
        config = {key: getattr(args, key) for key in keys}
        soak.validate_config(config, soak.clock())  # Before reading credentials or creating files.
        credentials = Credentials.load(args.credentials_file)
        stopped = threading.Event()
        old = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        def stop(signum, frame): stopped.set()
        try:
            for sig in old: signal.signal(sig, stop)
            result = soak.run(args.output, config, credentials, stop=stopped)
        finally:
            for sig, handler in old.items(): signal.signal(sig, handler)
    print(dumps(result), flush=True)
    return 0 if result['status'] == 'COMPLETED' and result['coverage_assessment'] == 'OBSERVATIONS_RECORDED' else 2
