"""Offline M5R evidence. Requires M5Q artifacts; refuses an existing output folder."""
import argparse
from decimal import Decimal as D
from pathlib import Path

from m5q_reconstruct import digest, typed_book
from predarb.quality_capture import replay
from predarb.quality_recovery import json_lines
from predarb.soak import atomic_json
from predarb.validation import load_json, utc_time
from predarb.viability import Attribution, VERSION, sensitivity


def pair_from(row):
    return dict(kalshi_id=row['displayed_books'][0]['source_id'],
        polymarket_us_id=row['displayed_books'][1]['source_id'],
        classification=row['classification'],ordinary_basis=row['ordinary_basis'],
        residual_risks=row['residual_risks'])


def run(source, output):
    output.mkdir(parents=True,exist_ok=False)
    paths = [source/'offline/observations.jsonl', source/'offline/report.json',
             Path('docs/evidence/M5Q_ECONOMICS.json')]
    rows = [r for r in json_lines(paths[0]) if any(c['positive_gross_signal'] for c in r['capital_cases'])
            and '/smoke-' not in r['provenance']['archive']]
    if len(rows) != 196:
        raise ValueError('unexpected M5Q operational positive population')
    workers = {Path(r['provenance']['archive']) for r in rows}
    screen = source/'screen'
    paths.extend(p for p in screen.rglob('*') if p.is_file())
    for worker in sorted(workers):
        paths.extend(p for p in worker.rglob('*') if p.is_file())
    for p in Path('data').glob('m5*/**/config.json'): paths.append(p)
    for p in Path('data').glob('m5*/**/status.json'): paths.append(p)
    # Preserve prior source code/gates too; M5R is an isolated consumer.
    paths.extend(p for p in Path('src/predarb').glob('*.py') if p.name != 'viability.py')
    before = {str(p):digest(p) for p in sorted(set(paths))}
    atomic_json(output/'preservation-before.json', before)
    ranked = load_json(Path('docs/evidence/M5Q_ECONOMICS.json').read_bytes())['ranked']
    best = []
    for group in ranked:
        if not group['positive_samples'] or group['scope'].startswith('DEVELOPMENT'): continue
        target = group['best']['500']
        row = next(r for r in rows if r['at'] == target['at'] and r['provenance'] == target['provenance'])
        books = [typed_book(b) for b in row['displayed_books']]
        cases = []
        for budget in ('5','25','100','500','3000'):
            for fraction in (None,D('.5'),D('.75')):
                cases.append(sensitivity(books,pair_from(row),at=utc_time(row['at']),
                                         budget=D(budget),kalshi_fraction=fraction))
        cases.append(sensitivity(books,pair_from(row),at=utc_time(row['at']),
                                 budget=D(3000),reserve=D(150)))
        best.append(dict(scope=group['scope'],source_ids=group['source_ids'],at=row['at'],
            provenance=row['provenance'],classification=row['classification'],
            historical_timing=target['timing'],cases=cases))
    summaries = {}
    with (output/'all-positive-sensitivities.jsonl').open('w') as f:
        from predarb.validation import dumps
        for row in rows:
            case = sensitivity([typed_book(b) for b in row['displayed_books']],pair_from(row),
                               at=utc_time(row['at']),budget=D(3000))
            f.write(dumps(dict(at=row['at'],provenance=row['provenance'],case=case))+'\n')
            key = row['displayed_books'][0]['source_id']+' / '+row['classification']
            group = summaries.setdefault(key,dict(samples=0,positive_hypothetical_standard_net=0,
                gross_min=None,gross_max=None,net_min=None,net_max=None,quantity_min=None,quantity_max=None))
            group['samples'] += 1
            net = case['cases'][0]['per_level_net_usd']
            group['positive_hypothetical_standard_net'] += int(net > 0)
            for label,value in [('gross',case['gross_usd']),('net',net),('quantity',case['gross_optimal_quantity'])]:
                for suffix,fn in [('min',min),('max',max)]:
                    k=label+'_'+suffix;group[k]=value if group[k] is None else fn(group[k],value)
    config = load_json((screen/'config.json').read_bytes())
    quality = {}
    for pair in config['pairs']:
        engine = Attribution(pair,config['started_at'],config['deadline_at'])
        audit = replay(screen/pair['id'],pair,config,event_observer=engine.event)
        report = engine.report()
        original = load_json((screen/pair['id']/'result.json').read_bytes())
        if report['strict']['valid_local_market_state_seconds']['us_ws'] != D(original['valid_local_market_state_seconds']['us_ws']):
            raise ValueError('original strict coverage changed')
        quality[pair['id']] = dict(audit=audit,**report)
    changed = [p for p,h in before.items() if digest(Path(p)) != h]
    if changed: raise ValueError('source archive changed: '+repr(changed))
    evidence = dict(schema=VERSION,inputs={str(p):digest(p) for p in paths[:3]},
        preservation=dict(files=len(before),changed=changed,manifest=str(output/'preservation-before.json')),
        best_historical=best,all_positive_3000=summaries,quality=quality,
        trading_authorized=False,actual_net_profitability='UNKNOWN',
        actual_fee_applicability='UNKNOWN',actual_fills=0)
    atomic_json(output/'report.json',evidence)
    return evidence


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('data/m5q/run-20261108'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.source,args.output)
    print('M5R offline analysis complete; preserved',result['preservation']['files'],'files; no trading')
