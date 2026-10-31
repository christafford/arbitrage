"""Source-backed economic case file; failed gates yield unknown returns, never zero."""
import argparse
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from predarb.backups import readonly
from predarb.book_store import inspect_book
from predarb.validation import utc_time,dumps,load_json
from predarb import kalshi,polymarket_us,sports_discovery


def blocked_capital(reasons):
    if not reasons or any(not isinstance(x,str) or not x for x in reasons):
        raise ValueError('explicit unresolved gates required; use approved research evaluator for passing cases')
    return [{'combined_capital_usd':str(capital),'net_return_usd':None,'net_return_percent':None,
        'feasible_quantity':None,'fill_feasibility':'UNVERIFIED','reasons':sorted(set(reasons))}
        for capital in (Decimal(5),Decimal(25),Decimal(100),Decimal(500))]


def analyze(directory):
    status=load_json((directory/'status.json').read_bytes());config=status['config']
    snapshots=[];latest={};comparisons=[];fixtures=[];contracts={}
    with closing(readonly(str(directory/'capture.sqlite3'))) as con:
        for row in con.execute('SELECT observation_id,evaluated_at FROM normalized_books ORDER BY id'):
            at=utc_time(row[1]);raw=con.execute('SELECT venue FROM raw_observations WHERE id=?',(row[0],)).fetchone()
            latest[raw[0]]=row[0]
            if len(latest)!=2:continue
            books={v:inspect_book(con,i,now=at) for v,i in latest.items()}
            stamps=[utc_time(b['source_ts']) for b in books.values() if b['source_ts']]
            received=[utc_time(b['received_at']) for b in books.values()]
            skew=abs((stamps[0]-stamps[1]).total_seconds()) if len(stamps)==2 else None
            receipt_skew=abs((received[0]-received[1]).total_seconds())
            usable=all(b['data_usable'] for b in books.values())
            comparison={'at':at.isoformat(),'observations':dict(latest),'both_usable':usable,
                'source_skew_seconds':skew,'receipt_skew_seconds':receipt_skew,
                'fresh_comparable':usable and skew is not None and skew<=2 and receipt_skew<=2,
                'rejections':{v:b['rejections'] for v,b in books.items()}}
            comparisons.append(comparison);snapshots.append((comparison,books))
        for venue,adapter,sid in [('kalshi',kalshi,config['kalshi_ticker']),('polymarket_us',polymarket_us,config['us_slug'])]:
            row=con.execute('SELECT * FROM raw_observations WHERE endpoint=? ORDER BY id LIMIT 1',(adapter.detail_url(sid),)).fetchone()
            names=[x[1] for x in con.execute('pragma table_info(raw_observations)')];raw=dict(zip(names,row))
            body=raw.pop('raw_body');raw.pop('json_payload');raw['body']=body.decode();raw['representation']='EXACT_PUBLIC_RESPONSE'
            if hashlib.sha256(body).hexdigest()!=raw['body_sha256']:raise ValueError('source hash mismatch')
            adapter.validate_detail(load_json(body));contracts[venue]=load_json(body)['market'];fixtures.append(raw)
        for venue,endpoint in [('polymarket_us',polymarket_us.book_url(config['us_slug']))]:
            row=next(iter(con.execute('SELECT id,ts_utc,endpoint,schema_version,raw_body,body_sha256 FROM raw_observations WHERE endpoint=? ORDER BY id LIMIT 1',(endpoint,))))
            fixtures.append(dict(zip(('id','ts_utc','endpoint','schema_version','body','body_sha256'),[*row[:4],row[4].decode(),row[5]]),venue=venue,representation='EXACT_PUBLIC_RESPONSE'))
        # WS public frames have already passed the existing privacy sanitizer.
        for kind in ('orderbook_snapshot','orderbook_delta'):
            row=con.execute("SELECT r.id,r.ts_utc,r.endpoint,r.schema_version,r.raw_body,r.body_sha256,f.archive_kind,f.wire_sha256 FROM raw_observations r JOIN ws_frames f ON f.observation_id=r.id WHERE json_extract(r.json_payload,'$.type')=? ORDER BY r.id LIMIT 1",(kind,)).fetchone()
            if row:fixtures.append(dict(zip(('id','ts_utc','endpoint','schema_version','body','body_sha256','representation','wire_sha256'),[*row[:4],row[4].decode(),*row[5:]]),venue='kalshi'))
    if not snapshots:raise ValueError('no cross-venue captures')
    selected=min(snapshots,key=lambda item:(not item[0]['both_usable'],item[0]['source_skew_seconds'] if item[0]['source_skew_seconds'] is not None else float('inf')))
    warnings=['SETTLEMENT_SCENARIOS_UNAPPROVED','FEE_APPLICABILITY_UNAPPROVED','ACCOUNT_MECHANICS_UNAPPROVED','CAPITAL_RELEASE_UNKNOWN']
    if not any(r['fresh_comparable'] for r in comparisons):warnings.append('NO_OBSERVED_FRESH_COMPARABLE_BOOKS')
    report={'schema':'m5l-economic-case/v1','historical_capture_only':True,'capture_status':status,
        'contracts':contracts,'sports_identity':{v:sports_discovery.features(c) for v,c in contracts.items()},
        'comparisons':comparisons,'closest_usable_observation':selected[0],'books':selected[1],
        'capital_cases':blocked_capital(warnings),'strict_arbitrage_eligible':False,'trading_authorized':False,
        'routes':{'supported_for_review':'Kalshi cash-funded NO + US cash-funded long YES of the same selected winner',
                  'blocked':'Kalshi YES + US synthetic NO (short YES); full payout collateral is not complement cost'},
        'exceptional_payout':'For independent fair prices fK and fUS, unit combined payout on K NO + US YES is 1 - fK + fUS. Equality to 1 is not established.',
        'expected_capital_release':None}
    return report,fixtures

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directories',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);a=p.parse_args()
    reports=[];fixtures=[]
    for directory in a.directories:
        report,items=analyze(directory);reports.append(report)
        fixtures.extend(dict(item,capture=str(directory)) for item in items)
    a.output.write_text(dumps({'cases':reports})+'\n')
    a.fixture.write_text(json.dumps({'schema':'m5l-public-evidence/v1','hypothetical':False,
        'sanitization':'Public REST bytes unchanged; WS bodies use existing privacy-screened capture with wire hash and archive kind. No credentials/account data.',
        'responses':fixtures},indent=2)+'\n')
    print(dumps([{'case':r['capture_status']['config'],'comparable':sum(x['fresh_comparable'] for x in r['comparisons']),'closest':r['closest_usable_observation']} for r in reports]))
