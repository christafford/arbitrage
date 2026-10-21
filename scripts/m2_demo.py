"""HYPOTHETICAL M2 acceptance exercise; never reviews or approves real instruments.

Run from repository root: .venv/bin/python scripts/m2_demo.py --db data/m2-demo.sqlite3
The database must be empty. Generated review forms and exact CLI output remain local.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sys

from predarb.cli import main
from predarb.registry import CHECKS, SCENARIOS


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--db', required=True)
args = parser.parse_args()
artifacts = Path(args.db).parent / (Path(args.db).stem + '-artifacts')
artifacts.mkdir(parents=True, exist_ok=False)
trace = []


def invoke(*argv, expected=0):
    out, err = StringIO(), StringIO()
    sys.argv = ['predarb', 'pairs', *argv, '--db', args.db]
    with redirect_stdout(out), redirect_stderr(err):
        status = main()
    result = json.loads(out.getvalue()) if out.getvalue() else None
    trace.append({'argv': sys.argv[1:], 'exit_code': status, 'stdout': result, 'stderr': err.getvalue()})
    if status != expected:
        raise RuntimeError(f'HYPOTHETICAL demo command failed: {argv}: {err.getvalue()}')
    return result


def form(pair_id, filename, *, different=False):
    path = artifacts / filename
    invoke('review', str(pair_id), '--template-output', str(path))
    data = json.loads(path.read_text())
    data.update(reviewer='HYPOTHETICAL reviewer (simulated CLI test)', human_reviewed=True,
                reason='HYPOTHETICAL ONLY: explicit comparison of synthetic terms',
                expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                outcome_mapping={'YES': 'YES', 'NO': 'NO'},
                legs={'kalshi': 'YES', 'polymarket_us': 'NO'})
    for key in CHECKS:
        data['comparisons'][key] = {'equivalent': True, 'rationale': 'HYPOTHETICAL fixture: both specified terms agree for ' + key}
    if different:
        data['comparisons']['thresholds_revisions'] = {
            'equivalent': False, 'rationale': 'FINAL report including revisions differs from FIRST report excluding revisions'}
    for case in SCENARIOS:
        normal = case in {'YES', 'NO'}
        data['settlement_scenarios'].append({
            'case': case, 'condition': 'HYPOTHETICAL explicit fixture condition: ' + case,
            'kalshi_payout': ('1' if case == 'YES' else '0') if normal else '0.50',
            'polymarket_us_payout': ('0' if case == 'YES' else '1') if normal else '0.50',
            'kalshi_settlement_at': '2030-07-04T12:00:00Z',
            'polymarket_us_settlement_at': '2030-07-04T12:00:00Z'})
    path.write_text(json.dumps(data, indent=2) + '\n')
    return path


invoke('load-example', '--fixture', 'examples/M2_HYPOTHETICAL.json')
suggestions = invoke('candidates')
assert len(suggestions) == 2 and all(row['status'] == 'UNVERIFIED' for row in suggestions)
bad = invoke('propose', '--kalshi', 'HYPOTHETICAL-K', '--polymarket-us', 'HYPOTHETICAL-P-DIFFERENT',
             '--operator', 'HYPOTHETICAL proposer')['pair_id']
bad_form = form(bad, 'different-review.json', different=True)
invoke('approve', str(bad), '--review-file', str(bad_form), '--human-review', expected=1)
assert invoke('reject', str(bad), '--operator', 'HYPOTHETICAL reviewer', '--reason',
              'FIRST vs FINAL report and different revision cutoffs')['status'] == 'REJECTED'

pair_id = invoke('propose', '--kalshi', 'HYPOTHETICAL-K', '--polymarket-us', 'HYPOTHETICAL-P',
                 '--operator', 'HYPOTHETICAL proposer')['pair_id']
review = form(pair_id, 'matching-review.json')
assert invoke('approve', str(pair_id), '--review-file', str(review), '--human-review')['status'] == 'APPROVED'
assert invoke('revoke', str(pair_id), '--operator', 'HYPOTHETICAL reviewer',
              '--reason', 'HYPOTHETICAL withdrawal for fresh review')['status'] == 'REVOKED'

changed = invoke('propose', '--kalshi', 'HYPOTHETICAL-K', '--polymarket-us', 'HYPOTHETICAL-P',
                 '--operator', 'HYPOTHETICAL proposer')['pair_id']
changed_form = form(changed, 'changed-review.json')
assert invoke('approve', str(changed), '--review-file', str(changed_form), '--human-review')['status'] == 'APPROVED'
source = artifacts / 'changed-terms.txt'
source.write_text('HYPOTHETICAL ONLY: amendment now uses first report without revisions.\n')
invoke('document', '--venue', 'kalshi', '--source-id', 'HYPOTHETICAL-K',
       '--url', 'https://example.invalid/HYPOTHETICAL-K', '--source-file', str(source), '--text-file', str(source),
       '--retrieved-at', datetime.now(timezone.utc).isoformat(), '--operator', 'HYPOTHETICAL importer')
assert invoke('review', str(changed))['status'] == 'INVALIDATED'
final = invoke('list')
audit = invoke('audit')
assert [pair['status'] for pair in final] == ['REJECTED', 'REVOKED', 'INVALIDATED']
assert all(pair['hypothetical'] and not pair['trading_authorized'] for pair in final)
(artifacts / 'cli-trace.json').write_text(json.dumps({'hypothetical': True, 'commands': trace}, indent=2) + '\n')
print(json.dumps({'hypothetical': True, 'candidate_statuses': [row['status'] for row in suggestions],
                  'final_pairs': [{'pair_id': pair['id'], 'status': pair['status']} for pair in final],
                  'audit_events': len(audit), 'trading_authorized': False, 'trace': str(artifacts/'cli-trace.json')}, indent=2))
