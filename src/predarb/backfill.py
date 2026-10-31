"""M5L economic-priority work planner. Separate derived DB; never approves markets.

Three priority slots followed by one rotating hash-order slot. Successful vector
commits advance the fair cursor; a failed batch is retried without losing its turn.
"""
from collections import Counter
from datetime import timedelta
from decimal import Decimal
import hashlib
import json

from . import semantic as s, registry, discovery, embeddings
from .validation import load_json, dumps, utc_time

VERSION='economic-backfill/m5l-v1'
SCHEMA='''
CREATE TABLE IF NOT EXISTS backfill_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS backfill_tasks(
 venue TEXT NOT NULL, source_id TEXT NOT NULL, version_id INTEGER NOT NULL,
 content_hash TEXT NOT NULL, shuffle TEXT NOT NULL, tier INTEGER NOT NULL,
 evidence_json TEXT NOT NULL, PRIMARY KEY(venue,source_id));
CREATE INDEX IF NOT EXISTS backfill_priority ON backfill_tasks(venue,tier,shuffle);
CREATE INDEX IF NOT EXISTS backfill_fair ON backfill_tasks(venue,shuffle);
'''


def state(db,key,default=None):
    row=db.execute('SELECT value FROM backfill_state WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default


def put(db,key,value):
    db.execute('INSERT OR REPLACE INTO backfill_state VALUES(?,?)',(key,dumps(value)))


def initialize(db, source, index):
    if s.state(index,'schema')!=s.VERSION: raise ValueError('unknown semantic schema')
    source_path=source.execute('PRAGMA database_list').fetchone()[2]
    if s.state(index,'source_path')!=source_path: raise ValueError('source binding mismatch')
    index_path=index.execute('PRAGMA database_list').fetchone()[2]
    own=db.execute('PRAGMA database_list').fetchone()[2]
    if own and own in (source_path,index_path):raise ValueError('scheduler must be separate')
    db.executescript(SCHEMA)
    binding=[source_path,index_path,s.state(index,'active_identity')]
    if state(db,'schema',VERSION)!=VERSION or state(db,'binding',binding)!=binding:
        raise ValueError('unknown scheduler schema or namespace/source binding')
    put(db,'schema',VERSION);put(db,'binding',binding);db.commit()


def activity(venue, contract):
    key='volume_24h_fp' if venue=='kalshi' else 'volume24hr'
    value=contract.get(key)
    if value is None:return {'status':'UNKNOWN','field':key,'value':None}
    valid=isinstance(value,str) if venue=='kalshi' else type(value) in (int,Decimal)
    if not valid:raise ValueError('unknown activity schema')
    amount=Decimal(value)
    if not amount.is_finite() or amount<0:raise ValueError('invalid activity')
    return {'status':'POSITIVE_REPORTED_24H_VOLUME' if amount>0 else 'ZERO_REPORTED_24H_VOLUME',
            'field':key,'value':str(amount)}


def priority(*, event_date, activity_status, liquidity, now):
    # Calendar date precision is preserved; never invent a start hour/cash release.
    days=(utc_time(event_date+'T00:00:00Z').date()-now.date()).days if event_date else None
    near=days is not None and 0<=days<=7
    amount=liquidity.get('depth_proxy')
    fresh=liquidity.get('quality')=='FRESH' and amount is not None and Decimal(amount)>0
    active=activity_status=='POSITIVE_REPORTED_24H_VOLUME'
    return 0 if near and active and fresh else 1 if near and active else 2 if near else 3 if active and fresh else 4 if active else 5


def refresh(source,index,db,*,now):
    initialize(db,source,index)
    identity=s.state(index,'active_identity');context=s.venue_context(source)
    groups=Counter();stats=Counter(); db.execute('DELETE FROM backfill_tasks')
    clause,args=s.fresh_sql(now)
    # Current source heads are rechecked. No inference and no source writer lock.
    for doc in s.rows(index,'SELECT d.* FROM semantic_documents d WHERE '+clause,args):
        stats['sidecar_eligible']+=1
        head=s.current(source,doc,now,context)
        if head is None:stats['source_changed_or_ineligible']+=1;continue
        metadata=source.execute('''SELECT metadata_json FROM catalogue_entries
            WHERE run_id=? AND source_id=? AND observation_id=?''',
            (head['run_id'],doc['source_id'],head['observation_id'])).fetchone()
        contract=load_json(metadata[0]) if metadata else {}
        try: act=activity(doc['venue'],contract)
        except (ValueError,ArithmeticError):
            act={'status':'INVALID','field':None,'value':None};stats['invalid_activity']+=1
        liquid=discovery.liquidity(source,doc['venue'],doc['source_id'],now)
        sport=s.decode_features(doc['features_json']).get('sports')
        event_date=sport.get('scheduled_date') if sport and sport.get('supported') else None
        evidence={'category':doc['category'],'activity':act,'liquidity':liquid,
            'event_date':event_date,'market_cutoff':doc['cutoff'],
            'administrative_settlement_deadline':doc['horizon_end'],
            'expected_capital_release':None,'observed_at':head['observed_at'],
            'observation_id':head['observation_id'],'mechanics':'DISCOVERY_SUPPORTED_ACCOUNT_UNVERIFIED',
            'economically_eligible':False}
        vector=index.execute('SELECT created_at FROM semantic_vectors WHERE identity=? AND content_hash=?',
                             (identity,doc['content_hash'])).fetchone()
        indexed=bool(vector and 0<=(now-utc_time(vector[0])).total_seconds()<=30*86400)
        bucket=(doc['venue'],doc['category'],act['status'],liquid['quality'],s.horizon(doc['horizon_end'],now),'indexed' if indexed else 'backlog')
        groups[bucket]+=1;stats['current_eligible']+=1;stats['indexed' if indexed else 'backlog']+=1
        if not indexed:
            tier=priority(event_date=event_date,activity_status=act['status'],liquidity=liquid,now=now)
            db.execute('INSERT INTO backfill_tasks VALUES(?,?,?,?,?,?,?)',
                (doc['venue'],doc['source_id'],doc['version_id'],doc['content_hash'],doc['shuffle'],tier,dumps(evidence)))
    report={'schema':VERSION,'at':now.isoformat(),'identity':identity,'counts':dict(stats),
        'groups':[dict(venue=v,category=c,activity=a,liquidity=l,administrative_horizon=h,status=status,count=count)
                  for (v,c,a,l,h,status),count in sorted(groups.items())],
        'capital_release_coverage':'UNKNOWN','economically_eligible':False,
        'note':'Reported 24h activity is not executable depth. Administrative deadline is not capital release. Source archive and semantic index are read-only.'}
    put(db,'snapshot',report);db.commit();return report


def select(source,index,db,venue,count,*,now):
    if venue not in registry.VENUES or type(count)is not int or not 1<=count<=64:raise ValueError('bounded venue batch required')
    initialize(db,source,index)
    snapshot=state(db,'snapshot')
    if not snapshot or not 0<=(now-utc_time(snapshot['at'])).total_seconds()<=86400:raise ValueError('stale scheduler snapshot')
    identity=s.state(index,'active_identity');context=s.venue_context(source)
    before=state(db,'progress:'+venue,{'slot':0,'cursor':''});after=dict(before)
    chosen=[];used=set();fair=[]
    # Sort priority candidates once per batch, not once per selected item.
    # Fresh depth lasts seconds, not the plan's metadata lifetime.
    order = """CASE
        WHEN tier<=2 AND json_extract(evidence_json,'$.event_date')<?
            THEN CASE WHEN json_extract(evidence_json,'$.activity.status')='POSITIVE_REPORTED_24H_VOLUME' THEN 4 ELSE 5 END
        WHEN tier IN (0,3) AND NOT (
            COALESCE(julianday(json_extract(evidence_json,'$.liquidity.source_ts')) BETWEEN julianday(?) AND julianday(?),0)
            AND COALESCE(julianday(json_extract(evidence_json,'$.liquidity.received_at')) BETWEEN julianday(?) AND julianday(?),0))
            THEN tier+1 ELSE tier END,shuffle"""
    order_args=(now.date().isoformat(),
        (now-timedelta(seconds=60)).isoformat(),(now+timedelta(seconds=5)).isoformat(),
        (now-timedelta(seconds=60)).isoformat(),(now+timedelta(seconds=5)).isoformat())
    prioritized=s.rows(db,'SELECT * FROM backfill_tasks WHERE venue=? ORDER BY '+order,(venue,*order_args))
    def rotating():
        yield from s.rows(db,'SELECT * FROM backfill_tasks WHERE venue=? AND shuffle>? ORDER BY shuffle',(venue,before['cursor']))
        yield from s.rows(db,'SELECT * FROM backfill_tasks WHERE venue=? AND shuffle<=? ORDER BY shuffle',(venue,before['cursor']))
    rotated=rotating()
    def find(candidates):
        for task in candidates:
            if task['source_id'] in used:continue
            doc=next(s.rows(index,'SELECT * FROM semantic_documents WHERE venue=? AND source_id=?',(venue,task['source_id'])),None)
            if not doc or doc['version_id']!=task['version_id'] or doc['content_hash']!=task['content_hash']:continue
            if s.current(source,doc,now,context) is None:continue
            vector=index.execute('SELECT created_at FROM semantic_vectors WHERE identity=? AND content_hash=?',(identity,doc['content_hash'])).fetchone()
            if vector and 0<=(now-utc_time(vector[0])).total_seconds()<=30*86400:continue
            return doc
    for _ in range(count):
        is_fair=after['slot']%4==3
        doc=find(rotated if is_fair else prioritized)
        if doc is None:break
        chosen.append(doc);used.add(doc['source_id']);fair.append(is_fair)
        if is_fair:after['cursor']=doc['shuffle']
        after['slot']+=1
    token={'venue':venue,'identity':identity,'before':before,'after':after,
           'contents':[r['content_hash'] for r in chosen],'fair_slots':fair}
    return chosen,token


def acknowledge(index,db,token,*,now):
    if s.state(index,'active_identity')!=token['identity']:raise ValueError('namespace changed')
    if state(db,'progress:'+token['venue'],{'slot':0,'cursor':''})!=token['before']:raise ValueError('scheduler progress changed')
    for content in token['contents']:
        row=next(s.rows(index,'SELECT * FROM semantic_vectors WHERE identity=? AND content_hash=?',(token['identity'],content)),None)
        if row is None or not 0<=(now-utc_time(row['created_at'])).total_seconds()<=30*86400:raise ValueError('vector not committed')
        s.unpack(row)
    put(db,'progress:'+token['venue'],token['after']);db.commit()


class Scheduler:
    """Optional worker adapter; callers hold the separate scheduler writer lock."""
    def __init__(self,source,index,db):
        self.source,self.index,self.db=source,index,db
    def select(self,venue,count,*,now):
        return select(self.source,self.index,self.db,venue,count,now=now)
    def acknowledge(self,token,*,now):
        acknowledge(self.index,self.db,token,now=now)
