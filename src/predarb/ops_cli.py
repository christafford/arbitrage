"""Health, verified backups and bounded monitor invocation; no service installation."""
from pathlib import Path
import signal
from contextlib import closing

from .backups import backup, readonly, restore, verify
from .operations import health, metrics_text, run_cycles
from .validation import dumps, load_json


def add_parser(subparsers):
    root = subparsers.add_parser('ops', help='local monitoring and verified backup/restore')
    commands = root.add_subparsers(dest='ops_cmd', required=True)
    for name in ('health', 'metrics', 'events', 'backup', 'verify-backup', 'restore', 'run'):
        command = commands.add_parser(name)
        if name in {'health', 'metrics', 'events', 'backup'}: command.add_argument('--db', default='data/research.sqlite3')
        if name in {'health', 'metrics'}:
            command.add_argument('session_id', type=int)
            command.add_argument('--min-free-bytes', type=int, default=209715200)
            command.add_argument('--max-db-bytes', type=int, default=10737418240)
            command.add_argument('--backup-dir')
        elif name in {'backup', 'restore'}: command.add_argument('--output', required=True)
        if name in {'verify-backup', 'restore'}: command.add_argument('backup')
        if name == 'run': command.add_argument('--config', required=True)
        if name == 'events': command.add_argument('--limit', type=int, default=100)


def run(args):
    if args.ops_cmd == 'backup': result = backup(args.db, args.output)
    elif args.ops_cmd == 'verify-backup': result = verify(args.backup)
    elif args.ops_cmd == 'restore': result = restore(args.backup, args.output)
    elif args.ops_cmd == 'run':
        previous = {}
        def stop(signum, frame): raise KeyboardInterrupt('monitor signal stop')
        try:
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, stop)
            return run_cycles(load_json(Path(args.config).read_bytes()))
        finally:
            for signum, handler in previous.items(): signal.signal(signum, handler)
    else:
        with closing(readonly(args.db)) as con:
            if args.ops_cmd == 'events':
                if not 1 <= args.limit <= 1000: raise ValueError('event limit must be 1..1000')
                result = [dict(zip(('id', 'at', 'severity', 'action', 'detail'), row)) for row in
                          con.execute('SELECT id,ts_utc,severity,action,detail_json FROM ops_events ORDER BY id DESC LIMIT ?', (args.limit,))]
            else:
                result = health(con, args.session_id, min_free_bytes=args.min_free_bytes,
                                max_db_bytes=args.max_db_bytes, backup_dir=args.backup_dir, record=False)
                if args.ops_cmd == 'metrics':
                    print(metrics_text(result), end='')
                    return 0 if result['ready'] else 2
    print(dumps(result))
    return 2 if isinstance(result, dict) and result.get('ready') is False else 0
