"""Read-only M5O/M5P reconstruction; output must be a new directory."""
import argparse
from collections import Counter
from contextlib import closing
from dataclasses import fields
from decimal import Decimal
import hashlib
from pathlib import Path

from predarb.backups import readonly
from predarb.continuous_research import archived_visibility, observation
from predarb.economic_signals import Episodes, VERSION, reconstruct
from predarb.models import AskLevel
from predarb.orderbooks import Book, PriceBand
from predarb.quality_capture import replay
from predarb.quality_recovery import json_lines, verify_raw
from predarb.soak import atomic_json
from predarb.validation import dumps, load_json, utc_time


def typed_book(data):
    values={f.name:data[f.name] for f in fields(Book)}
    for key in ('yes_asks','no_asks'):
        values[key]=tuple(AskLevel(Decimal(x['price']),Decimal(x['quantity'])) for x in values[key])
    values['price_bands']=tuple(PriceBand(**{k:Decimal(v) for k,v in x.items()}) for x in values['price_bands'])
    for key in ('quantity_step','minimum_quantity'):
        values[key]=Decimal(values[key]) if values[key] is not None else None
    values['rejections']=tuple(values['rejections'])
    return Book(**values)


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def summarize(rows, folder, pair, channel, audit, counts, wall):
    episodes=Episodes()
    for row in rows:episodes.add(row)
    clusters=episodes.report()
    positive=[r for r in rows if any(c['positive_gross_signal'] for c in r.get('capital_cases',[]))]
    best=max(positive,key=lambda r:max(Decimal(c['gross_edge_usd']) for c in r['capital_cases']),default=None)
    compact=[]
    for e in clusters:
        b=e.pop('best_observation')
        e['best_at']=b['at'];e['best_provenance']=b['provenance']
        compact.append(e)
    return dict(source=str(folder),pair=pair,channel=channel,audit=audit,counts=dict(counts),
        positive_samples=len(positive),distinct_positive_source_states=len(episodes.states),
        distinct_positive_depth_states=len(episodes.depths),episodes=compact,best=best,
        wall_coverage=wall,net_profitability='UNKNOWN',trading_authorized=False)


def m5p_window(root):
    config=load_json((root/'config.json').read_bytes())
    for pair in config['pairs']:
        folder=root/pair['id'];rows={c:[] for c in ('us_ws','us_rest')};counts={c:Counter() for c in rows}
        def sample(saved,engine):
            channel=saved['channel'];counts[channel]['samples']+=1
            if not saved['quality']['timestamp_depth_overlap']:
                rows[channel].append(dict(at=saved['at'],quality=saved['quality']))
                return
            states=[engine.states[c] for c in ('kalshi',channel)]
            p=dict(pair)
            if any(s.source_changed for s in states):p['classification']='DISCOVERY'
            books=[s.book for s in states];at=utc_time(saved['at'])
            row=reconstruct(books,p,at=at,inspected=[b.as_dict(now=at) for b in books],
                provenance=dict(archive=str(folder),channel=channel,event_number=saved['event_number'],event_sha256=saved['event_sha256']))
            if not row['quality']['timestamp_depth_overlap']:raise ValueError('reconstruction changed quality pass')
            rows[channel].append(row);counts[channel]['quality_passes']+=1
        try:
            audit=replay(folder,pair,config,sample_observer=sample)
            result=load_json((folder/'result.json').read_bytes())
            for channel in rows:
                yield summarize(rows[channel],folder,pair,channel,audit,counts[channel],dict(
                    seconds=result['valid_local_market_state_seconds'][channel],
                    percent=result['valid_local_market_state_percent'][channel],
                    planned_seconds=config['seconds'])),rows[channel]
        except (ValueError,KeyError,OSError) as exc:
            yield dict(source=str(folder),pair=pair,audit={'replay':'FAIL','error':str(exc)},
                       quarantined=True,trading_authorized=False),[]


def m5o_window(root):
    config=load_json((root/'config.json').read_bytes())
    for pair in config['pairs']:
        worker=root/pair['id']
        if not worker.exists():continue
        for folder in sorted(worker.glob('segment-*')):
            if not (folder/'observations.jsonl').exists():continue
            rows=[];counts=Counter()
            try:
                old=load_json((folder/'audit.json').read_bytes())
                if old['replay']!='PASS':raise ValueError('historical segment audit failed')
                hashes=sum(verify_raw(folder/name) for name in ('kalshi.sqlite3','us.sqlite3'))
                with closing(readonly(folder/'kalshi.sqlite3')) as kc,closing(readonly(folder/'us.sqlite3')) as uc:
                    for saved in json_lines(folder/'observations.jsonl'):
                        counts['samples']+=1
                        if not saved.get('quality',{}).get('timestamp_depth_overlap'):
                            rows.append(dict(at=saved['at'],quality=saved.get('quality',{})))
                            continue
                        at=utc_time(saved['at'])
                        with archived_visibility(kc,saved['archive_visibility']['kalshi']),archived_visibility(uc,saved['archive_visibility']['polymarket_us']):
                            rebuilt=observation(kc,uc,pair,at,synchronized=saved['clock_synchronized'])
                        if load_json(dumps(rebuilt))!={k:saved[k] for k in rebuilt}:raise ValueError('M5O observation mismatch')
                        books=[typed_book(b) for b in rebuilt['displayed_books']]
                        p=dict(pair,classification=rebuilt['classification'])
                        row=reconstruct(books,p,at=at,inspected=rebuilt['displayed_books'],
                            provenance=dict(archive=str(folder),sources=rebuilt['sources'],
                                archive_visibility=saved['archive_visibility']))
                        rows.append(row);counts['quality_passes']+=1
                audit=dict(replay='PASS',new_quality_passing_sample_replays=counts['quality_passes'],
                    raw_hashes_verified=hashes,historical_full_segment_audit_sha256=digest(folder/'audit.json'),
                    rejected_samples='Historical classifications retained; not newly semantically replayed')
                yield summarize(rows,folder,pair,'us_rest',audit,counts,None),rows
            except (ValueError,KeyError,OSError) as exc:
                yield dict(source=str(folder),pair=pair,audit={'replay':'FAIL','error':str(exc)},
                    quarantined=True,trading_authorized=False),[]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,action='append',help='Specific window(s); default all M5O/M5P configs')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    roots=args.source or sorted([*Path('data/m5o').rglob('config.json'),*Path('data/m5p').rglob('config.json')])
    roots=[r.parent if r.name=='config.json' else r for r in roots]
    results=[];inputs=[]
    with (args.output/'observations.jsonl').open('w') as output:
        for root in roots:
            config=load_json((root/'config.json').read_bytes())
            # Only actual observation configs, not profiling/output copies.
            if config.get('schema') == 'continuous-conditional-observation/m5o-v1':
                for path in sorted(root.glob('*/segment-*/observations.jsonl')):
                    saved=list(json_lines(path))
                    results.append(dict(source=str(path.parent),quarantined=True,
                        audit=dict(replay='FAIL',error='Historical v1 lacks committed-reader frontier; never promote'),
                        archived_samples=len(saved),archived_quality_passes=sum(bool(r.get('quality',{}).get('timestamp_depth_overlap')) for r in saved)))
                continue
            if config.get('schema') not in {'continuous-conditional-observation/m5o-v2','market-data-quality-recovery/m5p-v1'}:
                raise ValueError('unknown observation configuration schema: '+str(root))
            inputs.append(dict(path=str(root/'config.json'),sha256=digest(root/'config.json')))
            print('REPLAY',root,flush=True)
            iterator=m5p_window(root) if config['schema'].startswith('market-data') else m5o_window(root)
            for summary,rows in iterator:
                for row in rows:
                    if row.get('capital_cases'):output.write(dumps(row)+'\n')
                results.append(summary)
                print(summary['source'],summary.get('channel'),summary['audit']['replay'],summary.get('counts'),flush=True)
    ranked=sorted([r for r in results if r.get('best')],key=lambda r:(
        -max(Decimal(c['gross_edge_usd']) for c in r['best']['capital_cases']),
        -max(Decimal(c['evaluated_quantity']) for c in r['best']['capital_cases']),
        -max(e['sampled_span_seconds'] for e in r['episodes']),r['source'],r['channel']))
    totals=Counter()
    for r in results:
        if r.get('quarantined'):totals['quarantined_workers_or_segments']+=1;continue
        totals.update(r['counts']);totals['positive_samples']+=r['positive_samples'];totals['episodes']+=len(r['episodes'])
    report=dict(schema=VERSION,inputs=inputs,totals=dict(totals),results=results,
        ranking=[dict(source=r['source'],pair=r['pair']['id'],channel=r['channel'],classification=r['best']['classification'],
            max_gross_edge_usd=max(Decimal(c['gross_edge_usd']) for c in r['best']['capital_cases']),
            positive_samples=r['positive_samples'],distinct_depth_states=r['distinct_positive_depth_states'],
            episodes=len(r['episodes']),longest_sampled_span_seconds=max(e['sampled_span_seconds'] for e in r['episodes']),
            settlement_uncertainty=r['pair']['residual_risks']) for r in ranked],
        observations_sha256=digest(args.output/'observations.jsonl'),
        strict_pairs=0,net_profitability='UNKNOWN_UNREVIEWED_FEES_AND_SETTLEMENT',trading_authorized=False)
    atomic_json(args.output/'report.json',report)
    print(dumps(dict(totals=totals,ranking=report['ranking'][:10])))


if __name__=='__main__':main()
