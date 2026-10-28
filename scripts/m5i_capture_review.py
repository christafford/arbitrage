"""Bounded fresh public metadata evidence for an existing operator review shortlist."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from predarb import kalshi, polymarket_us, registry, sports_discovery as sports
from predarb.collector import collect
from predarb.provider import HttpClient
from predarb.store import connect
from predarb.validation import dumps,load_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--db',required=True);p.add_argument('--output',required=True)
    p.add_argument('--limit',type=int,default=30);a=p.parse_args()
    if not 1<=a.limit<=40:raise ValueError('review capture limit must be 1..40')
    if Path(a.db).exists():raise ValueError('review evidence archive must be new')
    candidates=json.loads(Path(a.candidates).read_text())['candidates'];seen=set();out=[]
    with connect(a.db) as source:
        clients={v:HttpClient(source,v,interval=1) for v in registry.VENUES}
        for row in candidates:
            # Known explicit scheduled rule dates; do not present completed
            # previous-calendar-day games as the most promising future events.
            sport=row.get('features',{}).get('kalshi',{}).get('sports')
            date=sport.get('scheduled_date') if sport else None
            if date and date<registry.now_utc().date().isoformat():continue
            event=row['kalshi_id'].rsplit('-',1)[0]
            if event in seen:continue
            seen.add(event)
            item={'kalshi_id':row['kalshi_id'],'polymarket_us_id':row['polymarket_us_id'],'runs':[],'errors':[]}
            for adapter in (kalshi,polymarket_us):
                try:
                    r=collect(source,adapter,scope=event if adapter is kalshi else row['polymarket_us_id'],
                              page_size=20,max_pages=3,books=0,client=clients[adapter.VENUE])
                    item['runs'].append(r.as_dict())
                except (ValueError,OSError) as exc:item['errors'].append(str(exc))
            available=[];identities=[];versions=[]
            for venue in registry.VENUES:
                try:
                    instrument=registry._instrument(source,venue,row[venue+'_id'])
                    available.append(bool(instrument['available']))
                    identities.append(sports.key(sports.features(load_json(instrument['evidence_json'])['contract'])))
                    versions.append(instrument['version_id'])
                except ValueError:available.append(False);identities.append(None)
            item.update(available=available,sports_identities=identities,live_identity_confirmed=all(available) and bool(identities[0]) and identities[0]==identities[1],
                        captured_at=registry.now_utc().isoformat(),versions=versions,status='UNVERIFIED',equivalence_verified=False,trading_authorized=False)
            out.append(item)
            if len(out)>=a.limit:break
        raw=[{'id':r['id'],'venue':r['venue'],'endpoint':r['endpoint'],'received_at':r['ts_utc'],'sha256':r['body_sha256'],'schema_version':r['schema_version'],'validation_status':r['validation_status']} for r in registry._rows(source,'SELECT * FROM raw_observations')]
    report={'schema':'m5i-live-review-capture/v1','hypothetical':False,'archive':a.db,'captures':out,'raw_evidence':raw}
    Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    print(dumps({'captures':len(out),'live_identity_confirmed':sum(x['live_identity_confirmed'] for x in out),'raw_responses':len(raw)}))
if __name__=='__main__':main()
