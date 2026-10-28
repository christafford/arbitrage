"""Restartable sidecar discovery index. Similarity never authorizes equivalence.

SQLite FTS5 and multi-probe random-hyperplane buckets bound retrieval memory.
Only public definition text crosses the private inference boundary. The source
archive is opened read-only by workers; inference commits only to the sidecar.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
import struct
import time

from . import discovery as d, embeddings as e, registry, sports_discovery as sports
from .validation import dumps, load_json, utc_time

VERSION = 'semantic-discovery/m5i-v1'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS semantic_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS semantic_documents (
 id INTEGER PRIMARY KEY, venue TEXT NOT NULL, source_id TEXT NOT NULL,
 version_id INTEGER NOT NULL, observed_at TEXT NOT NULL, observation_id INTEGER,
 hypothetical INTEGER NOT NULL, category TEXT NOT NULL, cutoff TEXT,
 horizon_end TEXT, sport_key TEXT, event_key TEXT NOT NULL,
 features_json TEXT NOT NULL, content_hash TEXT, public_text TEXT,
 reason TEXT NOT NULL, priority INTEGER NOT NULL, shuffle TEXT NOT NULL,
 UNIQUE(venue,source_id)
);
CREATE INDEX IF NOT EXISTS semantic_work ON semantic_documents(venue,reason,priority DESC,shuffle);
CREATE INDEX IF NOT EXISTS semantic_sport ON semantic_documents(venue,sport_key);
CREATE INDEX IF NOT EXISTS semantic_content ON semantic_documents(content_hash);
CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(subject, description);
CREATE TABLE IF NOT EXISTS semantic_vectors (
 identity TEXT NOT NULL, content_hash TEXT NOT NULL, dimensions INTEGER NOT NULL,
 vector BLOB NOT NULL, sha256 TEXT NOT NULL, observation_id INTEGER NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(identity,content_hash)
);
CREATE TABLE IF NOT EXISTS semantic_buckets (
 identity TEXT NOT NULL, band INTEGER NOT NULL, bucket INTEGER NOT NULL,
 content_hash TEXT NOT NULL,
 PRIMARY KEY(identity,band,bucket,content_hash)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS semantic_models (
 identity TEXT PRIMARY KEY, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
 checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS semantic_candidates (
 kalshi_id TEXT NOT NULL, polymarket_us_id TEXT NOT NULL, report_json TEXT NOT NULL,
 PRIMARY KEY(kalshi_id,polymarket_us_id)
);
'''


def initialize(index, source):
    index.executescript(SCHEMA)
    if state(index, 'schema', VERSION) != VERSION:
        raise ValueError('unknown semantic index schema; rebuild into a new sidecar')
    set_state(index, 'schema', VERSION)
    path = source.execute('PRAGMA database_list').fetchone()[2]
    previous = state(index, 'source_path')
    if previous and previous != path:
        raise ValueError('semantic sidecar belongs to a different source archive')
    set_state(index, 'source_path', path)
    index.commit()


def state(con, key, default=None):
    row = con.execute('SELECT value FROM semantic_state WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_state(con, key, value):
    con.execute('INSERT OR REPLACE INTO semantic_state VALUES(?,?)', (key, dumps(value)))


def rows(con, sql, args=()):
    cur = con.execute(sql, args)
    names = [x[0] for x in cur.description]
    for row in cur:
        yield dict(zip(names, row))


def encode_features(features):
    return dumps({k: sorted(v) if isinstance(v, (set, frozenset)) else v for k,v in features.items()})


def decode_features(text):
    f = json.loads(text)
    for k in ('subject', 'description', 'dates', 'text_dates', 'policy'):
        f[k] = frozenset(f[k])
    f['thresholds'] = frozenset(tuple(x) for x in f['thresholds'])
    return f


def venue_context(source):
    result = {}
    for venue in registry.VENUES:
        latest = source.execute('SELECT id,status FROM collection_runs WHERE venue=? ORDER BY id DESC LIMIT 1', (venue,)).fetchone()
        full = source.execute("SELECT id,status FROM collection_runs WHERE venue=? AND json_extract(scope_json,'$.filter') IS NULL ORDER BY id DESC LIMIT 1", (venue,)).fetchone()
        result[venue] = (latest, full)
    return result


def eligible(source, row, now, context):
    if not row['available']: return 'UNAVAILABLE'
    age = (now - utc_time(row['observed_at'])).total_seconds()
    if not -5 <= age <= 86400: return 'STALE_OR_FUTURE_CATALOGUE'
    contract = load_json(row['evidence_json'])['contract']
    cutoff = contract.get('close_time') or contract.get('endDate')
    if cutoff and utc_time(cutoff) <= now: return 'CLOSED'
    if not row['hypothetical']:
        latest, full = context[row['venue']]
        if any(r and r[1] in ('FAILED','INTERRUPTED','RUNNING') for r in (latest,full)):
            return 'COLLECTION_UNCERTAIN'
        if full and full[1] == 'COMPLETE' and not source.execute(
                'SELECT 1 FROM catalogue_entries WHERE run_id=? AND source_id=?', (full[0],row['source_id'])).fetchone():
            return 'ABSENT_FROM_COMPLETE_CATALOGUE'
    return 'ELIGIBLE'


def sync(source, index, *, budget=10000, now=None):
    """Bounded new-version priority plus guaranteed rotating catalogue backfill.

    Checkpoints commit with document/FTS changes. A killed page repeats safely.
    Source receipt times are copied, never renewed by this operation.
    """
    if not 1 <= budget <= 100000: raise ValueError('sync budget must be 1..100000')
    now = now or registry.now_utc()
    initialize(index, source)
    context = venue_context(source)
    maximum = source.execute('SELECT coalesce(max(id),0) FROM rule_versions').fetchone()[0]
    watermark = state(index, 'version_watermark', maximum)
    cursor = state(index, 'scan_cursor', 0)
    processed = 0
    sql = '''SELECT h.rowid AS scan_id,h.*,v.evidence_json,v.hypothetical
             FROM registry_instruments h JOIN rule_versions v ON v.id=h.version_id '''
    def save(row, priority):
        contract = load_json(row['evidence_json'])['contract']
        reason = eligible(source, row, now, context)
        f = d.features(contract)
        if contract.get('question') and contract.get('title'):
            f['subject_text'] += ' ' + contract['title']
            f['subject'] = f['subject'] | d.tokens(contract['title'])
        # Include explicit side/subtitle thresholds omitted by generic question titles.
        threshold_text = ' '.join(contract.get(k,'') for k in ('title','subtitle','yes_sub_title','question','description','rules_primary'))
        f['thresholds'] = d.features({'title':threshold_text})['thresholds']
        sport_key = sports.key(f['sports'])
        if f['sports'] is not None and sport_key is None and reason == 'ELIGIBLE':
            reason = 'UNSUPPORTED_SPORTS'
        if reason == 'ELIGIBLE' and not row['hypothetical']:
            if row['venue']=='kalshi' and (contract.get('market_type')!='binary' or 'notional_value_dollars' not in contract or Decimal(contract['notional_value_dollars'])!=1):
                reason='UNSUPPORTED_MECHANICS'
            if row['venue']=='polymarket_us':
                sides=contract.get('marketSides',[])
                if (len(sides)!=2 or {s.get('long') for s in sides}!={True,False} or
                    any(s.get('marketSideType')!='MARKET_SIDE_TYPE_INSTRUMENT' or s.get('identifier')!=row['source_id'] or s.get('tradable') is not True for s in sides)):
                    reason='UNSUPPORTED_MECHANICS'
        category = sports.metadata(contract, 'category') or ('sports' if f['sports'] else 'UNKNOWN')
        if not isinstance(category,str): raise ValueError('invalid category')
        cutoff = f['cutoff']
        end = contract.get('latest_expiration_time') or contract.get('endDate')
        end = utc_time(end).isoformat() if end else None
        event = (dumps(sport_key[:-1]) if sport_key else contract.get('event_ticker')
                 or dumps([d.normalize(contract.get('question') or f['title']), sorted(f['text_dates'])]))
        text = content = None
        try:
            text = e.public_text(contract)
            content = e.digest(text)
        except e.EmbeddingError:
            if reason == 'ELIGIBLE': reason = 'TEXT_TOO_LARGE'
        old = index.execute('SELECT id,version_id,priority FROM semantic_documents WHERE venue=? AND source_id=?',
                            (row['venue'],row['source_id'])).fetchone()
        priority = max(priority, old[2] if old else 0)
        values = (row['venue'],row['source_id'],row['version_id'],row['observed_at'],row['observation_id'],
                  row['hypothetical'],category,cutoff,end,dumps(sport_key) if sport_key else None,event,
                  encode_features(f),content,text,reason,priority,e.digest(row['venue']+row['source_id']))
        index.execute('''INSERT INTO semantic_documents(venue,source_id,version_id,observed_at,observation_id,
            hypothetical,category,cutoff,horizon_end,sport_key,event_key,features_json,content_hash,public_text,reason,priority,shuffle)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(venue,source_id) DO UPDATE SET
            version_id=excluded.version_id,observed_at=excluded.observed_at,observation_id=excluded.observation_id,
            hypothetical=excluded.hypothetical,category=excluded.category,cutoff=excluded.cutoff,horizon_end=excluded.horizon_end,
            sport_key=excluded.sport_key,event_key=excluded.event_key,features_json=excluded.features_json,
            content_hash=excluded.content_hash,public_text=excluded.public_text,reason=excluded.reason,priority=excluded.priority''',values)
        doc = old[0] if old else index.execute('SELECT last_insert_rowid()').fetchone()[0]
        if not old or old[1] != row['version_id']:
            index.execute('DELETE FROM semantic_fts WHERE rowid=?',(doc,))
            index.execute('INSERT INTO semantic_fts(rowid,subject,description) VALUES(?,?,?)',
                          (doc,' '.join(sorted(f['subject'] - d.RETRIEVAL_STOP)), ' '.join(sorted(f['description']))))
    # A high-water mark is version based, not provider page order. Reserve >=25%
    # for old catalogue traversal so sustained new listings cannot starve backfill.
    changed = rows(source,sql+'WHERE h.version_id>? ORDER BY h.version_id LIMIT ?',
                   (watermark,max(1,budget*3//4)))
    try:
        for row in changed:
            save(row,1); watermark=row['version_id']; processed+=1
        remaining = budget-processed
        for row in rows(source,sql+'WHERE h.rowid>? ORDER BY h.rowid LIMIT ?', (cursor,remaining)):
            save(row,0); cursor=row['scan_id']; processed+=1
        end = not source.execute('SELECT 1 FROM registry_instruments WHERE rowid>? LIMIT 1',(cursor,)).fetchone()
        set_state(index,'scan_cursor',0 if end else cursor)
        set_state(index,'version_watermark',watermark)
        set_state(index,'sync_at',now.isoformat())
        if end: set_state(index,'last_full_scan',now.isoformat())
        index.commit()
    except BaseException:
        index.rollback(); raise
    return {'processed':processed,'scan_complete':end,'scan_cursor':0 if end else cursor,
            'documents':index.execute('SELECT count(*) FROM semantic_documents').fetchone()[0],
            'source_instruments':source.execute('SELECT count(*) FROM registry_instruments').fetchone()[0]}


def horizon(value, now):
    if value is None: return 'UNKNOWN'
    days = (utc_time(value)-now).total_seconds()/86400
    return 'PAST' if days<0 else '0_7_DAYS' if days<=7 else '8_30_DAYS' if days<=30 else '31_90_DAYS' if days<=90 else 'OVER_90_DAYS'


def fresh_sql(now, alias='d'):
    # ISO clocks here were normalized to UTC by sync; source clocks are rechecked
    # against the authoritative archive again before returning a candidate.
    return (f"{alias}.reason='ELIGIBLE' AND {alias}.observed_at>=? AND {alias}.observed_at<=? "
            f"AND ({alias}.cutoff IS NULL OR {alias}.cutoff>?)"), (
                (now-timedelta(days=1)).isoformat(),(now+timedelta(seconds=5)).isoformat(),now.isoformat())


def coverage(source, index, *, now=None):
    now = now or registry.now_utc()
    identity = state(index,'active_identity')
    groups = defaultdict(Counter)
    for row in rows(index,'''SELECT d.venue,d.category,d.horizon_end,d.reason,d.observed_at,d.cutoff,
            v.created_at AS vector_at FROM semantic_documents d LEFT JOIN semantic_vectors v
            ON v.identity=? AND v.content_hash=d.content_hash''',(identity,)):
        group=groups[(row['venue'],row['category'],horizon(row['horizon_end'],now))]
        group['catalogued']+=1
        valid=row['reason']=='ELIGIBLE' and -5 <= (now-utc_time(row['observed_at'])).total_seconds()<=86400 and (not row['cutoff'] or utc_time(row['cutoff'])>now)
        if valid:
            group['eligible']+=1
            if row['vector_at'] and 0 <= (now-utc_time(row['vector_at'])).total_seconds()<=30*86400: group['indexed']+=1
            else: group['backlog']+=1
        else: group['excluded']+=1
    totals={v:Counter() for v in registry.VENUES}
    for (v,_,_),counts in groups.items():totals[v].update(counts)
    result={v:dict(c,source_total=source.execute('SELECT count(*) FROM registry_instruments WHERE venue=?',(v,)).fetchone()[0]) for v,c in totals.items()}
    for c in result.values(): c['unsynced']=c['source_total']-c.get('catalogued',0)
    return {'at':now.isoformat(),'identity':identity,'venues':result,
            'groups':[dict(venue=v,category=c,settlement_deadline_horizon=h,**counts) for (v,c,h),counts in sorted(groups.items())],
            'horizon_note':'Administrative deadline proxy; cash availability and settlement timing remain unverified',
            'last_full_scan':state(index,'last_full_scan'),'collection':venue_context(source)}


def signatures(values):
    """16 deterministic 8-bit sparse hyperplane hashes; not monetary arithmetic."""
    size=len(values)
    for band in range(16):
        bucket=0
        for bit in range(8):
            seed=hashlib.sha256(f'm5i-lsh-v1/{band}/{bit}'.encode()).digest()
            dot=sum(values[((seed[j]<<8)|seed[j+1])%size] * (1 if seed[j]&1 else -1) for j in range(0,32,2))
            if dot>=0:bucket |= 1<<bit
        yield band,bucket


def pack(values): return struct.pack('<'+'d'*len(values),*values)


def unpack(row):
    body=row['vector']
    if len(body)!=row['dimensions']*8 or hashlib.sha256(body).hexdigest()!=row['sha256']:
        raise e.EmbeddingError('CORRUPT_PERSISTENT_VECTOR')
    values=struct.unpack('<'+'d'*row['dimensions'],body)
    if not all(math.isfinite(x) for x in values) or not .999999 <= math.hypot(*values) <= 1.000001:
        raise e.EmbeddingError('INVALID_PERSISTENT_VECTOR')
    return values


def index_batch(index, client, *, budgets=None, now=None, seconds=120, texts_per_second=8):
    budgets=budgets or dict.fromkeys(registry.VENUES,256)
    if set(budgets)!=set(registry.VENUES) or any(type(n)is not int or not 0<=n<=10000 for n in budgets.values()):
        raise ValueError('per-venue budgets must be 0..10000')
    if not 1<=seconds<=3600 or not 0<texts_per_second<=100: raise ValueError('invalid worker throughput/time budget')
    start=time.monotonic(); now=now or registry.now_utc()
    report={'status':'READY','completed':dict.fromkeys(registry.VENUES,0),'requests':0,'cache_hits':0}
    try:
        if client.identity is None:client.probe()
        index.execute('INSERT OR REPLACE INTO semantic_models VALUES(?,?,?,?)',
                      (client.identity,client.model,client.dimensions,now.isoformat()))
        set_state(index,'active_identity',client.identity);index.commit()
        clause,args=fresh_sql(now)
        exhausted=set()
        turn=0
        while len(exhausted)<len(budgets) and time.monotonic()-start<seconds:
            venue=registry.VENUES[turn % len(registry.VENUES)];turn+=1
            budget=budgets[venue]
            if venue in exhausted:continue
            if report['completed'][venue]>=budget:
                exhausted.add(venue);continue
            count=min(client.config.batch_size,budget-report['completed'][venue])
            # Every fourth batch takes the stable hashed backfill order. Initial
            # catalogues are never treated as a representative provider prefix.
            order='d.shuffle' if (sum(report['completed'].values())//client.config.batch_size)%4==3 else 'd.priority DESC,d.shuffle'
            work_now=datetime.fromtimestamp(client.clock(),timezone.utc)
            selected=list(rows(index,f'''SELECT d.* FROM semantic_documents d
                WHERE d.venue=? AND {clause} AND d.content_hash IS NOT NULL AND NOT EXISTS
                (SELECT 1 FROM semantic_vectors v WHERE v.identity=? AND v.content_hash=d.content_hash
                 AND v.created_at>=? AND v.created_at<=?) ORDER BY {order} LIMIT ?''',
                (venue,*args,client.identity,(work_now-timedelta(days=30)).isoformat(),work_now.isoformat(),count)))
            if not selected:
                exhausted.add(venue);continue
            from pathlib import Path
            from shutil import disk_usage
            dbpath=Path(index.execute('PRAGMA database_list').fetchone()[2])
            if disk_usage(dbpath.parent).free<1024*1024*1024:
                raise e.EmbeddingError('INDEX_DISK_SPACE_GUARD')
            tick=time.monotonic()
            vectors=client.embed([r['public_text'] for r in selected])
            for doc,values in zip(selected,vectors):
                cached=index.execute('SELECT observation_id,created_at FROM embedding_cache WHERE identity=? AND content_hash=?',
                                     (client.identity,doc['content_hash'])).fetchone()
                if cached is None:raise e.EmbeddingError('MISSING_VECTOR_PROVENANCE')
                blob=pack(values)
                index.execute('INSERT OR REPLACE INTO semantic_vectors VALUES(?,?,?,?,?,?,?)',
                              (client.identity,doc['content_hash'],len(values),blob,hashlib.sha256(blob).hexdigest(),*cached))
                index.execute('DELETE FROM semantic_buckets WHERE identity=? AND content_hash=?',(client.identity,doc['content_hash']))
                index.executemany('INSERT INTO semantic_buckets VALUES(?,?,?,?)',
                                  [(client.identity,b,s,doc['content_hash']) for b,s in signatures(values)])
                index.execute('UPDATE semantic_documents SET priority=0 WHERE id=?',(doc['id'],))
            # Expire inactive model spaces first; the cap is explicit and any
            # removed current vector returns to the reported backlog.
            excess=index.execute('SELECT max(0,count(*)-250000) FROM semantic_vectors').fetchone()[0]
            if excess:
                index.execute('DELETE FROM semantic_vectors WHERE rowid IN (SELECT rowid FROM semantic_vectors ORDER BY identity=?,created_at LIMIT ?)',(client.identity,excess))
                index.execute('DELETE FROM semantic_buckets WHERE NOT EXISTS (SELECT 1 FROM semantic_vectors v WHERE v.identity=semantic_buckets.identity AND v.content_hash=semantic_buckets.content_hash)')
            index.commit()
            report['completed'][venue]+=len(selected)
            delay=len(selected)/texts_per_second-(time.monotonic()-tick)
            if delay>0:client.sleep(min(delay,max(0,seconds-(time.monotonic()-start))))
    except (ValueError,OSError) as exc:
        index.rollback()
        report.update(status='FALLBACK',reason=str(exc) if isinstance(exc,e.EmbeddingError) else 'INDEX_INPUT_OR_IO_ERROR')
    report['stop_reason']='TIME_BUDGET' if time.monotonic()-start>=seconds else 'PER_VENUE_BUDGET_OR_EMPTY'
    report.update(requests=client.requests,cache_hits=client.hits,model=client.model,identity=client.identity,
                  dimensions=client.dimensions,elapsed_seconds=time.monotonic()-start)
    report['texts_per_second']=sum(report['completed'].values())/max(report['elapsed_seconds'],.001)
    set_state(index,'last_worker',report);index.commit()
    return report


def vector_candidates(index, query, identity, now, *, cap=256):
    row=next(rows(index,'SELECT * FROM semantic_vectors WHERE identity=? AND content_hash=?',(identity,query['content_hash'])),None)
    if row is None or not 0<=(now-utc_time(row['created_at'])).total_seconds()<=30*86400:return {},False
    values=unpack(row)
    hits=Counter()
    # Each bucket probe is capped; the report surfaces saturation. No hidden
    # first-N catalogue pool. Sparse approximate retrieval is measured in eval.
    saturated=False
    target='polymarket_us' if query['venue']=='kalshi' else 'kalshi'
    clause,args=fresh_sql(now)
    for band,bucket in signatures(values):
        buckets=[bucket]+[bucket^(1<<bit) for bit in range(8)]
        # Force the indexed bucket to drive this lookup. Otherwise SQLite can
        # choose a venue-wide metadata scan for every band in a partial index.
        found=index.execute(f'''SELECT DISTINCT b.content_hash FROM semantic_buckets b
            CROSS JOIN semantic_documents d INDEXED BY semantic_content ON d.content_hash=b.content_hash
            WHERE b.identity=? AND b.band=? AND b.bucket IN (?,?,?,?,?,?,?,?,?)
            AND d.venue=? AND d.hypothetical=? AND {clause} LIMIT ?''',
            (identity,band,*buckets,target,query['hypothetical'],*args,cap+1)).fetchall()
        hits.update(x[0] for x in found[:cap])
        if len(found)>cap:saturated=True
    result={}
    for content,_ in hits.most_common(cap):
        v=next(rows(index,'SELECT * FROM semantic_vectors WHERE identity=? AND content_hash=?',(identity,content)),None)
        if not v or v['dimensions']!=len(values) or not 0<=(now-utc_time(v['created_at'])).total_seconds()<=30*86400:continue
        score=sum(a*b for a,b in zip(values,unpack(v)))
        if score>=.70:result[content]=max(-1,min(1,score))
    return result,saturated


def current(source, doc, now, context):
    row=next(rows(source,'''SELECT h.*,v.evidence_json,v.hypothetical FROM registry_instruments h
         JOIN rule_versions v ON v.id=h.version_id WHERE h.venue=? AND h.source_id=?''',
         (doc['venue'],doc['source_id'])),None)
    if row is None or row['version_id']!=doc['version_id'] or eligible(source,row,now,context)!='ELIGIBLE':return None
    row['features']=decode_features(doc['features_json'])
    return row


def rank_pair(source, index, left, right, reasons, semantic, now, context, *, recheck=True):
    if left['hypothetical']!=right['hypothetical']:return None
    k,p=(left,right) if left['venue']=='kalshi' else (right,left)
    kr,pr=(current(source,k,now,context),current(source,p,now,context)) if recheck else (dict(k,features=decode_features(k['features_json'])),dict(p,features=decode_features(p['features_json'])))
    if kr is None or pr is None:return None
    comparison=d.compare(kr['features'],pr['features'],semantic=semantic is not None)
    if comparison is None:return None
    score,signals,warnings=comparison
    if not k['sport_key'] and k['horizon_end'] and p['horizon_end']:
        gap=abs((utc_time(k['horizon_end'])-utc_time(p['horizon_end'])).total_seconds())
        if gap>90*86400:return None
        if gap>7*86400:warnings.append('SETTLEMENT_DEADLINE_HORIZONS_DIFFER')
    if semantic is not None:
        signals['embedding']=semantic
        warnings.append('EMBEDDING_RETRIEVAL_ONLY_HUMAN_REVIEW_REQUIRED')
    material=[w for w in warnings if 'CONFLICT' in w or w=='RESOLUTION_LANGUAGE_DIFFERS']
    if k['sport_key']:
        warnings.extend(['EXCEPTIONAL_FAIR_PRICE_PAYOUTS_NOT_ESTABLISHED_COMPLEMENTARY',
                         'FORFEIT_AND_SOURCE_REVISION_RULES_REQUIRE_REVIEW'])
    expires=min(utc_time(kr['observed_at']),utc_time(pr['observed_at']))+timedelta(days=1)
    if semantic:
        stamps=index.execute('SELECT created_at FROM semantic_vectors WHERE identity=? AND content_hash IN (?,?)',
                             (semantic['identity'],k['content_hash'],p['content_hash'])).fetchall()
        if stamps:expires=min(expires,min(utc_time(x[0]) for x in stamps)+timedelta(days=30))
    # Scores never compensate for explicit contradictions. This is a review
    # ordering, not a probability of equivalence or an executable opportunity.
    similarity=semantic['cosine'] if semantic else 0
    rank=(bool(material),-score,-similarity,k['source_id'],p['source_id'])
    return rank, {'kalshi_id':k['source_id'],'polymarket_us_id':p['source_id'],
        'kalshi_title':kr['features']['title'],'polymarket_us_title':pr['features']['title'],
        'versions':[k['version_id'],p['version_id']], 'event_key':k['event_key'], 'polymarket_event_key':p['event_key'],
        'retrieval_reasons':sorted(reasons),'signals':signals,'warnings':warnings,
        'known_contradictions':material,'equivalence_score_bps':score,
        'match_basis':'SPORTS_EVENT_IDENTITY' if k['sport_key'] else 'EMBEDDING_ASSISTED' if semantic else 'TEXT_HEURISTIC',
        'status':'UNVERIFIED','equivalence_verified':False,'trading_authorized':False,
        'hypothetical':bool(k['hypothetical']),'algorithm':VERSION,
        'source_observations':[kr['observation_id'],pr['observation_id']],
        'source_received_at':[kr['observed_at'],pr['observed_at']],
        'review_snapshot_expires_at':expires.isoformat(),
        'settlement_deadlines':[k['horizon_end'],p['horizon_end']],
        'definition_links':{'kalshi':d.kalshi.detail_url(k['source_id']), 'polymarket_us':d.polymarket_us.detail_url(p['source_id'])},
        'review_reason':'EVENT_IDENTITY_ONLY' if k['sport_key'] else 'TEXT_SIMILARITY_REQUIRES_PROPOSITION_REVIEW'}


def retrieve(source,index,*,limit=20,query_budget=500,candidate_cap=256,now=None,semantic=True,
             query_ids=None,persist=True):
    if not 1<=limit<=1000 or not 1<=query_budget<=10000 or not 1<=candidate_cap<=1024:
        raise ValueError('retrieval bounds: limit 1..1000, queries 1..10000, candidates 1..1024')
    now=now or registry.now_utc();context=venue_context(source)
    identity=state(index,'active_identity') if semantic else None
    model=next(rows(index,'SELECT * FROM semantic_models WHERE identity=?',(identity,)),{})
    clause,args=fresh_sql(now)
    result={}; queries=0;saturated=0; failures=0
    def keep(item):
        if item is None:return
        rank,row=item
        if len(result)>=limit and rank[:2]>max(x[0][:2] for x in result.values()):return
        if row['event_key'] in result and rank[:2]>result[row['event_key']][0][:2]:return
        for venue,version in zip(registry.VENUES,row['versions']):
            instrument=registry._instrument(source,venue,row[venue+'_id'])
            if instrument['version_id']!=version or eligible(source,instrument,now,context)!='ELIGIBLE':return
        liquidity={v:d.liquidity(source,v,row[v+'_id'],now) for v in registry.VENUES}
        verified=all(x['quality']=='FRESH' and x['depth_proxy'] is not None and Decimal(x['depth_proxy'])>0 for x in liquidity.values())
        depth=min(Decimal(x['depth_proxy']) for x in liquidity.values()) if verified else Decimal(0)
        row['liquidity']=liquidity
        rank=(*rank[:2],-int(verified),-depth,*rank[2:])
        key=row['event_key']
        for existing,(prior_rank,prior_row) in list(result.items()):
            if existing!=key and prior_row['polymarket_event_key']==row['polymarket_event_key']:
                if rank>=prior_rank:return
                del result[existing]
        if key not in result or rank<result[key][0]:result[key]=(rank,row)
        if len(result)>limit:
            del result[max(result,key=lambda x:result[x][0])]
    # Revalidate the bounded persistent reservoir before unioning a new query
    # window. Previous versions or stale observations can never survive here.
    if persist:
        for (encoded,) in index.execute('SELECT report_json FROM semantic_candidates LIMIT 1000'):
            previous=json.loads(encoded)
            docs=[next(rows(index,'SELECT * FROM semantic_documents WHERE venue=? AND source_id=?',(v,previous[v+'_id'])),None) for v in registry.VENUES]
            if all(docs) and [x['version_id'] for x in docs]==previous['versions']:
                emb=previous['signals'].get('embedding') if identity else None
                if emb and emb['identity']!=identity:emb=None
                # Semantic-only proposals expire with their vector evidence.
                if emb:
                    vectors=list(rows(index,'SELECT * FROM semantic_vectors WHERE identity=? AND content_hash IN (?,?)',
                                      (identity,docs[0]['content_hash'],docs[1]['content_hash'])))
                    if len(vectors)!=len({doc['content_hash'] for doc in docs}) or any(not 0<=(now-utc_time(v['created_at'])).total_seconds()<=30*86400 for v in vectors):emb=None
                    else:
                        try:
                            for v in vectors:unpack(v)
                        except e.EmbeddingError:
                            emb=None;failures+=1
                keep(rank_pair(source,index,*docs,previous['retrieval_reasons'],emb,now,context))
    # Prefer the smaller US side as queries. Supported sports identity retrieval
    # is always visited independently of the generic query checkpoint.
    if query_ids is not None:
        def queries_iter():
            for venue,source_id in query_ids:
                yield from rows(index,f'SELECT d.* FROM semantic_documents d WHERE venue=? AND source_id=? AND {clause}',(venue,source_id,*args))
        selected=queries_iter()
        finished=False
    else:
        cursor=state(index,'query_cursor','') if persist else ''
        sport_cursor=state(index,'sports_query_cursor','') if persist else ''
        sport_rows=list(rows(index,f'''SELECT d.* FROM semantic_documents d WHERE venue='polymarket_us'
            AND {clause} AND sport_key IS NOT NULL AND shuffle>? ORDER BY shuffle LIMIT ?''',
            (*args,sport_cursor,max(1,query_budget//2))))
        def window():
            yield from sport_rows
            yield from rows(index,f'''SELECT d.* FROM semantic_documents d WHERE venue='polymarket_us'
                AND {clause} AND sport_key IS NULL AND shuffle>? ORDER BY shuffle LIMIT ?''',
                (*args,cursor,query_budget-len(sport_rows)))
        selected=window()
        finished=True
    last=None
    sport_last=None
    for query in selected:
        queries+=1
        if queries>query_budget:finished=False;break
        target='polymarket_us' if query['venue']=='kalshi' else 'kalshi'
        possible={}
        def add(doc,reason,cosine=None):
            if doc['id'] not in possible and len(possible)>=2*candidate_cap:return
            item=possible.setdefault(doc['id'],[doc,set(),None])
            item[1].add(reason)
            if cosine is not None:item[2]=cosine
        if query['sport_key']:
            sport_last=query['shuffle']
            for doc in rows(index,f'SELECT d.* FROM semantic_documents d WHERE venue=? AND sport_key=? AND {clause} LIMIT ?',
                            (target,query['sport_key'],*args,candidate_cap)):
                add(doc,'EXACT_LEAGUE_PARTICIPANTS_RULE_DATE_AND_SELECTION')
        else:
            last=query['shuffle']
            f=decode_features(query['features_json'])
            terms=sorted(f['subject']-d.RETRIEVAL_STOP)
            if terms:
                match='subject : ('+' OR '.join('"'+t+'"' for t in terms[:32])+')'
                for (doc_id,) in index.execute(f'''SELECT d.id FROM semantic_fts JOIN semantic_documents d ON d.id=semantic_fts.rowid
                     WHERE semantic_fts MATCH ? AND d.venue=? AND d.sport_key IS NULL AND {clause}
                     ORDER BY bm25(semantic_fts,5.0,1.0),d.source_id LIMIT ?''',(match,target,*args,candidate_cap)):
                    doc=next(rows(index,'SELECT * FROM semantic_documents WHERE id=?',(doc_id,)))
                    add(doc,'KEYWORD_BM25')
            if identity:
                try:
                    vectors,cap_hit=vector_candidates(index,query,identity,now,cap=candidate_cap)
                    saturated+=int(cap_hit)
                    for content,cosine in vectors.items():
                        for doc in rows(index,f'''SELECT d.* FROM semantic_documents d WHERE venue=? AND content_hash=?
                             AND sport_key IS NULL AND {clause} LIMIT ?''',(target,content,*args,candidate_cap)):
                            add(doc,'PERSISTENT_VECTOR_COSINE',cosine)
                except e.EmbeddingError:failures+=1
        for doc,reasons,cosine in possible.values():
            emb=dict(cosine=cosine,identity=identity,model=model.get('model'),dimensions=model.get('dimensions'),
                     versions=[query['version_id'],doc['version_id']] if query['venue']=='kalshi' else [doc['version_id'],query['version_id']]) if cosine is not None else None
            keep(rank_pair(source,index,query,doc,reasons,emb,now,context,recheck=False))
    if query_ids is None and last is not None:
        finished=not index.execute(f'''SELECT 1 FROM semantic_documents d WHERE venue='polymarket_us'
             AND sport_key IS NULL AND {clause} AND shuffle>? LIMIT 1''',(*args,last)).fetchone()
    candidates=[row for _,row in sorted(result.values(),key=lambda x:x[0])]
    # Liquidity is inspected only for the bounded finalist queue. Unknown/stale
    # depth is never promoted to verified liquidity or treated as a zero cost.
    for row in candidates:
        row['mechanics']={'research_path':'CASH_FUNDED_LONG_ONLY','polymarket_us_no':'UNSUPPORTED_SYNTHETIC_SHORT',
                          'account_applicability':'UNVERIFIED'}
        row['prior_reviews']=registry._rows(source,'SELECT id,status,reason FROM pairs WHERE kalshi_id=? AND polymarket_us_id=? ORDER BY id',
                                            (row['kalshi_id'],row['polymarket_us_id']))
    candidates.sort(key=lambda r:(bool(r['known_contradictions']),-r['equivalence_score_bps'],
        -int(all(x['quality']=='FRESH' and x['depth_proxy'] is not None and Decimal(x['depth_proxy'])>0 for x in r['liquidity'].values())),
        -min((Decimal(x['depth_proxy']) for x in r['liquidity'].values()),default=Decimal(0)) if all(x['quality']=='FRESH' and x['depth_proxy'] is not None for x in r['liquidity'].values()) else Decimal(0),
        -r['signals'].get('embedding',{}).get('cosine',0),r['kalshi_id'],r['polymarket_us_id']))
    if persist:
        index.execute('DELETE FROM semantic_candidates')
        index.executemany('INSERT INTO semantic_candidates VALUES(?,?,?)',[(r['kalshi_id'],r['polymarket_us_id'],dumps(r)) for r in candidates])
        if query_ids is None:
            if last is not None:
                set_state(index,'query_cursor','' if finished else last)
            if sport_last:
                sport_more=index.execute(f"SELECT 1 FROM semantic_documents d WHERE venue='polymarket_us' AND {clause} AND sport_key IS NOT NULL AND shuffle>? LIMIT 1",(*args,sport_last)).fetchone()
                set_state(index,'sports_query_cursor',sport_last if sport_more else '')
        index.commit()
    return {'algorithm':VERSION,'ranked_at':now.isoformat(),'candidates':candidates,
            'retrieval':{'queries':min(queries,query_budget),'window_complete':finished,'bucket_saturations':saturated,
                         'vector_failures':failures,'candidate_cap':candidate_cap,'approximate':True,
                         'identity':identity,'model':model.get('model'),'deterministic_enabled':True},
            'coverage':coverage(source,index,now=now)}
