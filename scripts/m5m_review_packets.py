"""Archive-backed M5M review forms. Source imports/proposals only; never approve."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from predarb import registry, kalshi, polymarket_us as us, fee_capture
from predarb.store import connect
from predarb.validation import dumps, load_json, utc_time
from m5m_packets import CANDIDATES


def verified_document(row, at):
    raw=Path(row['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('document raw hash mismatch')
    text=Path(row['path']).with_suffix('.txt').read_bytes()
    if row.get('text_sha256') and hashlib.sha256(text).hexdigest()!=row['text_sha256']:
        raise ValueError('document text hash mismatch')
    age=(at-utc_time(row['retrieved_at'])).total_seconds()
    if not 0<=age<=86400:raise ValueError('document stale or future; receipt cannot be renewed')
    return raw,text


def definition(con,adapter,source,at):
    row=con.execute('SELECT id,ts_utc,raw_body,body_sha256,schema_version,validation_status FROM raw_observations WHERE endpoint=? ORDER BY id DESC LIMIT 1', (adapter.detail_url(source),)).fetchone()
    if not row or row[5]!='VALID' or hashlib.sha256(row[2]).hexdigest()!=row[3]:raise ValueError('missing or invalid definition provenance')
    if row[4] not in (adapter.SCHEMA_VERSION,fee_capture.SCHEMA):raise ValueError('unknown definition schema')
    data=load_json(row[2]);adapter.validate_detail(data)
    if data['market'][adapter.ID_FIELD]!=source:raise ValueError('definition identity mismatch')
    if not 0<=(at-utc_time(row[1])).total_seconds()<=86400:raise ValueError('definition stale or future')
    return {'venue':adapter.VENUE,'source_id':source,'observation_id':row[0],'retrieved_at':row[1],
            'source_url':adapter.detail_url(source),'body':row[2].decode(),'sha256':row[3],
            'schema_version':row[4],'contract':data['market']}


def build(directory,documents,output):
    # This script only accepts the dedicated preparation archive, never a caller's
    # production source/index DB. Re-run into a new preparation directory.
    manifest=load_json((directory/'manifest.json').read_bytes())
    if manifest.get('schema')!='m5m-review-preparation/v1':raise ValueError('unknown preparation schema')
    if len(manifest['candidates'])!=5:raise ValueError('all five bounded captures required')
    for row in manifest['candidates']:
        for venue in ('kalshi','polymarket_us'):
            if row.get(venue+'_collection',{}).get('status')!='COMPLETE' or venue+'_error' in row:
                raise ValueError('incomplete source capture; do not create ready review forms')
    docs={Path(x.get('path','')).stem:x for x in documents if x.get('status')==200 and x.get('path','').endswith('.pdf')}
    at=datetime.now(timezone.utc)
    sources={k:verified_document(docs[k],at) for k in ('kalshi-cpi','us-cpi','kalshi-gas','us-gas','us-rulebook')}
    output.mkdir(parents=True,exist_ok=False)
    packets=[]
    with closing(connect(str(directory/'research.sqlite3'))) as con:
        if con.execute('SELECT COUNT(*) FROM pairs').fetchone()[0]:raise ValueError('prepared proposals already exist; preserve them')
        for name,k,u,event in CANDIDATES:
            family='cpi' if name.startswith('cpi') else 'gas'
            definitions={a.VENUE:definition(con,a,s,at) for a,s in ((kalshi,k),(us,u))}
            for venue,source,keys in [('kalshi',k,['kalshi-'+family]),('polymarket_us',u,['us-'+family,'us-rulebook'])]:
                for key in keys:
                    row=docs[key];raw,text=sources[key]
                    registry.import_document(con,venue,source,row['url'],raw,text,row['retrieved_at'],'CODEX_EVIDENCE_PREPARATION',now=at)
            pair_id=registry.propose(con,k,u,'CODEX_EVIDENCE_PREPARATION',now=at)
            review=registry.review(con,pair_id,now=at);form=registry.review_template(con,pair_id,now=at)
            (output/(name+'-registry.json')).write_text(dumps(review)+'\n')
            (output/(name+'-human-review.json')).write_text(json.dumps(form,indent=2)+'\n')
            capture_row=next(x for x in manifest['candidates'] if x['name']==name)
            fees={v:fee_capture.review(con,capture_row[v+'_fee_capture_id'],now=at)
                  for v in ('kalshi','polymarket_us')}
            for venue,source,side in (('kalshi',k,'NO'),('polymarket_us',u,'YES')):
                if (fees[venue]['draft']['source_id'],fees[venue]['draft']['side'])!=(source,side):
                    raise ValueError('fee packet identity/route mismatch')
            reasons=(['REVISION_POLICY_MISMATCH','MISSING_DATA_FALLBACK_MISMATCH','INDEPENDENT_DISCRETIONARY_SETTLEMENT']
                     if family=='cpi' else ['OBSERVATION_WINDOW_MISMATCH','REVISION_POLICY_MISMATCH','EXCEPTIONAL_SETTLEMENT_UNVERIFIED'])
            reasons+=['HUMAN_SETTLEMENT_REVIEW_PENDING','ACCOUNT_MECHANICS_UNAPPROVED','FEE_APPLICABILITY_UNAPPROVED','CASH_RELEASE_UNCONFIRMED']
            packet={'schema':'settlement-review-packet/m5m-v1','name':name,'pair_id':pair_id,'prepared_at':at.isoformat(),
                    'source_database':str(directory/'research.sqlite3'),'definitions':definitions,
                    'documents':[docs[x] for x in ('kalshi-'+family,'us-'+family,'us-rulebook')],
                    'fee_packets':fees,'assistant_screen':'STRICT_INELIGIBLE_PENDING_HUMAN_REVIEW',
                    'human_decision':None,'strict_arbitrage_eligible':False,'reasons':reasons,
                    'supported_route_for_review':{'kalshi':'cash-funded NO','polymarket_us':'cash-funded long YES'},
                    'unsupported_route':'US synthetic NO / short YES; full payout collateral, no execution support',
                    'cash_release_estimate':None,'capital_cases':[{'combined_capital_usd':str(n),
                        'gross_edge_usd':None,'net_edge_usd':None,'executable_quantity':None,
                        'venue_capital':None,'observable_duration_seconds':None,'hypothetical_unmatched_leg_exposure_usd':None,
                        'status':'BLOCKED_BEFORE_ECONOMIC_EVALUATION','reasons':reasons} for n in (5,25,100,500)],
                    'trading_authorized':False}
            (output/(name+'-packet.json')).write_text(dumps(packet)+'\n');packets.append(packet)
    return packets

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--documents',type=Path,required=True);a=p.parse_args()
    packets=build(a.source,load_json(a.documents.read_bytes()),a.output)
    print(dumps([{'name':x['name'],'pair_id':x['pair_id'],'strict_arbitrage_eligible':False} for x in packets]))
