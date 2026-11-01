"""Freeze a diverse bounded shortlist from the existing index; no inference or writes to it."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from predarb import kalshi, polymarket_us as us, registry, semantic, sports_discovery
from predarb.backups import readonly
from predarb.conditional_research import contract_fingerprint
from predarb.orderbooks import market_rules
from predarb.provider import HttpClient
from predarb.store import connect
from predarb.validation import dumps, load_json

PIN = '8f1b745674ea82993cc5211498d606a86627ecedb6776637daeaf66e42611204'
PROPOSALS = [
    ('nba-brooklyn', 'KXNBAGAME-26NOV01BKNIND-BKN', 'aec-nba-bkn-ind-2026-11-01', 'NBA', None),
    ('nba-boston', 'KXNBAGAME-26NOV01BOSORL-BOS', 'aec-nba-bos-orl-2026-11-01', 'NBA', None),
    ('nba-toronto', 'KXNBAGAME-26NOV01TORLAL-TOR', 'aec-nba-tor-lal-2026-11-01', 'NBA', None),
    ('nfl-arizona', 'KXNFLGAME-26NOV01ARIDAL-ARI', 'aec-nfl-ari-dal-2026-11-01', 'NFL', None),
    ('nfl-baltimore', 'KXNFLGAME-26NOV01BALBUF-BAL', 'aec-nfl-bal-buf-2026-11-01', 'NFL', None),
    ('nfl-chicago', 'KXNFLGAME-26NOV02CHISEA-CHI', 'aec-nfl-chi-sea-2026-11-02', 'NFL', None),
    ('fed-hold', 'KXFEDDECISION-26DEC-H0', 'rdc-usfed-fomc-2026-12-09-nochng', 'FED', 'docs/FED_HOLD_SOURCE_BOUND_REVIEW.md'),
    ('payrolls', 'KXPAYROLLS-26OCT-T0', 'nfpc-usnfp-sa-october-2026-11-06-gt0', 'PAYROLLS', 'docs/m5n/payrolls-zero.md'),
    ('unemployment', 'KXU3-26OCT-T4.3', 'urc-usunemp-sa-october-2026-11-06-gt4pt3pct', 'UNEMPLOYMENT', 'docs/m5n/unemployment-4pt3.md'),
    ('cpi', 'KXCPI-26OCT-T0.2', 'cpic-uscpi-october-mom-2026-11-10-gt0pt2pct', 'CPI', 'docs/m5m/cpi-two.md'),
    ('gas-high', 'KXAAAGASMAX-26DEC31-4.60', 'aaagaspc-usgas-high-2026-12-31-gt4pt60', 'GAS', 'docs/m5m/gas-high.md'),
]


def select(root, index_path):
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    pairs, rejected, fixtures = [], [], []
    previous={}
    for path,key in [('docs/evidence/M5N_DEFINITIONS.json','definitions'),
                     ('tests/fixtures/m5m-public-definitions.json','responses')]:
        for item in load_json(Path(path).read_bytes())[key]:
            previous[item['source_id']]=load_json(item['body'])['market']
    with closing(readonly(index_path)) as index, connect(str(root/'definitions.sqlite3')) as archive:
        if semantic.state(index, 'active_identity') != PIN:
            raise ValueError('production model namespace mismatch')
        queue = [load_json(r[0]) for r in index.execute('SELECT report_json FROM semantic_candidates')]
        (root/'index-reservoir.json').write_text(dumps(queue)+'\n')
        clients = {v: HttpClient(archive, v, interval=1, attempts=1) for v in registry.VENUES}
        for name, ticker, slug, family, review in PROPOSALS:
            try:
                documents, definitions, refs, fingerprints = [], [], [], {}
                for venue, adapter, sid in [('kalshi', kalshi, ticker), ('polymarket_us', us, slug)]:
                    row = index.execute('SELECT id,version_id,observation_id,observed_at,public_text,content_hash FROM semantic_documents WHERE venue=? AND source_id=?', (venue, sid)).fetchone()
                    if row is None: raise ValueError('not present in existing index')
                    documents.append(dict(zip(('document_id','version_id','observation_id','observed_at','public_text','content_hash'), row), venue=venue, source_id=sid))
                    observed = clients[venue].get(adapter.detail_url(sid), adapter.SCHEMA_VERSION, adapter.validate_detail)
                    market = observed.data['market']
                    market_rules(venue, sid, market, now=datetime.now(timezone.utc))
                    raw, digest = archive.execute('SELECT raw_body,body_sha256 FROM raw_observations WHERE id=?', (observed.id,)).fetchone()
                    fixtures.append({'venue':venue, 'source_id':sid, 'endpoint':observed.endpoint,
                        'received_at':observed.received_at,'schema_version':adapter.SCHEMA_VERSION,
                        'body':raw.decode(),'sha256':digest,'representation':'EXACT_PUBLIC_RESPONSE'})
                    refs.append({'venue':venue,'observation_id':observed.id,'sha256':digest,'received_at':observed.received_at})
                    fingerprints[venue] = contract_fingerprint(venue, market)
                    definitions.append(market)
                stored = next((q for q in queue if q['kalshi_id']==ticker and q['polymarket_us_id']==slug), None)
                if family in {'NBA', 'NFL'}:
                    features = [sports_discovery.features(m) for m in definitions]
                    if not sports_discovery.key(features[0]) or sports_discovery.key(features[0]) != sports_discovery.key(features[1]):
                        raise ValueError('current sports ordinary event identity mismatch')
                    basis = 'Matching league, participants, explicit rule date and selected team in fresh definitions.'
                    risks = ['Independent discretionary settlement', 'Cancellation/forfeit/shortened game and revisions', 'Unreviewed fees, account mechanics and cash release', 'Non-atomic fills']
                    review = 'docs/M5L_RESULTS.md'
                else:
                    for venue,sid,market in zip(registry.VENUES,(ticker,slug),definitions):
                        fields=('rules_primary','rules_secondary','yes_sub_title','no_sub_title') if venue=='kalshi' else ('description',)
                        if any(market.get(f)!=previous[sid].get(f) for f in fields):
                            raise ValueError('reviewed ordinary proposition text changed; new screen required')
                    basis = 'Assistant ordinary-event assessment in '+review+'; no operator approval.'
                    risks = ['Source/version/exceptional-outcome interpretation unresolved; see '+review,
                             'Unreviewed fees, account mechanics and cash release', 'Non-atomic fills']
                review_path = Path(review)
                pairs.append({'id': name, 'kalshi_id':ticker,'polymarket_us_id':slug,'family':family,
                    'classification':'DISCOVERY' if family=='GAS' else 'CONDITIONAL',
                    'ordinary_basis':basis,'residual_risks':risks,
                    'exceptional_scenario':'HYPOTHETICAL K YES=1, US YES=0 => selected legs pay 0; source-bound possibilities, not a venue ruling. '+review,
                    'origin':'DETERMINISTIC',
                    'origin_detail':stored['retrieval_reasons'] if stored else ['EXPLICIT_INDEX_LOOKUP_AND_PRIOR_SOURCE_REVIEW'],
                    'ai_only':False, 'index_documents':documents,'fresh_sources':refs,
                    'contract_fingerprints':fingerprints,
                    'review':{'path':review,'sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),'operator_attested':False},
                    'kalshi_expected_expiration':definitions[0].get('expected_expiration_time'),
                    'us_administrative_end_date':definitions[1]['endDate'],
                    'settlement_delay_seconds':None,'cash_release_at':None})
            except (ValueError, OSError, KeyError) as exc:
                rejected.append({'id':name,'reason':str(exc)})
    report = {'schema':'m5o-candidates/v1','selected_at':datetime.now(timezone.utc).isoformat(),
        'source_index':str(index_path),'model_identity':PIN,'inference_requests':0,
        'selection':'Purposive deterministic index shortlist; one threshold per macro event, six separate sports games. Not representative market coverage.',
        'ai_only_selected':0,'ai_incremental_value':'NOT_ESTIMABLE_WITH_NO_AI_ONLY_SELECTED_PAIRS',
        'pairs':pairs,'rejected':rejected,'strict_pairs':0,'operator_approvals_created':0}
    ablation=Path('docs/evidence/M5O_AI_ABLATION.json')
    if ablation.exists():
        a=load_json(ablation.read_bytes())
        report['ai_ablation']={'path':str(ablation),'sha256':hashlib.sha256(ablation.read_bytes()).hexdigest(),
            'historical_replay_at':a['historical_replay_at'],'query_budget':a['query_budget'],
            'candidate_cap':a['candidate_cap'],'deterministic_candidates':a['deterministic_candidates'],
            'semantic_union_candidates':a['semantic_union_candidates'],
            'additional_ranked_candidates':len(a['semantic_only_candidates']),
            'additional_same_event_pairs_selected':0,
            'exclusions':'Additional ranked pairs have date/proposition conflicts; none selected.'}
    (root/'candidates.json').write_text(dumps(report)+'\n')
    (root/'definitions-fixture.json').write_text(dumps({'schema':'m5o-public-definitions/v1','hypothetical':False,'responses':fixtures})+'\n')
    print(dumps({'selected':len(pairs),'rejected':rejected,'manifest':str(root/'candidates.json')}))
    if not 10 <= len(pairs) <= 20: raise ValueError('need 10..20 freshly open pairs before launch')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--index',default='data/m5i/qwen-8f1b.semantic.sqlite3')
    a=p.parse_args(); select(a.output,a.index)
