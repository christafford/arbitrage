"""Sidecar workers never acquire the collector's writer lock or send venue writes."""
from contextlib import closing, contextmanager, ExitStack
from pathlib import Path
from shutil import disk_usage

from . import semantic, embeddings, registry
from .backups import readonly
from .runtime import writer_lock
from .store import connect
from .validation import dumps


def add_parsers(actions):
    for name in ('index-sync','index-work','index-coverage','index-retrieve'):
        p=actions.add_parser(name,help='M5I persistent sidecar '+name)
        p.add_argument('--db',default='data/research.sqlite3')
        p.add_argument('--index-db',help='default: source path plus .semantic.sqlite3')
        p.add_argument('--min-free-mb',type=int,default=1024)
        if name=='index-sync':p.add_argument('--budget',type=int,default=10000)
        if name=='index-work':
            p.add_argument('--kalshi-budget',type=int,default=256)
            p.add_argument('--us-budget',type=int,default=256)
            p.add_argument('--seconds',type=int,default=120)
            p.add_argument('--texts-per-second',type=float,default=8)
            p.add_argument('--expected-identity',help='require this exact previously validated model fingerprint')
        if name=='index-retrieve':
            p.add_argument('--limit',type=int,default=20)
            p.add_argument('--query-budget',type=int,default=500)
            p.add_argument('--candidate-cap',type=int,default=256)
            p.add_argument('--deterministic-only',action='store_true')


@contextmanager
def sidecar(path, source, *, read_fallback=False):
    with ExitStack() as stack:
        writable=True
        try:
            stack.enter_context(writer_lock(path))
        except ValueError as exc:
            if not read_fallback or 'another predarb writer' not in str(exc):raise
            writable=False
        index=stack.enter_context(connect(path) if writable else closing(readonly(path)))
        if writable:semantic.initialize(index,source)
        else:
            index.execute('BEGIN')
            if semantic.state(index,'source_path')!=source.execute('PRAGMA database_list').fetchone()[2]:
                raise ValueError('semantic sidecar belongs to a different source archive')
            if semantic.state(index,'schema')!=semantic.VERSION:raise ValueError('unknown semantic schema')
        yield index,writable


def run(args):
    path=args.index_db or args.db+'.semantic.sqlite3'
    if Path(path).resolve()==Path(args.db).resolve():raise ValueError('index must be separate from source archive')
    if args.min_free_mb<1 or disk_usage(Path(path).resolve().parent).free<args.min_free_mb*1024*1024:
        raise ValueError('insufficient free disk for semantic sidecar')
    with closing(readonly(args.db)) as source, sidecar(path,source,read_fallback=args.discovery_cmd in ('index-retrieve','index-coverage')) as (index,writable):
        if args.discovery_cmd=='index-sync':report=semantic.sync(source,index,budget=args.budget)
        elif args.discovery_cmd=='index-work':
            client=embeddings.from_environment(index)
            if client is None:raise ValueError('PREDARB_EMBEDDING_URL is required for index-work')
            if not client.base.split('/')[2].endswith('.ts.net'):
                raise ValueError('M5I worker requires the private Tailscale HTTPS endpoint')
            report=semantic.index_batch(index,client,budgets={'kalshi':args.kalshi_budget,'polymarket_us':args.us_budget},
                                        seconds=args.seconds,texts_per_second=args.texts_per_second,
                                        expected_identity=args.expected_identity)
        elif args.discovery_cmd=='index-retrieve':
            report=semantic.retrieve(source,index,limit=args.limit,query_budget=args.query_budget,
                                     candidate_cap=args.candidate_cap,semantic=not args.deterministic_only,persist=writable)
            report['sidecar_writable']=writable
        else:report=semantic.coverage(source,index)
    print(dumps(report))
    return 2 if report.get('status')=='FALLBACK' else 0


def refresh_archive(args):
    """Public collection finishes before local indexed retrieval; no inference."""
    from . import kalshi, polymarket_us, discovery_cli
    from .catalogue_walk import walk
    from .validation import load_json
    if not 1<=args.limit<=1000 or not 0<=args.books<=100 or not .25<=args.request_interval<=60:
        raise ValueError('invalid discovery limits or request interval')
    runs=[]; errors=[]
    with connect(args.db) as source:
        if not args.cached_catalogues:
            for adapter in (kalshi,polymarket_us):
                try:
                    runs.append(walk(source,adapter,page_size=args.page_size,max_pages=min(args.max_pages,1000),
                        client=discovery_cli.SpaceCheckedClient(source,adapter.VENUE,min_free_mb=args.min_free_mb,
                                                               interval=args.request_interval)).as_dict())
                except (ValueError,OSError) as exc:
                    errors.append({'venue':adapter.VENUE,'error':str(exc)})
        path=args.db+'.semantic.sqlite3'
        with sidecar(path,source,read_fallback=True) as (index,writable):
            if writable:semantic.sync(source,index,budget=10000)
            report=semantic.retrieve(source,index,limit=args.limit,query_budget=500,persist=writable)
            report['sidecar_writable']=writable
            # Preserve established deterministic matches while the sidecar is
            # partially populated or busy. Only the bounded prior queue is read.
            retained=retained_deterministic(source,args.limit)
            merged=[];k_events=set();p_events=set()
            for row in sorted(report['candidates']+retained,key=lambda r:(bool(r['known_contradictions']),-r['equivalence_score_bps'],r['kalshi_id'],r['polymarket_us_id'])):
                if row['event_key'] in k_events or row['polymarket_event_key'] in p_events:continue
                k_events.add(row['event_key']);p_events.add(row['polymarket_event_key']);merged.append(row)
                if len(merged)>=args.limit:break
            report['candidates']=merged
            report['retained_deterministic_candidates']=len(retained)
            # Selected source capture remains bounded and separate from inference.
            captured=set()
            for row in ([] if args.cached_catalogues else report['candidates'][:args.books]):
                if row['hypothetical']:continue
                for adapter in (kalshi,polymarket_us):
                    sid=row[adapter.VENUE+'_id']
                    if (adapter.VENUE,sid) in captured:continue
                    captured.add((adapter.VENUE,sid))
                    contract=load_json(registry._instrument(source,adapter.VENUE,sid)['evidence_json'])['contract']
                    try:
                        runs.append(discovery_cli.collect(source,adapter,scope=contract['event_ticker'] if adapter is kalshi else sid,
                            books=0,selected=(sid,),page_size=args.page_size,max_pages=3,
                            client=discovery_cli.SpaceCheckedClient(source,adapter.VENUE,min_free_mb=args.min_free_mb,
                                                                   interval=args.request_interval)).as_dict())
                    except (ValueError,OSError) as exc:errors.append({'venue':adapter.VENUE,'error':str(exc)})
            if captured:
                # Source-version changes invalidate rather than inherit similarity.
                report['candidates']=revalidate_candidates(source,report['candidates'])
            source.execute('DELETE FROM discovery_queue')
            source.executemany('INSERT INTO discovery_queue VALUES(?,?,?,?)',
                [(r['kalshi_id'],r['polymarket_us_id'],report['ranked_at'],dumps(r)) for r in report['candidates']])
            report.update(collection_runs=runs,errors=errors)
            source.execute('INSERT OR REPLACE INTO discovery_state VALUES(1,?,?)',(report['ranked_at'],dumps(report)))
            source.commit()
    print(dumps(report))
    return 1 if errors else 2 if any(x['status']!='COMPLETE' for x in runs) else 0


def revalidate_candidates(source,candidates,*,now=None):
    now=now or registry.now_utc(); context=semantic.venue_context(source);result=[]
    for candidate in candidates:
        expiry=candidate.get('review_snapshot_expires_at')
        if expiry is None or now>semantic.utc_time(expiry):continue
        valid=True; instruments=[]
        for venue,version in zip(registry.VENUES,candidate['versions']):
            row=registry._instrument(source,venue,candidate[venue+'_id'])
            instruments.append(row)
            if row['version_id']!=version or semantic.eligible(source,row,now,context)!='ELIGIBLE':valid=False;break
        if valid:
            candidate=dict(candidate)
            features=[semantic.d.features(semantic.load_json(r['evidence_json'])['contract']) for r in instruments]
            comparison=semantic.d.compare(*features,semantic='embedding' in candidate['signals'])
            if comparison is None:continue
            score,signals,warnings=comparison
            candidate['equivalence_score_bps']=score
            candidate['signals']={**candidate['signals'],**signals}
            candidate['warnings']=sorted(set(candidate['warnings'])|set(warnings))
            candidate['known_contradictions']=[w for w in candidate['warnings'] if 'CONFLICT' in w or w=='RESOLUTION_LANGUAGE_DIFFERS']
            candidate['liquidity']={v:semantic.d.liquidity(source,v,candidate[v+'_id'],now) for v in registry.VENUES}
            candidate['prior_reviews']=registry._rows(source,'SELECT id,status,reason FROM pairs WHERE kalshi_id=? AND polymarket_us_id=? ORDER BY id',
                (candidate['kalshi_id'],candidate['polymarket_us_id']))
            result.append(candidate)
    result.sort(key=lambda r:(bool(r['known_contradictions']),-r['equivalence_score_bps'],r['kalshi_id'],r['polymarket_us_id']))
    return result


def retained_deterministic(source,limit,*,now=None):
    from . import discovery
    from datetime import timedelta
    now=now or registry.now_utc()
    keys=source.execute('SELECT kalshi_id,polymarket_us_id FROM discovery_queue LIMIT 1000').fetchall()
    if not keys:return []
    previous=discovery.discover(source,limit=limit,now=now,_pair_keys=keys)['candidates']
    for row in previous:
        instruments=[registry._instrument(source,v,row[v+'_id']) for v in registry.VENUES]
        contracts=[semantic.load_json(x['evidence_json'])['contract'] for x in instruments]
        sport=semantic.sports.key(row['features']['kalshi']['sports'])
        row['event_key']=dumps(sport[:-1]) if sport else contracts[0].get('event_ticker',row['kalshi_id'])
        row['polymarket_event_key']=dumps(sport[:-1]) if sport else dumps([discovery.normalize(contracts[1].get('question') or contracts[1].get('title','')),row['features']['polymarket_us']['text_dates']])
        row['known_contradictions']=[w for w in row['warnings'] if 'CONFLICT' in w or w=='RESOLUTION_LANGUAGE_DIFFERS']
        if sport:
            row['warnings'].extend(['EXCEPTIONAL_FAIR_PRICE_PAYOUTS_NOT_ESTABLISHED_COMPLEMENTARY','FORFEIT_AND_SOURCE_REVISION_RULES_REQUIRE_REVIEW'])
        row['review_snapshot_expires_at']=(min(semantic.utc_time(x['observed_at']) for x in instruments)+timedelta(days=1)).isoformat()
        row['source_observations']=[x['observation_id'] for x in instruments]
        row['source_received_at']=[x['observed_at'] for x in instruments]
        row['retrieval_reasons']=['ESTABLISHED_DETERMINISTIC_QUEUE',row['match_basis']]
        row['algorithm']=semantic.VERSION
    return previous
