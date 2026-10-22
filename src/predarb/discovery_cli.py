"""Bounded public discovery refresh, suitable for a periodic systemd timer."""
from shutil import disk_usage
from contextlib import closing
from pathlib import Path

from . import discovery, kalshi, polymarket_us
from .collector import collect
from .backups import readonly
from .provider import HttpClient
from .store import connect
from .validation import dumps


class SpaceCheckedClient(HttpClient):
    def __init__(self, con, venue, *, min_free_mb, **kwargs):
        super().__init__(con, venue, **kwargs)
        self.directory = Path(con.execute('PRAGMA database_list').fetchone()[2]).parent
        self.min_free_bytes = min_free_mb * 1024 * 1024

    def get(self, *args, **kwargs):
        if disk_usage(self.directory).free < self.min_free_bytes:
            raise OSError('insufficient free disk for discovery archive')
        return super().get(*args, **kwargs)


def add_parser(commands):
    root = commands.add_parser('discovery', help='public US catalogue refresh and human review queue')
    actions = root.add_subparsers(dest='discovery_cmd', required=True)
    for name in ('refresh', 'queue'):
        parser = actions.add_parser(name)
        parser.add_argument('--db', default='data/research.sqlite3')
        parser.add_argument('--limit', type=int, default=20, help='ranked queue size (1..1000)')
        if name == 'refresh':
            parser.add_argument('--offline', action='store_true', help='rebuild queue from existing evidence only')
            parser.add_argument('--page-size', type=int, default=200)
            parser.add_argument('--max-pages', type=int, default=1000, help='per-venue traversal budget; cap reports PARTIAL')
            parser.add_argument('--books', type=int, default=10, help='capture details/books for top N candidates (0..100)')
            parser.add_argument('--request-interval', type=float, default=1.0, help='seconds between requests per venue (minimum .25)')
            parser.add_argument('--min-free-mb', type=int, default=1024)


def refresh(con, *, limit=20, page_size=200, max_pages=1000, books=10,
            request_interval=1.0, client_factory=HttpClient, now=None):
    if not 1 <= limit <= 1000 or not 0 <= books <= 100:
        raise ValueError('limit must be 1..1000 and books 0..100')
    if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 10000:
        raise ValueError('page size must be 1..1000 and max pages 1..10000')
    if not .25 <= request_interval <= 60:
        raise ValueError('request interval must be .25..60 seconds')
    runs, errors, clients = [], [], {}
    blocked_venues = set()
    for adapter in (kalshi, polymarket_us):
        clients[adapter.VENUE] = client_factory(con, adapter.VENUE, interval=request_interval)
        try:
            runs.append(collect(con, adapter, page_size=page_size, max_pages=max_pages,
                                books=0, client=clients[adapter.VENUE], now=now).as_dict())
        except (ValueError, OSError) as exc:
            blocked_venues.add(adapter.VENUE)
            errors.append({'venue': adapter.VENUE, 'stage': 'catalogue', 'error': str(exc)})
    preliminary = discovery.discover(con, limit=limit, now=now)
    captured = set()
    for row in preliminary['candidates'][:books]:
        if row['hypothetical']:
            continue
        for adapter in (kalshi, polymarket_us):
            source_id = row[adapter.VENUE + '_id']
            key = adapter.VENUE, source_id
            if key in captured or adapter.VENUE in blocked_venues:
                continue
            captured.add(key)
            instrument = discovery.registry._instrument(con, adapter.VENUE, source_id)
            from .validation import load_json
            contract = load_json(instrument['evidence_json'])['contract']
            scope = contract['event_ticker'] if adapter is kalshi else source_id
            try:
                runs.append(collect(con, adapter, scope=scope, page_size=page_size,
                                    max_pages=max_pages, books=0, selected=(source_id,),
                                    client=clients[adapter.VENUE], now=now).as_dict())
            except (ValueError, OSError) as exc:
                blocked_venues.add(adapter.VENUE)
                errors.append({'venue': adapter.VENUE, 'source_id': source_id, 'stage': 'detail', 'error': str(exc)})
    report = discovery.refresh_queue(con, limit=limit, now=now,
                _pair_keys=[(r['kalshi_id'], r['polymarket_us_id']) for r in preliminary['candidates']],
                catalogue_coverage_at_refresh=preliminary['coverage'])
    report.update(collection_runs=runs, errors=errors)
    return report, 1 if errors else 2 if any(run['status'] != 'COMPLETE' for run in runs) else 0


def run(args):
    if args.discovery_cmd == 'refresh' and not args.offline:
        if args.min_free_mb < 1:
            raise ValueError('min-free-mb must be positive')
        if disk_usage(Path(args.db).resolve().parent).free < args.min_free_mb * 1024 * 1024:
            raise ValueError('insufficient free disk for discovery archive')
    with (closing(readonly(args.db)) if args.discovery_cmd == 'queue' else connect(args.db)) as con:
        if args.discovery_cmd == 'queue':
            con.execute('BEGIN')  # One consistent read snapshot alongside the writer.
            report, code = discovery.queue(con, limit=args.limit), 0
        elif args.offline:
            report, code = discovery.refresh_queue(con, limit=args.limit), 0
        else:
            report, code = refresh(con, limit=args.limit, page_size=args.page_size, max_pages=args.max_pages,
                                   books=args.books, request_interval=args.request_interval,
                                   client_factory=lambda con, venue, **kw: SpaceCheckedClient(
                                       con, venue, min_free_mb=args.min_free_mb, **kw))
    print(dumps(report))
    return code
