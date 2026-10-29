"""Re-rank a bounded archived queue at its recorded clock, with no network/writes.

Uses archived actual cosine evidence after validating cached vectors. This is a
retrospective ranking regression, not a new live inference or recall benchmark.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path

from predarb import semantic as s, propositions as p, registry
from predarb.backups import readonly
from predarb.validation import utc_time


def replay(source, index, snapshot):
    if len(snapshot['candidates']) > 1000:
        raise ValueError('at most 1000 archived candidates')
    now=utc_time(snapshot['ranked_at']);context=s.venue_context(source)
    results=[];comparisons=[]
    for previous in snapshot['candidates']:
        docs=[next(s.rows(index,'SELECT * FROM semantic_documents WHERE venue=? AND source_id=?',
                         (v,previous[v+'_id'])),None) for v in registry.VENUES]
        if not all(docs) or [x['version_id'] for x in docs]!=previous['versions']:
            raise ValueError('snapshot definitions have changed; use the preserved archive')
        embedding=previous['signals'].get('embedding')
        if embedding:
            for doc in docs:
                vector=next(s.rows(index,'SELECT * FROM semantic_vectors WHERE identity=? AND content_hash=?',
                                   (embedding['identity'],doc['content_hash'])),None)
                if vector is None or not 0 <= (now-utc_time(vector['created_at'])).total_seconds() <= 30*86400:
                    raise ValueError('archived vector unavailable at replay clock')
                s.unpack(vector)
        ranked=s.rank_pair(source,index,*docs,previous['retrieval_reasons'],embedding,now,context)
        if ranked is None:raise ValueError('archived candidate is ineligible at its recorded clock')
        rank,row=ranked;results.append((rank,row))
        comparisons.append({'kalshi_id':row['kalshi_id'],'polymarket_us_id':row['polymarket_us_id'],
            'before':previous['known_contradictions'],'after':row['known_contradictions'],
            'score_before':previous['equivalence_score_bps'],'score_after':row['equivalence_score_bps']})
    return {'mode':'READ_ONLY_HISTORICAL_QUEUE_REPLAY','replay_clock':now.isoformat(),
            'guard_version':p.VERSION,'new_inference_requests':0,
            'candidate_count':len(results),'comparisons':comparisons,
            'candidates':[r for _,r in sorted(results,key=lambda x:x[0])],
            'limit':'Re-ranks the saved queue only; no new-candidate recall or equivalence claim.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True);parser.add_argument('--index-db',required=True)
    parser.add_argument('--snapshot',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.snapshot.stat().st_size>20*1024**2:raise ValueError('snapshot exceeds 20 MiB')
    body=args.snapshot.read_bytes()
    with closing(readonly(args.db)) as source, closing(readonly(args.index_db)) as index:
        result=replay(source,index,json.loads(body))
    result['snapshot_sha256']=hashlib.sha256(body).hexdigest()
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'candidates':result['candidate_count'],
        'newly_flagged':sum(bool(c['after']) and not c['before'] for c in result['comparisons']),
        'replay_clock':result['replay_clock'],'guard_version':p.VERSION}))


if __name__=='__main__':main()
