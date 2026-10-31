"""Same-corpus deterministic/actual-vector ablation; independent labels stay pending."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from predarb import semantic as s, embeddings as e, discovery as d
from predarb.store import connect
from predarb.validation import dumps,utc_time
from m5i_evaluate import seed
from m5i_compatibility_evaluate import metrics,validate
from m5l_benchmark import ROOT,INSTRUCTION


def run(benchmark,directory,*,now=None):
    directory.mkdir(parents=True,exist_ok=False)
    corpus=json.loads((ROOT/'tests/fixtures/m5i-compatibility-genuine.json').read_text());validate(corpus)
    replay=now is not None
    now=now or datetime.now(timezone.utc);variants={};review={}
    with connect(str(directory/'source.sqlite3')) as source:
        seed(source,corpus)
        for method in ('deterministic','existing','instruction'):
            path=directory/(method+'.sqlite3')
            if method!='deterministic':
                # Backup retains exact raw inference bodies/receipts, not just vector JSON.
                with closing(sqlite3.connect('file:'+str((benchmark/f'{method}-b32.sqlite3').resolve())+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(path)) as dest:original.backup(dest)
            with connect(str(path)) as index:
                s.sync(source,index,now=now)
                docs=list(s.rows(index,'SELECT * FROM semantic_documents'))
                if len(docs)!=60 or any(s.current(source,row,now,s.venue_context(source)) is None for row in docs):
                    raise ValueError('corpus no longer fresh/eligible: use a new corpus; do not renew source timestamps')
                if method!='deterministic':
                    data=json.loads((benchmark/f'{method}-b32-vectors.json').read_text())
                    runlog=json.loads((benchmark/'results.json').read_text())
                    measured=next(r for r in runlog['direct'] if r['method']==method and r['batch_size']==32)
                    dimensions=measured['probes'][-1]['dimensions']
                    if measured['probes'][-1]['identity']!=data['identity']:
                        raise ValueError('model provenance mismatch')
                    ids=measured['samples'][-1]['raw_observations']
                    lookup={tuple(key):i for i,key in enumerate(data['source_ids'])}
                    namespace=data['namespace'];s.set_state(index,'active_identity',namespace)
                    expected_namespace=e.digest(dumps([data['identity'],method,INSTRUCTION if method=='instruction' else e.TEXT_VERSION]))
                    if namespace!=expected_namespace:raise ValueError('method namespace mismatch')
                    index.execute('INSERT INTO semantic_models VALUES(?,?,?,?)',(namespace,'qwen3-embedding-8b',dimensions,now.isoformat()))
                    for doc in docs:
                        i=lookup[(doc['venue'],doc['source_id'])]
                        raw=ids[i//32]
                        created,body,sha=index.execute('SELECT ts_utc,raw_body,body_sha256 FROM raw_observations WHERE id=?',(raw,)).fetchone()
                        if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('inference raw hash mismatch')
                        payload=json.loads(body)
                        items=[x for x in payload['data'] if x['index']==i%32]
                        if payload['model']!=measured['probes'][-1]['model'] or len(items)!=1:raise ValueError('inference identity/index mismatch')
                        values=e.vector(items[0]['embedding'],dimensions)
                        if list(values)!=data['vectors'][i]:raise ValueError('vector export differs from raw inference')
                        blob=s.pack(values);content=data['text_hashes'][i]
                        expected_text=doc['public_text']
                        if method=='instruction' and doc['venue']=='polymarket_us':expected_text=f'Instruct: {INSTRUCTION}\nQuery: {expected_text}'
                        if e.digest(expected_text)!=content:raise ValueError('input text hash mismatch')
                        index.execute('UPDATE semantic_documents SET content_hash=? WHERE id=?',(content,doc['id']))
                        index.execute('INSERT INTO semantic_vectors VALUES(?,?,?,?,?,?,?)',(namespace,content,dimensions,blob,hashlib.sha256(blob).hexdigest(),raw,created))
                        index.executemany('INSERT INTO semantic_buckets VALUES(?,?,?,?)',[(namespace,b,k,content) for b,k in s.signatures(values)])
                    index.commit()
                start=time.perf_counter();retrieved={};stats=Counter()
                for query in sorted({c['polymarket_us_id'] for c in corpus['cases']}):
                    report=s.retrieve(source,index,now=now,limit=100,query_budget=1,query_ids=[('polymarket_us',query)],
                        semantic=method!='deterministic',persist=False)
                    retrieved[query]=report['candidates'];stats.update({k:report['retrieval'][k] for k in ('queries','bucket_saturations','vector_failures')})
                measured=metrics(corpus['cases'],retrieved)
                positives={(c['kalshi_id'],c['polymarket_us_id']) for c in corpus['cases'] if c['retrieval_relevant']}
                events={r['event_key'] for rows in retrieved.values() for r in rows if (r['kalshi_id'],r['polymarket_us_id']) in positives}
                variants[method]={'metrics':measured,'events':sorted(events),'retrieved':retrieved,'seconds':time.perf_counter()-start,
                    'query_stats':dict(stats),'coverage':s.coverage(source,index,now=now)}
                for c in corpus['cases']:
                    key=c['kalshi_id'],c['polymarket_us_id']
                    packet=review.setdefault(key,{'kalshi_id':key[0],'polymarket_us_id':key[1],
                        'sampling_stratum':c['category'],'retrieved_by':[],'assistant_relevance':c['retrieval_relevant'],
                        'independent_reviewer':None,'independent_same_event':None,'independent_conflict':None,
                        'reviewed_at':None,'settlement_approval':False})
                    if any(r['kalshi_id']==key[0] for r in retrieved.get(key[1],[])):packet['retrieved_by'].append(method)
        evidence={(r['venue'],r['source_id']):r for r in corpus['instruments']}
        for packet in review.values():
            packet['definitions']=[evidence[(venue,packet[venue+'_id'])] for venue in ('kalshi','polymarket_us')]
        for method in ('existing','instruction'):
            variants[method]['new_labeled_distinct_events']=sorted(set(variants[method]['events'])-set(variants['deterministic']['events']))
    result={'schema':'m5l-discovery-evaluation/v1','at':now.isoformat(),'corpus_sha256':e.digest(dumps(corpus)),
        'historical_replay':replay,
        'variants':variants,'independent_adjudication':'PENDING_OPERATOR_REQUEST',
        'limits':'Purposive development corpus. Metrics restricted to explicit assistant labels. Unlisted pairs UNLABELED. Not production precision/recall; not settlement equivalence. Candidate pools and warnings unchanged.',
        'instruction':INSTRUCTION,'new_inference_requests':0,'trading_authorized':False}
    (directory/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (directory/'review-packet.json').write_text(json.dumps({'schema':'m5l-independent-review/v1',
        'sampling':'All 42 development pairs including retrieved, missed and hard negatives; category coverage is purposive, not representative of venue census.',
        'instructions':'Review ordinary event/outcome identity independently from assistant label. Keep legal equivalence separate. Null means pending, never false.',
        'pairs':list(review.values())},indent=2)+'\n')
    print(dumps({k:{'recall':v['metrics']['20']['recall'],'raw':v['metrics']['20']['raw'],'new_events':v.get('new_labeled_distinct_events')} for k,v in variants.items()}))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--benchmark',type=Path,required=True);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--at',help='explicit historical replay clock; never renews receipts')
    a=p.parse_args();run(a.benchmark,a.directory,now=utc_time(a.at) if a.at else None)
