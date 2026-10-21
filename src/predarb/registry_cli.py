"""Local operator CLI for evidence and pair decisions; no network or execution path."""
from pathlib import Path
from . import registry
from .store import connect
from .validation import dumps, load_json


def _read(path, cap=2_000_000):
    with Path(path).open('rb') as stream:
        data = stream.read(cap + 1)
    if not 0 < len(data) <= cap:
        raise ValueError(f'{path}: file must contain 1..{cap} bytes')
    return data


def add_parser(subparsers):
    root = subparsers.add_parser('pairs', help='human-reviewed local pair registry; no trading')
    commands = root.add_subparsers(dest='pair_cmd', required=True)
    for command in ('candidates', 'document', 'propose', 'review', 'approve', 'reject', 'revoke', 'list', 'audit', 'load-example'):
        parser = commands.add_parser(command)
        parser.add_argument('--db', default='data/research.sqlite3')
        if command in {'propose', 'document', 'reject', 'revoke'}:
            parser.add_argument('--operator', required=True)
        if command in {'review', 'approve', 'reject', 'revoke'}:
            parser.add_argument('pair_id', type=int)
        if command == 'candidates':
            parser.add_argument('--limit', type=int, default=20)
            parser.add_argument('--max-instruments', type=int, default=500)
        elif command == 'document':
            parser.add_argument('--venue', choices=registry.VENUES, required=True)
            parser.add_argument('--source-id', required=True)
            parser.add_argument('--url', required=True)
            parser.add_argument('--source-file', required=True, help='original official source bytes, e.g. PDF')
            parser.add_argument('--text-file', required=True, help='exact UTF-8 resolution text/extraction')
            parser.add_argument('--retrieved-at', required=True, help='original source retrieval timestamp with UTC offset')
        elif command == 'propose':
            parser.add_argument('--kalshi', required=True)
            parser.add_argument('--polymarket-us', required=True)
        elif command == 'review':
            parser.add_argument('--template-output', help='write an unapproved review form (will not overwrite)')
        elif command == 'approve':
            parser.add_argument('--review-file', required=True)
            parser.add_argument('--human-review', action='store_true', help='attest that a human performed this review')
        elif command in {'reject', 'revoke'}:
            parser.add_argument('--reason', required=True)
        elif command == 'audit':
            parser.add_argument('--pair-id', type=int)
        elif command == 'load-example':
            parser.add_argument('--fixture', required=True, help='HYPOTHETICAL fixture; requires empty isolated database')


def run(args):
    with connect(args.db) as con:
        command = args.pair_cmd
        if command == 'candidates':
            result = registry.candidates(con, limit=args.limit, max_instruments=args.max_instruments)
        elif command == 'document':
            result = {'document_id': registry.import_document(con, args.venue, args.source_id, args.url,
                      _read(args.source_file), _read(args.text_file), args.retrieved_at, args.operator)}
        elif command == 'propose':
            result = {'pair_id': registry.propose(con, args.kalshi, args.polymarket_us, args.operator),
                      'status': 'UNVERIFIED'}
        elif command == 'review':
            result = registry.review(con, args.pair_id)
            if args.template_output:
                template = registry.review_template(con, args.pair_id)
                with Path(args.template_output).open('x') as stream:
                    stream.write(dumps(template) + '\n')
        elif command == 'approve':
            result = registry.approve(con, args.pair_id, load_json(_read(args.review_file)), human_attested=args.human_review)
        elif command in {'reject', 'revoke'}:
            result = registry.decide(con, args.pair_id, 'REJECTED' if command == 'reject' else 'REVOKED',
                                     args.operator, args.reason)
        elif command == 'list':
            result = registry.list_pairs(con)
        elif command == 'audit':
            result = registry.audit(con, args.pair_id)
        else:
            result = registry.load_hypothetical(con, load_json(_read(args.fixture)))
    print(dumps(result))
    return 0
