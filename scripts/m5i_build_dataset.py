"""Export a bounded genuine-definition event-retrieval corpus; no approvals.

Assistant labels are based on explicit participant/date/selection and CPI month,
measure and threshold. They concern ordinary propositions ONLY. Exceptional rule
incompatibilities are separately labeled. All unlisted cross pairs are negatives
in this deliberately narrow corpus, not labels for the rest of the live catalogue.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path

from predarb.backups import readonly
from predarb import registry, sports_discovery as sports, kalshi, polymarket_us
from predarb.validation import dumps, load_json


def build(source):
    now=registry.now_utc(); selected={}; positives=[]; negatives=[]; sports_k={}; sports_p={}
    def row(venue,sid):return registry._instrument(source,venue,sid)
    def add(venue,sid):
        key=(venue,sid)
        if key in selected:return
        r=row(venue,sid)
        raw=registry._one(source,'SELECT * FROM raw_observations WHERE id=?',(r['observation_id'],))
        assert hashlib.sha256(raw['raw_body']).hexdigest()==raw['body_sha256']
        envelope=load_json(raw['raw_body'])
        adapter=kalshi if venue=='kalshi' else polymarket_us
        original=next(m for m in envelope.get('markets',[envelope.get('market')]) if m and m[adapter.ID_FIELD]==sid)
        adapter.validate_market(original)
        excerpt=dumps({'market':original})
        selected[key]={'venue':venue,'source_id':sid,'contract':load_json(r['evidence_json'])['contract'],
            'observed_at':r['observed_at'],'original_version_id':r['version_id'],
            'source_url':adapter.detail_url(sid),'parent_endpoint':raw['endpoint'],
            'parent_observation_id':raw['id'],'parent_sha256':raw['body_sha256'],
            'schema_version':raw['schema_version'],'representation':'RESERIALIZED_GENUINE_MARKET_EXCERPT',
            'body':excerpt,'body_sha256':hashlib.sha256(excerpt.encode()).hexdigest()}
    for venue,target,pattern in [('kalshi',sports_k,'KX%GAME-%'),('polymarket_us',sports_p,'aec-%')]:
        for r in registry._rows(source,'''SELECT h.source_id,v.evidence_json FROM registry_instruments h
           JOIN rule_versions v ON v.id=h.version_id WHERE h.venue=? AND h.available=1
           AND h.observed_at>? AND h.source_id LIKE ?''',(venue,(now-registry.MAX_AGE).isoformat(),pattern)):
            identity=sports.key(sports.features(load_json(r['evidence_json'])['contract']))
            if identity and identity[3]>='2026-10-28':target[identity]=r['source_id']
    common=sorted(set(sports_k)&set(sports_p))
    # Ten dates/participants, including both leagues; selection is explicit.
    chosen=common[:8]+[x for x in common if x[0]=='NFL'][:2]
    for identity in chosen:
        k,p=sports_k[identity],sports_p[identity];add('kalshi',k);add('polymarket_us',p)
        positives.append({'kalshi_id':k,'polymarket_us_id':p,'category':'same_event_different_settlement_rules',
            'reason':'Same league, named participants, originally scheduled rule date and selected winner.',
            'settlement_equivalence':'UNVERIFIED','known_contradictions':['Independent fair-price settlements','Postponement/forfeit/source revision applicability unverified']})
        inverse=next((key for key in sports_k if key[:-1]==identity[:-1] and key[-1]!=identity[-1]),None)
        if inverse:
            inv=sports_k[inverse];add('kalshi',inv)
            negatives.append({'kalshi_id':inv,'polymarket_us_id':p,'category':'inverse_outcome','reason':'Opposite selected winner for the same game; no complementary payoff approval.'})
    for strike in ('-0.1','0.0','0.1','0.2','0.3','0.4','0.5','0.6'):
        k='KXCPI-26OCT-T'+strike
        suffix=('neg'+strike[1:] if strike.startswith('-') else strike).replace('.','pt')
        p='cpic-uscpi-october-mom-2026-11-10-gt'+suffix+'pct'
        add('kalshi',k);add('polymarket_us',p)
        positives.append({'kalshi_id':k,'polymarket_us_id':p,'category':'cpi_monthly_threshold',
            'reason':f'October 2026 CPI monthly change above {strike}% in both ordinary propositions.',
            'settlement_equivalence':'UNVERIFIED','known_contradictions':['Kalshi shutdown extension versus US previous-month fallback after three months','Single-decimal source and revision applicability require review']})
    for a,b in zip(positives[-8:],positives[-7:]):
        negatives.append({'kalshi_id':a['kalshi_id'],'polymarket_us_id':b['polymarket_us_id'],'category':'different_threshold','reason':'Different explicit percentage threshold.'})
    for k,p in [('KXCPI-26OCT-T0.2','cpic-uscpi-october-yoy-2026-11-10-gt3pt2pct'),
                ('KXFED-26OCT-T4.25','rdc-usfed-fomc-2026-10-28-cut25')]:
        add('kalshi',k);add('polymarket_us',p)
        negatives.append({'kalshi_id':k,'polymarket_us_id':p,'category':'different_measure_or_settlement_rule',
             'reason':'Monthly versus annual CPI; or absolute rate threshold versus rounded change bucket. Thematic similarity is insufficient.'})
    negatives.append({'kalshi_id':positives[0]['kalshi_id'],'polymarket_us_id':positives[-1]['polymarket_us_id'],
                      'category':'obvious_false_positive','reason':'Basketball game winner versus consumer price index change.'})
    return {'schema':'m5i-genuine-evaluation/v1','hypothetical':False,'created_at':now.isoformat(),
            'annotation_author':'codex-research-assistant','operator_approved':False,
            'label_definition':'Reviewable same ordinary proposition, NOT settlement equivalence; closed curated corpus, all unlisted cross pairs negative.',
            'sampling':'Purposive NBA/NFL and CPI contrast set, not representative, not independently human-adjudicated or held out.',
            'instruments':list(selected.values()),'positives':positives,'hard_negatives':negatives}


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    with closing(readonly(a.db)) as source:corpus=build(source)
    Path(a.output).write_text(json.dumps(corpus,indent=2)+'\n')
    print(dumps({'instruments':len(corpus['instruments']),'positives':len(corpus['positives']),'hard_negatives':len(corpus['hard_negatives'])}))
if __name__=='__main__':main()
