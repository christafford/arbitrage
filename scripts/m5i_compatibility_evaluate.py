"""Offline genuine proposition audit. Unknown cross-pairs are never negative labels."""
import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from predarb import discovery as d, semantic as s, propositions as p
from predarb.store import connect
from predarb.validation import utc_time
from m5i_evaluate import seed

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/m5i-compatibility-genuine.json'
BASELINE=ROOT/'tests/fixtures/m5i-propositions-v2.py'
BASELINE_RETRIEVAL=ROOT/'tests/fixtures/m5i-semantic-before-v3.py'


def validate(corpus):
    if corpus.get('hypothetical') is not False or corpus.get('operator_approved') is not False:
        raise ValueError('genuine unapproved corpus required')
    if not 1<=len(corpus['cases'])<=500 or not 1<=len(corpus['instruments'])<=500:
        raise ValueError('bounded corpus required')
    seen=set();ids={(x['venue'],x['source_id']) for x in corpus['instruments']}
    for c in corpus['cases']:
        key=c['kalshi_id'],c['polymarket_us_id']
        if key in seen:raise ValueError('duplicate/contradictory pair label')
        seen.add(key)
        if any(type(c[name]) is not bool for name in ('retrieval_relevant','proposition_conflict_expected')):
            raise ValueError('explicit boolean labels required')
        if any((v,c[v+'_id']) not in ids for v in ('kalshi','polymarket_us')):raise ValueError('missing labeled definition')


@contextmanager
def guards(module,retriever=s):
    previous=d.propositions,s.propositions,retriever.propositions
    d.propositions=s.propositions=retriever.propositions=module
    try:yield
    finally:d.propositions,s.propositions,retriever.propositions=previous


def metrics(cases,retrieved):
    labels={(x['kalshi_id'],x['polymarket_us_id']):x for x in cases}
    out={}
    for k in (20,100):
        returned={};clean={}
        for query,rows in retrieved.items():
            # Filter within the actual top-k; do not refill to improve metrics.
            for row in rows[:k]:
                key=row['kalshi_id'],query;returned[key]=row
                if not row['known_contradictions']:clean[key]=row
        positives={key for key,c in labels.items() if c['retrieval_relevant']}
        compatible={key for key in positives if not labels[key]['proposition_conflict_expected']}
        def precision(rows):
            judged=set(rows)&set(labels);tp=sum(labels[key]['retrieval_relevant'] for key in judged)
            return dict(returned=len(rows),labeled=len(judged),unlabeled=len(rows)-len(judged),
                        true_positive=tp,false_positive=len(judged)-tp,
                        precision_labeled=tp/len(judged) if judged else None)
        missed=positives-set(returned)
        out[str(k)]={'relevant_total':len(positives),'found':len(positives&set(returned)),
            'recall':len(positives&set(returned))/len(positives) if positives else None,
            'false_negative_categories':dict(Counter(labels[key]['category'] for key in missed)),
            'missed_pairs':[dict(labels[key]) for key in sorted(missed)],'raw':precision(returned),'unflagged':precision(clean),
            'compatible_relevant_total':len(compatible),'compatible_relevant_unflagged':len(compatible&set(clean)),
            'compatible_relevant_flagged':[dict(labels[key],warnings=returned[key]['known_contradictions']) for key in sorted((compatible&set(returned))-set(clean))]}
    return out


def run(corpus,directory):
    validate(corpus);now=utc_time(corpus['created_at'])
    spec=importlib.util.spec_from_file_location('frozen_m5i_v2',BASELINE)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    spec=importlib.util.spec_from_file_location('predarb.frozen_m5i_semantic',BASELINE_RETRIEVAL)
    old_retriever=importlib.util.module_from_spec(spec);spec.loader.exec_module(old_retriever)
    directory.mkdir(parents=True,exist_ok=False);output={}
    with connect(str(directory/'source.sqlite3')) as source,connect(str(directory/'index.sqlite3')) as index:
        seed(source,corpus);s.sync(source,index,now=now)
        documents={(row['venue'],row['source_id']):row for row in s.rows(index,'SELECT * FROM semantic_documents')}
        # Labels must not conceal stale/unsupported definitions as retrieval misses.
        ineligible=[{'venue':v,'source_id':sid,'reason':r['reason']} for (v,sid),r in documents.items() if s.current(source,r,now,s.venue_context(source)) is None]
        if ineligible:raise ValueError('ineligible evaluation definitions: '+json.dumps(ineligible))
        for name,module,legacy,retriever in (('deterministic_v2',baseline,True,s),('indexed_v2',baseline,False,old_retriever),('indexed_v3',p,False,s)):
            start=time.monotonic();retrieved={};triage=[]
            with guards(module,retriever):
                if legacy:
                    report=d.discover(source,now=now,limit=1000)
                    for row in report['candidates']:
                        row['known_contradictions']=[w for w in row['warnings'] if 'CONFLICT' in w or w=='RESOLUTION_LANGUAGE_DIFFERS']
                        retrieved.setdefault(row['polymarket_us_id'],[]).append(row)
                else:
                    for query in sorted({c['polymarket_us_id'] for c in corpus['cases']}):
                        retrieved[query]=retriever.retrieve(source,index,now=now,limit=100,query_budget=1,
                            query_ids=[('polymarket_us',query)],semantic=False,persist=False)['candidates']
                for c in corpus['cases']:
                    docs=[documents[(v,c[v+'_id'])] for v in ('kalshi','polymarket_us')]
                    f=[s.decode_features(row['features_json']) for row in docs]
                    for features,doc in zip(f,docs):features['proposition']=module.from_public_text(doc['public_text'])
                    comparison=d.compare(*f,semantic=True)
                    warnings=comparison[2] if comparison else ['REJECTED_BY_EXISTING_IDENTITY_GATE']
                    flagged=comparison is None or any('CONFLICT' in w or w=='RESOLUTION_LANGUAGE_DIFFERS' for w in warnings)
                    guard_warnings=module.compare(f[0]['proposition'],f[1]['proposition'])
                    triage.append(dict(c,flagged=flagged,warnings=warnings,guard_warnings=guard_warnings,
                                       guard_flagged=any('CONFLICT' in w for w in guard_warnings),
                                       sports=any(x.get('sports') is not None for x in f)))
            measured=metrics(corpus['cases'],retrieved)
            for result in measured.values():
                for label in result['missed_pairs']:
                    docs=[documents[(v,label[v+'_id'])] for v in ('kalshi','polymarket_us')]
                    gap=abs((utc_time(docs[0]['horizon_end'])-utc_time(docs[1]['horizon_end'])).total_seconds()) if all(x['horizon_end'] for x in docs) else None
                    label['miss_stage']='SETTLEMENT_HORIZON_FILTER' if not legacy and gap is not None and gap>90*86400 else 'RETRIEVAL_RANKING_OR_DIVERSITY'
                    label['administrative_horizon_gap_days']=gap/86400 if gap is not None else None
            counts=Counter(('expected_conflict_flagged' if c['flagged'] else 'missed_conflict') if c['proposition_conflict_expected'] else ('ordinary_control_with_material_warning' if c['flagged'] else 'unflagged_control') for c in triage)
            guard_counts=Counter(('true_positive' if c['guard_flagged'] else 'false_negative') if c['proposition_conflict_expected'] else ('false_positive' if c['guard_flagged'] else 'true_negative') for c in triage if not c['sports'])
            output[name]={'guard_version':module.VERSION,'elapsed_seconds':time.monotonic()-start,
                'retrieval':measured,'triage_counts':dict(counts),
                'non_sports_guard_confusion':{k:guard_counts[k] for k in ('true_positive','false_negative','true_negative','false_positive')},
                'triage':triage,'retrieved':retrieved}
        approvals=source.execute('SELECT count(*) FROM pairs').fetchone()[0]
        assert approvals==0
    return {'schema':'m5i-compatibility-evaluation/v1','clock':now.isoformat(),'hypothetical':False,
        'dataset_sha256':hashlib.sha256(json.dumps(corpus,sort_keys=True).encode()).hexdigest(),
        'baseline_sha256':hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
        'baseline_retrieval_sha256':hashlib.sha256(BASELINE_RETRIEVAL.read_bytes()).hexdigest(),
        'current_guard_sha256':hashlib.sha256(Path(p.__file__).read_bytes()).hexdigest(),
        'current_retrieval_sha256':hashlib.sha256(Path(s.__file__).read_bytes()).hexdigest(),
        'label_author':corpus['annotation_author'],'operator_approved':False,'sampling':corpus['sampling'],
        'cases':len(corpus['cases']),'instruments':len(corpus['instruments']),'new_inference_requests':0,'registry_approvals':approvals,
        'limits':'Small purposive development corpus, not held out or independently adjudicated. Unlabeled pairs excluded from precision, with counts shown. Raw recall includes conflict-flagged same-event candidates. False-conflict labels concern ordinary propositions, not approval of settlement rules. No vector/model-quality or venue-wide recall claim.',
        'variants':output}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(json.loads(FIXTURE.read_text()),args.directory)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:dict(triage=v['triage_counts'],recall20=v['retrieval']['20']['recall'],unflagged=v['retrieval']['20']['unflagged']) for k,v in report['variants'].items()},indent=2))


if __name__=='__main__':main()
