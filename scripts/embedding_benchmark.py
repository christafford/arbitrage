#!/usr/bin/env python3
"""HYPOTHETICAL retrieval benchmark. --live measures the configured real model."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time

from predarb import discovery, embeddings, registry
from predarb.store import connect
from predarb.validation import dumps, utc_time

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/embeddings-hypothetical.json'


class HypotheticalResponse(BytesIO):
    status = 200
    headers = {'Content-Type': 'application/json'}


class HypotheticalService:
    def __init__(self, fixture):
        self.fixture = fixture
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if request.full_url.endswith('/models'):
            payload = self.fixture['models']
        else:
            body = json.loads(request.data)
            rows = []
            for i, text in enumerate(body['input']):
                values = [-1, -1, -1, -1, -1, -1]
                if text == embeddings.PROBE:
                    values = [1, 0, 0, 0, 0, 0]
                else:
                    contract = json.loads(text)['public_contract']
                    title = contract.get('title') or contract.get('question')
                    for case in self.fixture['cases']:
                        if title in (case['left'], case['right']):
                            values = case['vector']
                rows.append({'object': 'embedding', 'index': i, 'embedding': values})
            payload = {'object': 'list', 'model': body['model'], 'data': list(reversed(rows))}
        return HypotheticalResponse(dumps(payload).encode())


def seed(con, fixture):
    now = utc_time(fixture['clock'])
    for case in fixture['cases']:
        for venue, key in [('kalshi', 'left'), ('polymarket_us', 'right')]:
            registry._record_instrument(con, venue, 'HYPOTHETICAL-' + case['id'],
                {'title': case[key], 'description': '', 'close_time': '2030-02-01T00:00:00Z'},
                observed_at=now.isoformat(), available=True, hypothetical=True, now=now)
    for i, title in enumerate(fixture['negative_titles']):
        registry._record_instrument(con, 'polymarket_us', 'HYPOTHETICAL-negative-' + str(i),
            {'title': title, 'description': '', 'close_time': '2030-02-01T00:00:00Z'},
            observed_at=now.isoformat(), available=True, hypothetical=True, now=now)


def benchmark(con, fixture, client, k=3):
    seed(con, fixture)
    results = {}
    for name, source in [('deterministic', None), ('embedding_assisted', client)]:
        started = time.monotonic()
        report = discovery.discover(con, now=utc_time(fixture['clock']), limit=1000, embedding_client=source)
        retrieved, hits, per_query = 0, 0, []
        for case in fixture['cases']:
            identity = 'HYPOTHETICAL-' + case['id']
            rows = [r for r in report['candidates'] if r['kalshi_id'] == identity][:k]
            hit = any(r['polymarket_us_id'] == identity for r in rows)
            hits += hit
            retrieved += len(rows)
            per_query.append({'query': identity, 'hit': hit, 'retrieved': [r['polymarket_us_id'] for r in rows]})
            assert all(r['status'] == 'UNVERIFIED' and not r['trading_authorized'] for r in rows)
        results[name] = {'recall_at_k': hits / len(fixture['cases']),
                         'precision_at_returned': hits / retrieved if retrieved else 0,
                         'hits': hits, 'relevant_pairs': len(fixture['cases']), 'returned': retrieved,
                         'seconds': time.monotonic() - started, 'embedding': report['embedding'], 'queries': per_query}
    return {'schema': 'embedding-retrieval-benchmark/v1', 'hypothetical_corpus': True,
            'k': k, 'generated_at': datetime.now(timezone.utc).isoformat(), 'results': results,
            'limitation': 'Small hand-labeled review-relevance corpus, no equivalence approvals; offline vectors test plumbing only.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='infer fixture text on PREDARB_EMBEDDING_URL')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text())
    with tempfile.TemporaryDirectory() as directory, closing(connect(str(Path(directory) / 'benchmark.sqlite3'))) as con:
        if args.live:
            client = embeddings.from_environment(con)
            if client is None:
                parser.error('--live requires PREDARB_EMBEDDING_URL')
        else:
            client = embeddings.Client(con, embeddings.Config('https://hypothetical.invalid'), opener=HypotheticalService(fixture))
        report = benchmark(con, fixture, client)
        report['inference'] = 'LIVE_MODEL' if args.live else 'HYPOTHETICAL_VECTORS'
        report['model_quality_measured'] = args.live and report['results']['embedding_assisted']['embedding']['status'] == 'READY'
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    print(encoded)
    return 0 if report['results']['embedding_assisted']['embedding']['status'] == 'READY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
