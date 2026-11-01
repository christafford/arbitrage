"""M5O fixed-deadline public observation with independent venue receivers.

Each pair/15-minute segment has separate single-writer venue archives. Source
databases and semantic indices are never opened here. No approval or order path.
"""
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from . import kalshi_ws, polymarket_us as us
from .backups import readonly
from .book_store import inspect_book
from .conditional_research import CAPITAL, classification, contract_fingerprint, quote_cases
from .kalshi_auth import Credentials
from .models import AskLevel
from .orderbooks import Book, PriceBand
from .quote_diagnostics import MeasuredClient
from .soak import atomic_json, poll_us, storage_bytes
from .store import connect
from .stream_comparison import clock_evidence
from .validation import dumps, identifier, load_json, utc_time

VERSION = 'continuous-conditional-observation/m5o-v2'
SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/m5o_observe.py'


class DeadlineClient(MeasuredClient):
    """Check the stop condition after pacing, immediately before network I/O."""
    def __init__(self,*args,guard,**kwargs):
        super().__init__(*args,**kwargs)
        original=self.opener
        class Guarded:
            def open(self,request,timeout):
                if guard(): raise OSError('FIXED_DEADLINE_OR_STOP')
                return original.open(request,timeout=timeout)
        self.opener=Guarded()


def now():
    return datetime.now(timezone.utc)


def append(path, row):
    with Path(path).open('a') as f:
        f.write(dumps(row)+'\n')


def validate_config(config):
    if config.get('schema') != VERSION: raise ValueError('unknown run schema')
    start, end = utc_time(config['started_at']), utc_time(config['deadline_at'])
    if not timedelta(seconds=10) <= end-start <= timedelta(hours=24):
        raise ValueError('fixed duration must be 10 seconds to 24 hours')
    pairs = config['pairs']
    if not 10 <= len(pairs) <= 20: raise ValueError('10..20 candidates required')
    if len({p['id'] for p in pairs}) != len(pairs): raise ValueError('duplicate pair id')
    if len({(p['kalshi_id'], p['polymarket_us_id']) for p in pairs}) != len(pairs):
        raise ValueError('duplicate market pair')
    for pair in pairs:
        for key in ('id','kalshi_id','polymarket_us_id'): identifier(pair[key])
        classification(pair)
        if pair['origin'] not in {'DETERMINISTIC','SEMANTIC_AI'} or type(pair['ai_only']) is not bool:
            raise ValueError('explicit discovery provenance required')
        if pair['ai_only'] and pair['origin'] != 'SEMANTIC_AI': raise ValueError('AI origin mismatch')
        if set(pair['contract_fingerprints']) != {'kalshi','polymarket_us'}:
            raise ValueError('source-bound ordinary assessment required')
    if config['poll_seconds'] != 5 or config['segment_seconds'] != 900:
        raise ValueError('unsupported observation cadence')
    if config['max_storage_bytes'] != 20*1024**3 or config['min_free_bytes'] != 2*1024**3:
        raise ValueError('unsupported resource limits')


def remaining(config, start_mono, *, at=None, mono=None):
    """Both original UTC and process monotonic limits apply; never renew a run."""
    at = at or now(); mono = time.monotonic() if mono is None else mono
    duration = (utc_time(config['deadline_at']) - utc_time(config['started_at'])).total_seconds()
    return max(0, min((utc_time(config['deadline_at'])-at).total_seconds(), duration-(mono-start_mono)))


def select_book(con, venue, sid, at):
    row = con.execute('''SELECT b.observation_id FROM book_captures b JOIN raw_observations r
        ON r.id=b.observation_id WHERE r.venue=? AND b.source_id=? AND r.ts_utc<=?
        ORDER BY b.observation_id DESC LIMIT 1''', (venue, sid, at.isoformat())).fetchone()
    if not row: raise ValueError(venue+':MISSING_BOOK')
    observed = row[0]
    saved = inspect_book(con, observed, now=at)
    # inspect_book already performed full raw-byte stream replay. Reconstruct its
    # typed result, rather than repeating the same expensive replay a second time.
    fields={key:saved[key] for key in Book.__dataclass_fields__}
    for key in ('yes_asks','no_asks'): fields[key]=tuple(AskLevel(**x) for x in fields[key])
    fields['price_bands']=tuple(PriceBand(**x) for x in fields['price_bands'])
    fields['rejections']=tuple(fields['rejections'])
    book=Book(**fields); metadata=saved['metadata_observation_id']
    if venue == 'kalshi':
        invalid = con.execute('''SELECT 1 FROM ws_frames f JOIN raw_observations r ON r.id=f.observation_id
            WHERE r.id>? AND r.ts_utc<=? AND r.validation_status!='VALID' LIMIT 1''',
            (observed, at.isoformat())).fetchone()
        if invalid: saved['rejections'] = list(saved['rejections'])+['NEWER_INVALID_FRAME']
    refs = {}
    for kind, oid in [('book', observed), ('metadata', metadata)]:
        raw, digest = con.execute('SELECT raw_body,body_sha256 FROM raw_observations WHERE id=?', (oid,)).fetchone()
        if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('source hash mismatch')
        refs[kind] = {'observation_id':oid,'sha256':digest}
        if kind == 'metadata': market = load_json(raw)['market']
    return book, saved, refs, market


def visible_archive(con):
    """Commit visibility differs from provider receipt time. Preserve both."""
    connections=con.execute('SELECT * FROM ws_connections')
    names=[c[0] for c in connections.description]
    return {'raw_head':con.execute('SELECT coalesce(max(id),0) FROM raw_observations').fetchone()[0],
        'book_head':con.execute('SELECT coalesce(max(observation_id),0) FROM book_captures').fetchone()[0],
        'catalogue_head':con.execute('SELECT coalesce(max(observation_id),0) FROM catalogue_entries').fetchone()[0],
        'nonvalid':dict(con.execute("SELECT id,validation_status FROM raw_observations WHERE validation_status!='VALID'")),
        'connections':[dict(zip(names,row)) for row in connections.fetchall()]}


@contextmanager
def archived_visibility(con, known):
    """TEMP views in a mode=ro connection reproduce the reader's committed frontier.

    No source archive rows are mutated. A received-but-uncommitted future frame
    cannot retroactively supersede a sample; an observed pending frame remains a
    blocker even if its validation later succeeded.
    """
    for key in ('raw_head','book_head','catalogue_head'):
        if type(known[key]) is not int or known[key]<0: raise ValueError('invalid archive frontier')
    if max(known['book_head'],known['catalogue_head'])>known['raw_head']:
        raise ValueError('inconsistent archive frontier')
    views=[]
    try:
        con.execute('CREATE TEMP TABLE m5o_validation(id INTEGER PRIMARY KEY,status TEXT)')
        con.executemany('INSERT INTO m5o_validation VALUES(?,?)',[(int(k),v) for k,v in known['nonvalid'].items()])
        cols=[r[1] for r in con.execute('PRAGMA main.table_info(raw_observations)')]
        select=','.join('coalesce((SELECT status FROM m5o_validation WHERE id=r.id),r.validation_status) AS validation_status'
                        if c=='validation_status' else 'r.'+c for c in cols)
        con.execute('CREATE TEMP VIEW raw_observations AS SELECT '+select+' FROM main.raw_observations r WHERE r.id<='+str(known['raw_head']))
        views.append('raw_observations')
        for table,field,head in [('book_captures','observation_id','book_head'),
                ('normalized_books','observation_id','book_head'),('catalogue_entries','observation_id','catalogue_head'),
                ('ws_frames','observation_id','book_head')]:
            con.execute(f'CREATE TEMP VIEW {table} AS SELECT * FROM main.{table} WHERE {field}<={known[head]}')
            views.append(table)
        con.execute('CREATE TEMP TABLE m5o_connections AS SELECT * FROM main.ws_connections WHERE 0')
        for row in known['connections']:
            columns=list(row)
            expected=[r[1] for r in con.execute('PRAGMA main.table_info(ws_connections)')]
            if set(columns)!=set(expected): raise ValueError('unknown connection snapshot schema')
            con.execute('INSERT INTO m5o_connections ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',list(row.values()))
        con.execute('CREATE TEMP VIEW ws_connections AS SELECT * FROM m5o_connections'); views.append('ws_connections')
        yield
    finally:
        for view in reversed(views): con.execute('DROP VIEW IF EXISTS temp.'+view)
        con.execute('DROP TABLE IF EXISTS temp.m5o_connections'); con.execute('DROP TABLE IF EXISTS temp.m5o_validation')


def observation(kcon, ucon, pair, at, *, synchronized):
    books, inspected, sources, markets = [], [], {}, {}
    for con, venue in [(kcon,'kalshi'),(ucon,'polymarket_us')]:
        book, saved, refs, market = select_book(con, venue, pair[venue+'_id'], at)
        books.append(book); inspected.append(saved); sources[venue]=refs; markets[venue]=market
    current_pair = dict(pair)
    changed = [v for v in markets if contract_fingerprint(v, markets[v]) != pair['contract_fingerprints'][v]]
    if changed:
        current_pair['classification']='DISCOVERY'
        current_pair['residual_risks']=pair['residual_risks']+['SOURCE_VERSION_CHANGED:'+','.join(changed)]
    if not synchronized:
        for saved in inspected: saved['rejections']=list(saved['rejections'])+['LOCAL_CLOCK_UNVERIFIED']
    result = quote_cases(books, current_pair, now=at, inspected=inspected)
    result.update(at=at.isoformat(), sources=sources, source_versions_changed=changed,
        displayed_books=[b.as_dict(now=at) for b in books],
        kalshi_expected_expiration=markets['kalshi'].get('expected_expiration_time'),
        us_administrative_end_date=markets['polymarket_us']['endDate'])
    return result


def empty_summary():
    return {'samples':0,'quality_passes':0,'conditional_gross_samples':0,'discovery_samples':0,
        'rejections':{}, 'capital':{b:{'positive_samples':0,'sample_clusters':0,
            'positive_sample_cluster_span_seconds':0, 'max_gross_edge_usd':None,
            'max_displayed_quantity':None, 'last_positive_at':None,
            'continuous_opportunity_duration_seconds':None} for b in CAPITAL},
        'strict_eligible_samples':0, 'net_positive_opportunities':None}


def accumulate(summary, row):
    from decimal import Decimal
    summary['samples'] += 1
    q=row.get('quality',{})
    summary['quality_passes'] += bool(q.get('timestamp_depth_overlap'))
    summary['conditional_gross_samples'] += row.get('status')=='CONDITIONAL_GROSS_ONLY'
    summary['discovery_samples'] += row.get('classification')=='DISCOVERY'
    reasons=Counter(summary['rejections']); reasons.update(q.get('rejections',row.get('rejections',[])))
    summary['rejections']=dict(reasons)
    by_budget={x['quote_only_budget_usd']:x for x in row.get('capital_cases',[])}
    for budget, stats in summary['capital'].items():
        case=by_budget.get(budget)
        positive=case and case['positive_conditional_discrepancy']
        if case:
            for key, value in [('max_gross_edge_usd',case['gross_edge_usd']),
                               ('max_displayed_quantity',case['maximum_quantity_within_quote_budget'])]:
                if stats[key] is None or Decimal(str(value))>Decimal(str(stats[key])): stats[key]=str(value)
        if positive:
            previous=stats['last_positive_at']
            gap=(utc_time(row['at'])-utc_time(previous)).total_seconds() if previous else None
            stats['positive_samples']+=1
            if gap is not None and 0<gap<=7:
                stats['positive_sample_cluster_span_seconds']+=gap
            else: stats['sample_clusters']+=1
            stats['last_positive_at']=row['at']
        else: stats['last_positive_at']=None


def replay_segment(root, pair):
    """Offline raw-byte replay at actual assessment instants, never at today's clock."""
    root=Path(root); verified=0; samples=0
    status=load_json((root/'status.json').read_bytes())
    if status['schema']!=VERSION or status['pair_id']!=pair['id']: raise ValueError('segment identity mismatch')
    if not (root/'clock-after.json').exists(): raise ValueError('unfinished segment')
    if not load_json((root/'clock-after.json').read_bytes())['synchronized']:
        raise ValueError('post-capture local clock unverified')
    with closing(readonly(root/'kalshi.sqlite3')) as kcon, closing(readonly(root/'us.sqlite3')) as ucon:
        for con in (kcon,ucon):
            for raw,digest in con.execute('SELECT raw_body,body_sha256 FROM raw_observations'):
                if raw is None or hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('raw hash mismatch')
                verified+=1
            for table in ('pairs','fee_profiles','research_sessions','paper_intents'):
                if con.execute('SELECT count(*) FROM '+table).fetchone()[0]:
                    raise ValueError('unexpected approval/economics mutation')
        if kcon.execute('SELECT count(*) FROM ws_connections WHERE ended_at IS NULL').fetchone()[0]:
            raise ValueError('unfinished Kalshi generation')
        lines=(root/'observations.jsonl').read_bytes().splitlines()
        if len(lines)!=status['samples']: raise ValueError('sample count mismatch')
        previous=None
        for line in lines:
            saved=load_json(line); samples+=1
            at=utc_time(saved['at'])
            if not utc_time(status['started_at'])<=at<=utc_time(status['finished_at']) or (previous and at<=previous):
                raise ValueError('sample time outside capture or regressed')
            previous=at
            if saved.get('status')=='POLL_OR_BOOK_ERROR': continue
            with archived_visibility(kcon,saved['archive_visibility']['kalshi']), archived_visibility(ucon,saved['archive_visibility']['polymarket_us']):
                computed=observation(kcon,ucon,pair,at,synchronized=saved['clock_synchronized'])
            if load_json(dumps(computed)) != {k:saved[k] for k in computed}:
                raise ValueError('conditional observation replay mismatch')
    return {'schema':VERSION,'raw_hashes_verified':verified,'samples':samples,'replay':'PASS',
            'skipped_error_samples':sum(load_json(x).get('status')=='POLL_OR_BOOK_ERROR'
                for x in (root/'observations.jsonl').read_bytes().splitlines())}


def segment(root, pair, config, credentials, stop, summary, heartbeat):
    root.mkdir(parents=True,exist_ok=False)
    start=time.monotonic(); started=now()
    duration=min(config['segment_seconds'],max(0,(utc_time(config['deadline_at'])-started).total_seconds()))
    end=start+duration
    local_stop=threading.Event(); errors=[]; kstats=[]
    clocks=clock_evidence(); atomic_json(root/'clock-before.json',clocks)
    next_clock=start+30
    (root/'observations.jsonl').touch()
    with connect(str(root/'kalshi.sqlite3')): pass
    def guard(_con=None,_at=None):
        return (stop.is_set() or local_stop.is_set() or time.monotonic()>=end or now()>=utc_time(config['deadline_at'])
            or abs((now()-started).total_seconds()-(time.monotonic()-start))>1)
    def kalshi_receiver():
        try:
            with connect(str(root/'kalshi.sqlite3')) as con:
                client=DeadlineClient(con,'kalshi',emit=lambda row:append(root/'kalshi-timing.jsonl',row),
                                      attempts=1,timeout=3,interval=1,guard=guard)
                stats=kalshi_ws.capture(con,pair['kalshi_id'],credentials,seconds=max(1,int(duration)),
                    max_connections=120,max_messages=100000,directory=root,on_tick=guard,
                    metadata_loader=lambda db,sid:kalshi_ws.refresh_metadata(db,sid,client=client),
                    on_receive=lambda row:append(root/'kalshi-timing.jsonl',row))
                kstats.append(stats)
        except Exception as exc:
            errors.append(type(exc).__name__); local_stop.set()
    receiver=threading.Thread(target=kalshi_receiver,name='kalshi-receiver',daemon=True)
    receiver.start(); poll_count=0; reason='SEGMENT_COMPLETE'; consecutive=0
    try:
        with connect(str(root/'us.sqlite3')) as ucon, closing(readonly(root/'kalshi.sqlite3')) as kcon:
            client=DeadlineClient(ucon,'polymarket_us',emit=lambda row:append(root/'us-timing.jsonl',row),
                                  attempts=1,timeout=3,interval=1,guard=guard)
            next_poll=start
            while not guard():
                if time.monotonic()>=next_clock:
                    clocks=clock_evidence(); append(root/'clock-checks.jsonl',clocks); next_clock=time.monotonic()+30
                if not clocks['synchronized']: reason='LOCAL_CLOCK_UNVERIFIED'; break
                if shutil.disk_usage(root).free<config['min_free_bytes']: reason='LOW_DISK'; break
                if time.monotonic()<next_poll:
                    stop.wait(min(.25,next_poll-time.monotonic())); continue
                poll_start=time.monotonic(); next_poll=poll_start+config['poll_seconds']
                try:
                    poll_us(ucon,pair['polymarket_us_id'],client)
                    # No quote calculation from work which completed after the fixed deadline.
                    if guard(): break
                    at=now()
                    kcon.execute('BEGIN')
                    try:
                        visibility={'kalshi':visible_archive(kcon),'polymarket_us':visible_archive(ucon)}
                        row=observation(kcon,ucon,pair,at,synchronized=clocks['synchronized'])
                        row['archive_visibility']=visibility
                    finally: kcon.rollback()
                    consecutive=0
                except (ValueError,OSError,KeyError) as exc:
                    row={'schema':VERSION,'at':now().isoformat(),'status':'POLL_OR_BOOK_ERROR',
                         'rejections':[type(exc).__name__+':'+str(exc)],'strict_arbitrage_eligible':False,
                         'trading_authorized':False}
                    consecutive+=1
                row.update(clock_synchronized=clocks['synchronized'],poll_started_monotonic=poll_start,
                           evaluated_monotonic=time.monotonic())
                append(root/'observations.jsonl',row); accumulate(summary,row); poll_count+=1
                heartbeat()
                if not receiver.is_alive():
                    reason='DEADLINE_REACHED' if (utc_time(config['deadline_at'])-now()).total_seconds()<=2 else 'KALSHI_ENDED_EARLY'
                    break
                if consecutive>=12: reason='CONSECUTIVE_FAILURE_LIMIT'; break
    finally:
        local_stop.set(); receiver.join(timeout=15)
        if receiver.is_alive(): reason='RECEIVER_STOP_TIMEOUT'
        elif stop.is_set(): reason='DEADLINE_REACHED' if now()>=utc_time(config['deadline_at']) else 'INTERRUPTED'
        elif errors: reason='KALSHI_RECEIVER_ERROR'
        elif abs((now()-started).total_seconds()-(time.monotonic()-start))>1: reason='WALL_CLOCK_JUMP'
        atomic_json(root/'clock-after.json',clock_evidence())
        result={'schema':VERSION,'pair_id':pair['id'],'started_at':started.isoformat(),
                'finished_at':now().isoformat(),'samples':poll_count,'reason':reason,
                'kalshi':kstats,'errors':errors}
        atomic_json(root/'status.json',result)
    if reason=='RECEIVER_STOP_TIMEOUT': raise RuntimeError('receiver could not stop; refuse another writer')
    return result


def worker(root, config, pair_id, credentials_path, stop):
    validate_config(config); pair=next(p for p in config['pairs'] if p['id']==pair_id)
    root=Path(root); root.mkdir(parents=True,exist_ok=False)
    start=time.monotonic(); summary=empty_summary(); segments=[]; outcome='DEADLINE_REACHED'
    creds=Credentials.load(credentials_path)
    def heartbeat():
        atomic_json(root/'status.json',{'schema':VERSION,'pair_id':pair_id,'heartbeat_at':now().isoformat(),
            'status':'RUNNING','deadline_at':config['deadline_at'],'summary':summary,'segments':segments})
    try:
        for number in range(1,101):
            if remaining(config,start)<2 or stop.is_set(): break
            folder=root/f'segment-{number:03d}'
            result=segment(folder,pair,config,creds,stop,summary,heartbeat)
            segments.append({'directory':folder.name,'reason':result['reason']})
            try:
                verified=replay_segment(folder,pair); atomic_json(folder/'audit.json',verified)
            except (ValueError,OSError,KeyError) as exc:
                atomic_json(folder/'audit.json',{'replay':'FAILED','error_type':type(exc).__name__})
                outcome='REPLAY_FAILED'; break
            for stats in summary['capital'].values(): stats['last_positive_at']=None
            heartbeat()
            if result['reason']!='SEGMENT_COMPLETE': outcome=result['reason']; break
            if stop.wait(min(1,remaining(config,start))): break
        else: outcome='SEGMENT_LIMIT'
    except Exception:
        outcome='WORKER_ERROR'; raise
    finally:
        if stop.is_set() and outcome!='REPLAY_FAILED':
            outcome='DEADLINE_REACHED' if now()>=utc_time(config['deadline_at']) else 'INTERRUPTED'
        atomic_json(root/'status.json',{'schema':VERSION,'pair_id':pair_id,'heartbeat_at':now().isoformat(),
            'status':outcome,'deadline_at':config['deadline_at'],'summary':summary,'segments':segments})


def render(root, config, status):
    """An interim/final report with actual sample denominators, never invented uptime."""
    workers={}
    for pair in config['pairs']:
        path=root/pair['id']/'status.json'
        if path.exists(): workers[pair['id']]=load_json(path.read_bytes())
    duration=(utc_time(config['deadline_at'])-utc_time(config['started_at'])).total_seconds()
    expected=int(duration//config['poll_seconds'])
    audits=[]
    for path in root.glob('*/segment-*/audit.json'):
        audits.append({'path':str(path.relative_to(root)),**load_json(path.read_bytes())})
    combined={'schema':VERSION,'run':status,'workers':workers,'segment_audits':audits,
              'expected_full_window_samples_per_pair_at_target_cadence':expected,
              'total_observed_samples':sum(w['summary']['samples'] for w in workers.values()),
              'total_valid_data_samples':sum(w['summary']['quality_passes'] for w in workers.values()),
              'planned_pair_samples':expected*len(config['pairs']),
              'classification_counts':dict(Counter(p['classification'] for p in config['pairs'])),
              'strict_pairs':0,'ai_only_pairs':sum(p['ai_only'] for p in config['pairs']),
              'trading_authorized':False}
    atomic_json(root/'report.json',combined)
    lines=['# M5O — Continuous cross-market economic research','',
        '**Status: '+status['status']+'. Capture status is separate from research acceptance.**','',
        'Fixed window: '+config['started_at']+' through '+config['deadline_at']+'.',
        'Report generated: '+now().isoformat()+'. No orders, funds or approvals.','',
        'The run uses independent Kalshi clocked-stream receivers and public US REST full snapshots. '
        'US source/receipt ages and both cross-venue skews must be within two seconds; existing '
        'metadata, price/quantity grid, sequence and market-state checks also apply. Cached/quiet '
        'books remain rejected. US WebSocket continuity is not promoted into eligibility.','',
        '| Pair | Class / origin | Worker state | Samples | Valid data | Conditional gross samples |',
        '| --- | --- | --- | ---: | ---: | ---: |']
    for pair in config['pairs']:
        worker_status=workers.get(pair['id'],{}); s=worker_status.get('summary',empty_summary())
        lines.append(f"| {pair['id']} | {pair['classification']} / {pair['origin']} | {worker_status.get('status','NOT_STARTED')} | {s['samples']} | {s['quality_passes']} | {s['conditional_gross_samples']} |")
    lines += ['', f"Observed pair samples: **{combined['total_observed_samples']}** / **{combined['planned_pair_samples']}** planned over the full window; valid data samples: **{combined['total_valid_data_samples']}**. "
        'Startup, poll errors, processing/audit gaps and early worker endings remain in the planned denominator. '
        'These sample counts are not continuously verified market time.', '',
        f"Segment audits: {sum(a['replay']=='PASS' for a in audits)} passed, {sum(a['replay']!='PASS' for a in audits)} failed. Running segments are pending. "
        'Failed-audit observations cannot support final economic findings.', '',
        'STRICT pairs: **0**. Conditional and discovery labels are assistant research '
        'assessments; operator adjudication remains pending. Definitions changing during the run '
        'downgrade the affected observation to DISCOVERY. Discovery signals have no arbitrage calculation.','',
        '| Pair / quote budget | Positive gross samples | Sample clusters | Cluster span (s) | Max gross edge ($) | Max displayed quantity under budget |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for pair in config['pairs']:
        s=workers.get(pair['id'],{}).get('summary',empty_summary())
        for b,v in s['capital'].items():
            lines.append(f"| {pair['id']} / ${b} | {v['positive_samples']} | {v['sample_clusters']} | {v['positive_sample_cluster_span_seconds']:.3f} | {v['max_gross_edge_usd'] or 'UNKNOWN'} | {v['max_displayed_quantity'] or 'UNKNOWN'} |")
    lines += ['', 'Budgets above are combined **quote costs before unknown fees/collateral**. '
        'Depth is displayed, not a fill guarantee. The evaluated cash-long direction is Kalshi NO '
        '+ US YES; reverse US synthetic NO remains unsupported. Gross outcomes assume matching '
        'ordinary settlement. Net fee-adjusted returns, all-in capital, cash release and settlement '
        'delay remain UNKNOWN. Per-venue quote funding, exceptional zero-payout loss and explicitly '
        'hypothetical 1/2/5-cent combined fee sensitivities are in each observations.jsonl row.','',
        'Clusters group consecutive positive five-second samples with gaps at most seven seconds; '
        'their spans are **not continuously verified opportunity durations**. Rejections, gaps and '
        'segment changes break clusters. Zero positive samples with no valid comparisons cannot '
        'establish absence of opportunities. Fee sensitivity never creates an approved fee profile.','',
        'Risks: independent sports discretionary payouts; Fed cancellation/rescheduling and rate-range '
        'interpretation; labor/CPI revisions and fallback dates; gas observation-window mismatch; '
        'non-atomic fills, uncertain account costs/collateral and cash-release timing. All can erase '
        'gross discrepancies; selected legs can conditionally both pay zero. See candidate source reviews.','',
        'AI contribution: '+str(combined['ai_only_pairs'])+' AI-only pairs in this purposive sample. '
        'With no AI-only selected pairs, incremental semantic economic value is NOT ESTIMABLE; '
        'this is not evidence that AI has no value. See the source-bound historical ablation in '
        'config.json and docs/evidence/M5O_AI_ABLATION.json. Its additional ranked pairs '
        'carried proposition/date conflicts and were excluded. This measures bounded ranking changes, not '
        'representative recall or current-market AI yield. The index/model were not modified or reindexed.','',
        'Blockers: US caching/source freshness, quiet Kalshi reconnect gaps, unresolved exceptional '
        'payouts, unreviewed fees and collateral, and unknown actual fills. Recommended next step: '
        'complete and audit this fixed window, then prioritize any persistent gross discrepancy '
        'for source-bound fee/mechanics/settlement review. No M6 or trading authorization.','',
        'Evidence: `config.json`, `report.json`, per-pair status, per-segment raw SQLite archives, '
        'HTTP/WS timing journals, `observations.jsonl`, clock checks and offline `audit.json` files. '
        'Full raw bytes precede normalization. See docs/M5O_OPERATIONS.md for commands and limits.','']
    (root/'RESULTS.md').write_text('\n'.join(lines))
    if config.get('report_path'):
        path=Path(config['report_path']); temporary=path.with_suffix('.md.tmp')
        temporary.write_text('\n'.join(lines)); temporary.replace(path)
    return combined


def supervise(root, candidates, credentials_path, *, seconds, stop, report_path=None):
    if type(seconds) is not int or not 10<=seconds<=86400: raise ValueError('duration 10..86400 required')
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=False)
    started=now(); start=time.monotonic()
    config={'schema':VERSION,'started_at':started.isoformat(),
        'deadline_at':(started+timedelta(seconds=seconds)).isoformat(),'pairs':candidates['pairs'],
        'poll_seconds':5,'segment_seconds':900,'max_storage_bytes':20*1024**3,'min_free_bytes':2*1024**3,
        'candidate_manifest_sha256':hashlib.sha256(dumps(candidates).encode()).hexdigest(),
        'ai_ablation':candidates.get('ai_ablation'),
        'report_path':str(Path(report_path).resolve()) if report_path else None}
    validate_config(config)
    code_paths=[*Path(__file__).parent.glob('*.py'),SCRIPT]
    config['code_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in code_paths}
    atomic_json(root/'config.json',config); atomic_json(root/'candidates.json',candidates)
    clocks=clock_evidence(); atomic_json(root/'clock-before.json',clocks)
    if not clocks['synchronized']: raise ValueError('local synchronized clock required')
    code=root/'code'; code.mkdir()
    for path in code_paths:
        shutil.copy2(path,code/path.name)
    children=[]; state='RUNNING'; last_check=start-60
    def status():
        return {'schema':VERSION,'status':state,'heartbeat_at':now().isoformat(),
                'deadline_at':config['deadline_at'],'started_at':config['started_at'],
                'elapsed_seconds':time.monotonic()-start,'children':[{'id':i,'exit_code':p.poll()} for i,p in children]}
    try:
        for pair in config['pairs']:
            if stop.is_set() or remaining(config,start)<=0: break
            with (root/(pair['id']+'.stdout')).open('w') as out, (root/(pair['id']+'.stderr')).open('w') as err:
                p=subprocess.Popen([sys.executable,str(SCRIPT),'worker','--config',str(root/'config.json'),
                    '--pair',pair['id'],'--credentials',str(credentials_path)],stdout=out,stderr=err)
            children.append((pair['id'],p))
            stop.wait(.3)  # Stagger metadata calls/handshakes; no synchronized request burst.
        while remaining(config,start)>0 and not stop.is_set():
            if abs((now()-started).total_seconds()-(time.monotonic()-start))>1: state='WALL_CLOCK_JUMP'; break
            if all(p.poll() is not None for _,p in children): state='ALL_WORKERS_ENDED_EARLY'; break
            if time.monotonic()-last_check>=30:
                last_check=time.monotonic()
                if shutil.disk_usage(root).free<config['min_free_bytes']: state='LOW_DISK'; break
                if storage_bytes(root)>config['max_storage_bytes']: state='STORAGE_LIMIT'; break
                atomic_json(root/'status.json',status()); render(root,config,status())
            stop.wait(min(1,remaining(config,start)))
        if state=='RUNNING': state='INTERRUPTED' if stop.is_set() else 'DEADLINE_REACHED'
    except BaseException:
        state='SUPERVISOR_ERROR'
        raise
    finally:
        for _,p in children:
            if p.poll() is None: p.terminate()
        for _,p in children:
            try: p.wait(timeout=180)  # Receivers stop promptly; offline replay may finish afterward.
            except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=5); state='FORCED_WORKER_STOP'
        atomic_json(root/'clock-after.json',clock_evidence())
        atomic_json(root/'status.json',status()); render(root,config,status())
    return status()
