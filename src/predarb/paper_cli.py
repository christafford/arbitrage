"""Local paper commands. --at is restricted to explicitly hypothetical replay."""
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing

from .backups import readonly
from .paper_store import archive_ticks, compare, create_intent, report
from .store import connect
from .validation import dumps, load_json, utc_time


def add_parser(subparsers):
    root = subparsers.add_parser('paper', help='zero-money stress and later-quote comparisons')
    commands = root.add_subparsers(dest='paper_cmd', required=True)
    for name in ('create', 'compare', 'ticks-import', 'report'):
        command = commands.add_parser(name)
        command.add_argument('--db', default='data/research.sqlite3')
        command.add_argument('--at', help='hypothetical replay clock only')
        if name == 'create':
            command.add_argument('evaluation_id', type=int);command.add_argument('--policy', required=True)
        elif name == 'compare':
            command.add_argument('intent_id', type=int);command.add_argument('--tick-input', type=int)
        elif name == 'ticks-import': command.add_argument('file')
        else: command.add_argument('--limit', type=int, default=100)


def run(args):
    now = utc_time(args.at) if args.at else datetime.now(timezone.utc)
    context = closing(readonly(args.db)) if args.paper_cmd == 'report' else connect(args.db)
    with context as con:
        if args.at and args.paper_cmd == 'create':
            row = con.execute('''SELECT s.mode FROM research_evaluations e JOIN research_cycles c ON c.id=e.cycle_id
                JOIN research_sessions s ON s.id=c.session_id WHERE e.id=?''', (args.evaluation_id,)).fetchone()
            if not row or row[0] != 'HYPOTHETICAL_REPLAY': raise ValueError('historical paper creation requires hypothetical mode')
        if args.at and args.paper_cmd == 'compare':
            row = con.execute('SELECT mode FROM paper_intents WHERE id=?', (args.intent_id,)).fetchone()
            if not row or row[0] != 'HYPOTHETICAL_REPLAY': raise ValueError('historical paper comparison requires hypothetical mode')
        if args.paper_cmd == 'create': result = {'paper_intent_id': create_intent(con, args.evaluation_id, load_json(Path(args.policy).read_bytes()), now=now)}
        elif args.paper_cmd == 'compare': result = compare(con, args.intent_id, tick_input_id=args.tick_input, now=now)
        elif args.paper_cmd == 'ticks-import': result = {'tick_input_id': archive_ticks(con, Path(args.file).read_bytes(), now=now)}
        else: result = report(con, limit=args.limit)
    print(dumps({'historical_replay': bool(args.at), 'result': result, 'trading_authorized': False}))
    return 2 if result.get('status') == 'UNOBSERVABLE' else 0
