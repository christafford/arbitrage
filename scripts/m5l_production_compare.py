"""Read-only identical-window production retrieval ablation and review sample."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
from predarb import semantic as s,registry
from predarb.backups import readonly
from predarb.validation import dumps,load_json,utc_time


def run(source_path,index_path,output,*,now=None):
    replay=now is not None
    now=now or datetime.now(timezone.utc);reports={}
    with closing(readonly(source_path)) as source,closing(readonly(index_path)) as index:
        if s.state(index,'source_path')!=source.execute('PRAGMA database_list').fetchone()[2]:raise ValueError('binding mismatch')
        if s.state(index,'schema')!=s.VERSION:raise ValueError('unknown semantic schema')
        for enabled in (False,True):
            start=time.perf_counter();r=s.retrieve(source,index,now=now,limit=100,query_budget=250,semantic=enabled,persist=False)
            r['elapsed_seconds']=time.perf_counter()-start;reports['semantic' if enabled else 'deterministic']=r
        sets={name:{(r['kalshi_id'],r['polymarket_us_id']) for r in result['candidates']} for name,result in reports.items()}
        sample=[]
        # Reproducible stratified sampling includes displaced/missed baseline rows.
        for label,keys in [('both',sets['semantic']&sets['deterministic']),('semantic_only',sets['semantic']-sets['deterministic']),('deterministic_only',sets['deterministic']-sets['semantic'])]:
            for key in sorted(keys,key=lambda k:hashlib.sha256(dumps(k).encode()).hexdigest())[:10]:
                definitions=[]
                for venue,sid in zip(registry.VENUES,key):
                    head=registry._instrument(source,venue,sid)
                    raw=source.execute('SELECT endpoint,ts_utc,body_sha256,schema_version FROM raw_observations WHERE id=?',(head['observation_id'],)).fetchone()
                    definitions.append({'venue':venue,'source_id':sid,'version_id':head['version_id'],
                        'contract':load_json(head['evidence_json'])['contract'],'raw_observation_id':head['observation_id'],
                        'source_url':raw[0],'received_at':raw[1],'parent_sha256':raw[2],'schema_version':raw[3]})
                sample.append({'kalshi_id':key[0],'polymarket_us_id':key[1],'stratum':label,'definitions':definitions,
                    'independent_same_event':None,'reviewer':None,'reviewed_at':None,'settlement_approval':False})
    result={'schema':'m5l-production-ablation/v1','at':now.isoformat(),'reports':reports,
        'historical_replay':replay,
        'new_candidate_pairs':[list(x) for x in sorted(sets['semantic']-sets['deterministic'])],
        'new_distinct_same_events':None,'independent_precision':None,'independent_recall':None,
        'review_sample':sample,'sampling':'Up to ten stable-hash pairs per intersection/difference stratum from identical 250-query windows; partial traversal, not a venue-wide random sample.',
        'trading_authorized':False}
    output.write_text(dumps(result)+'\n');print(dumps({k:{'seconds':v['elapsed_seconds'],'count':len(v['candidates']),'retrieval':v['retrieval']} for k,v in reports.items()}))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--index-db',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--at',help='explicit historical replay clock')
    a=p.parse_args();run(a.db,a.index_db,a.output,now=utc_time(a.at) if a.at else None)
