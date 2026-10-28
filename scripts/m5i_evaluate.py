"""Reproducible genuine archived corpus evaluation; retrieval labels are not approvals."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from predarb import discovery, semantic, embeddings, kalshi, polymarket_us, registry
from predarb.provider import Observation
from predarb.store import connect,archive_response,validate_observation,save_entry,start_run,update_run
from predarb.validation import dumps,load_json,utc_time

FIXTURE=Path(__file__).resolve().parents[1]/'tests/fixtures/m5i-genuine-evaluation.json'


def seed(source,corpus):
    if corpus['schema']!='m5i-genuine-evaluation/v1' or corpus['hypothetical'] is not False:raise ValueError('genuine corpus required')
    for venue in registry.VENUES:
        adapter=kalshi if venue=='kalshi' else polymarket_us
        run=start_run(source,venue,adapter.SCHEMA_VERSION,{'filter':'ARCHIVED_EVALUATION_CORPUS','hypothetical':False})
        count=0
        for item in corpus['instruments']:
            if item['venue']!=venue:continue
            body=item['body'].encode()
            if hashlib.sha256(body).hexdigest()!=item['body_sha256']:raise ValueError('corpus excerpt hash mismatch')
            data=load_json(body);adapter.validate_detail(data)
            if data['market'][adapter.ID_FIELD]!=item['source_id']:raise ValueError('corpus identity mismatch')
            raw=archive_response(source,venue,item['source_url'],body,200,{},item['observed_at'],adapter.SCHEMA_VERSION)
            validate_observation(source,raw,'VALID',None)
            save_entry(source,run,Observation(raw,item['source_url'],item['observed_at'],data),item['source_id'],data['market'],adapter.rules(data['market']),data['market'].get(adapter.TIME_FIELD))
            count+=1
        update_run(source,run,status='COMPLETE',pages=count,records=count,unique=count,next_page=None)


def metrics(corpus,retrieved):
    relevant={(x['kalshi_id'],x['polymarket_us_id']):x for x in corpus['positives']}
    queries=sorted({p for _,p in relevant})
    output={}
    for k in (20,100):
        found=set();returned=[];misses=Counter()
        for query in queries:
            selected=retrieved.get(query,[])[:k]
            pairs=[(x['kalshi_id'],x['polymarket_us_id']) for x in selected]
            returned.extend(pairs);found.update(set(pairs)&set(relevant))
        for pair,label in relevant.items():
            if pair not in found:misses[label['category']]+=1
        output[str(k)]={'relevant_found':len(found),'relevant_total':len(relevant),'recall':len(found)/len(relevant),
                        'returned':len(returned),'precision_among_returned':sum(p in relevant for p in returned)/len(returned) if returned else None,
                        'false_negative_categories':dict(misses)}
    output['hard_negative_retrievals']=[dict(x,retrieved=any(r['kalshi_id']==x['kalshi_id'] for r in retrieved.get(x['polymarket_us_id'],[]))) for x in corpus['hard_negatives']]
    return output


def evaluate(source,index,corpus,client=None):
    now=utc_time(corpus['created_at']);seed(source,corpus);semantic.sync(source,index,now=now)
    started=time.monotonic();old=discovery.discover(source,now=now,limit=1000)
    old_time=time.monotonic()-started
    baseline={}
    for row in old['candidates']:baseline.setdefault(row['polymarket_us_id'],[]).append(row)
    worker=semantic.index_batch(index,client,now=now,seconds=120) if client else {'status':'NOT_REQUESTED'}
    # Live inference receipts are newer than historical market receipt clocks;
    # use the later clock only when all definitions still satisfy normal freshness.
    run_at=max(now,registry.now_utc()) if client else now
    if client and (run_at-now).total_seconds()>86400:
        raise ValueError('live inference evaluation corpus is stale; collect a new corpus or use deterministic historical replay')
    improved={}; queries=sorted({x['polymarket_us_id'] for x in corpus['positives']})
    started=time.monotonic()
    for sid in queries:
        improved[sid]=semantic.retrieve(source,index,now=run_at,limit=100,query_budget=1,
                 query_ids=[('polymarket_us',sid)],persist=False)['candidates']
    elapsed=time.monotonic()-started
    def events(reports):
        result=set()
        for candidates in reports.values():
            for row in candidates:
                if (row['kalshi_id'],row['polymarket_us_id']) in {(x['kalshi_id'],x['polymarket_us_id']) for x in corpus['positives']}:
                    contract=load_json(registry._instrument(source,'kalshi',row['kalshi_id'])['evidence_json'])['contract']
                    result.add(contract['event_ticker'])
        return result
    old_events,new_events=events(baseline),events(improved)
    return {'schema':'m5i-evaluation-results/v1','hypothetical':False,'mode':'GENUINE_ARCHIVED_DEFINITIONS_EVENT_RETRIEVAL_ONLY',
       'dataset_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),'evaluated_at':run_at.isoformat(),
       'sampling_limits':corpus['sampling'],'settlement_equivalence_approved':False,
       'baseline':dict(metrics(corpus,baseline),elapsed_seconds=old_time,algorithm=old['algorithm']),
       'improved':dict(metrics(corpus,improved),elapsed_seconds=elapsed,algorithm=semantic.VERSION),
       'inference':worker,'coverage':semantic.coverage(source,index,now=run_at),
       'new_reviewable_events':sorted(new_events-old_events),'baseline_reviewable_events':len(old_events),
       'improved_reviewable_events':len(new_events),'retrieved':improved,
       'model_claim':'Actual Qwen inference' if client else 'Deterministic retrieval only; no model-quality measurement'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--directory',required=True);p.add_argument('--live',action='store_true');a=p.parse_args()
    directory=Path(a.directory);directory.mkdir(parents=True,exist_ok=False)
    corpus=json.loads(FIXTURE.read_text())
    with connect(str(directory/'source.sqlite3')) as source,connect(str(directory/'index.sqlite3')) as index:
        client=embeddings.from_environment(index) if a.live else None
        if a.live and client is None:raise ValueError('private embedding endpoint required')
        report=evaluate(source,index,corpus,client)
    Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    print(dumps({k:v for k,v in report.items() if k not in ('retrieved','coverage')}))
    return 2 if report['inference'].get('status')=='FALLBACK' else 0
if __name__=='__main__':raise SystemExit(main())
