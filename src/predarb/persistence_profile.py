"""Bounded OFFLINE profiling of the unchanged Kalshi writer, never a live feed.

Instrumentation patches are process-local: call only in a dedicated serial process.
Historical clocks exercise validation; perf/thread clocks measure local work.
"""
from collections import defaultdict
from contextlib import ExitStack, closing, contextmanager
from datetime import timedelta
from decimal import Decimal
from functools import wraps
import hashlib
from pathlib import Path
import socket
import sqlite3
import time
from unittest.mock import patch

from . import kalshi, kalshi_ws, quality_capture, store, ws_store
from .backups import readonly, file_hash
from .book_stream import KalshiBookStream
from .conditional_research import contract_fingerprint
from .provider import Observation
from .quality_recovery import verify_raw
from .soak import atomic_json
from .validation import dumps, load_json, utc_time

VERSION = 'offline-persistence-profile/m5p-v1'


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def distribution(values):
    values = sorted(values)
    n = len(values)
    return dict(count=n, total_ns=sum(values), median_ns=(values[(n-1)//2]+values[n//2])//2 if n else None,
                p95_ns=values[(n*95+99)//100-1] if n else None, max_ns=max(values) if n else None)


class Timings:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.stack = []
        self.rows = defaultdict(list)

    @contextmanager
    def phase(self, name):
        if not self.enabled:
            yield
            return
        row = [name, time.perf_counter_ns(), time.thread_time_ns(), 0, 0]
        self.stack.append(row)
        try:
            yield
        finally:
            wall, cpu = time.perf_counter_ns()-row[1], time.thread_time_ns()-row[2]
            path = '/'.join(r[0] for r in self.stack)
            self.rows[path].append((wall, cpu, wall-row[3], cpu-row[4]))
            self.stack.pop()
            if self.stack:
                self.stack[-1][3] += wall
                self.stack[-1][4] += cpu

    def wrap(self, name, fn):
        @wraps(fn)
        def measured(*args, **kwargs):
            with self.phase(name):
                return fn(*args, **kwargs)
        return measured

    def report(self):
        return {key: {name: distribution([r[i] for r in rows]) for i, name in enumerate(
            ('inclusive_wall', 'inclusive_thread_cpu', 'exclusive_wall', 'exclusive_thread_cpu'))}
                for key, rows in sorted(self.rows.items())}


class MeasuredConnection:
    """Delegate real transactions unchanged; never suppress or defer a commit."""
    def __init__(self, con, timings):
        self.con, self.timings = con, timings

    def execute(self, *args, **kwargs):
        with self.timings.phase('sqlite_execute'):
            return self.con.execute(*args, **kwargs)

    def commit(self):
        with self.timings.phase('sqlite_commit'):
            return self.con.commit()

    def __getattr__(self, name):
        return getattr(self.con, name)


def source_case(source, pair, frames=256):
    """Freeze a bounded prefix of the FIRST connection, including its snapshot.

    Restrict to previously valid exact public wire bytes. Unsupported/redacted
    or rejected sources fail, rather than selecting another connection silently.
    """
    if type(frames) is not int or not 3 <= frames <= 1000:
        raise ValueError('frame budget must be 3..1000')
    path = Path(source)/pair['id']/'kalshi.sqlite3'
    with closing(readonly(path)) as con:
        connection = con.execute('SELECT id,source_id,metadata_observation_id,started_at,ended_at FROM ws_connections ORDER BY id LIMIT 1').fetchone()
        if not connection or connection[1] != pair['kalshi_id'] or connection[4] is None:
            raise ValueError('missing, mismatched or unfinished source connection')
        def raw(oid):
            r = con.execute('SELECT raw_body,body_sha256,ts_utc,schema_version,validation_status,endpoint,http_status,truncated FROM raw_observations WHERE id=?',(oid,)).fetchone()
            if not r or r[0] is None or hashlib.sha256(r[0]).hexdigest()!=r[1] or r[4]!='VALID' or r[7]:
                raise ValueError('source raw integrity/status mismatch')
            return dict(body=r[0].decode(),sha256=r[1],received_at=r[2],schema_version=r[3],endpoint=r[5],http_status=r[6],source_observation_id=oid)
        meta = raw(connection[2])
        if (meta['schema_version']!=kalshi.SCHEMA_VERSION or meta['endpoint']!=kalshi.detail_url(pair['kalshi_id']) or meta['http_status']!=200):
            raise ValueError('source metadata provenance mismatch')
        rows=[]
        for oid, wire, kind in con.execute('SELECT observation_id,wire_sha256,archive_kind FROM ws_frames WHERE connection_id=? ORDER BY observation_id LIMIT ?', (connection[0], frames)):
            r=raw(oid)
            if kind!='EXACT_WIRE' or wire!=r['sha256'] or r['schema_version']!=ws_store.SCHEMA_VERSION or r['endpoint']!=kalshi_ws.WS_URL or r['http_status']!=101:
                raise ValueError('unsupported source frame provenance')
            frame=load_json(r['body'])
            if frame.get('type') not in {'subscribed','orderbook_snapshot','orderbook_delta'}:
                raise ValueError('profile prefix does not support control/unknown frames')
            expected=con.execute('SELECT result_json FROM normalized_books WHERE observation_id=?',(oid,)).fetchone()
            r['expected_book']=load_json(expected[0]) if expected else None
            rows.append(r)
        if len(rows)<3 or load_json(rows[0]['body']).get('type')!='subscribed' or load_json(rows[1]['body']).get('type')!='orderbook_snapshot':
            raise ValueError('profile needs acknowledgment, snapshot and following frame')
    return dict(schema=VERSION, hypothetical=False, source=str(path), source_sha256=file_hash(path),
                source_connection_id=connection[0], started_at=connection[3], pair=pair,
                metadata=meta, frames=rows, prefix_limit=frames)


class HistoricalSocket:
    """HYPOTHETICAL transport only; bodies and receipt clocks remain source exact."""
    def __init__(self, case):
        self.frames = iter(case['frames'])
        self.start = utc_time(case['started_at'])
        self.at = self.start
        self.sent = []
        self.receive_started_ns = None
        self.delivered = 0

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def now(self): return self.at
    def monotonic(self): return (self.at-self.start).total_seconds()

    def recv(self, **_):
        row = next(self.frames)
        self.at = utc_time(row['received_at'])
        self.receive_started_ns = time.perf_counter_ns()
        self.delivered += 1
        return row['body'].encode()

    def send(self, value):
        command = load_json(value)
        if command.get('cmd') not in {'subscribe','update_subscription'}:
            raise ValueError('unexpected offline command')
        self.sent.append(command)


class OfflineCredentials:
    def headers(self):
        return {'KALSHI-ACCESS-KEY':'HYPOTHETICAL_OFFLINE_KEY',
                'KALSHI-ACCESS-SIGNATURE':'HYPOTHETICAL_OFFLINE_SIGNATURE'}


def run_case(case, output, *, instrumented=True, timeout_seconds=120):
    """Run actual capture/storage/validation functions against an offline socket.

    Journal uses historical receive clocks and only the Kalshi channel; it is a
    cost probe, NOT a coverage simulation. No source archive is opened writable.
    """
    if case.get('schema')!=VERSION or not 3<=len(case['frames'])<=1000:
        raise ValueError('invalid profile fixture/bounds')
    for row in [case['metadata'],*case['frames']]:
        if hashlib.sha256(row['body'].encode()).hexdigest()!=row['sha256']:
            raise ValueError('fixture hash mismatch')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    output.chmod(0o700)
    atomic_json(output/'status.json',dict(schema=VERSION,status='RUNNING',offline=True))
    timings=Timings(instrumented);transport=HistoricalSocket(case)
    pair=case['pair'];meta=case['metadata'];latencies=[];admitted=[]
    config=dict(started_at=case['started_at'],deadline_at=(transport.start+timedelta(seconds=3600)).isoformat())
    journal=quality_capture.Journal(output,pair,config)
    hard_end=time.monotonic()+timeout_seconds
    try:
        with store.connect(str(output/'profile.sqlite3')) as real:
            settings={key:real.execute('PRAGMA '+key).fetchone()[0] for key in
                      ('journal_mode','synchronous','wal_autocheckpoint','page_size','foreign_keys')}
            if settings['journal_mode']!='wal' or settings['synchronous']!=2 or settings['foreign_keys']!=1:
                raise ValueError('profile requires unchanged WAL/FULL/foreign_keys settings')
            # Metadata seeding and migrations are outside measured per-frame capture.
            run=store.start_run(real,'kalshi',kalshi.SCHEMA_VERSION,{'scope':'OFFLINE_PROFILE'})
            oid=store.archive_response(real,'kalshi',meta['endpoint'],meta['body'].encode(),200,{},meta['received_at'],kalshi.SCHEMA_VERSION)
            data=load_json(meta['body']);kalshi.validate_detail(data)
            store.validate_observation(real,oid,'VALID',None)
            detail=Observation(oid,meta['endpoint'],meta['received_at'],data)
            store.save_entry(real,run,detail,pair['kalshi_id'],data['market'],kalshi.rules(data['market']),data['market'][kalshi.TIME_FIELD])
            store.update_run(real,run,status='COMPLETE',pages=1,records=1,unique=1,next_page=None)
            con=MeasuredConnection(real,timings) if instrumented else real

            def state(db,event,book):
                with timings.phase('state_callback'):
                    event=dict(event,channel='kalshi')
                    if book:
                        with timings.phase('source_fingerprint'):
                            raw=db.execute('SELECT raw_body,body_sha256 FROM raw_observations WHERE id=?',(event['metadata_observation_id'],)).fetchone()
                            event['source_changed']=contract_fingerprint('kalshi',load_json(raw[0])['market'])!=pair['contract_fingerprints']['kalshi']
                            event['metadata_sha256']=raw[1]
                    journal.event(event,book)
                if book:
                    latencies.append(time.perf_counter_ns()-transport.receive_started_ns)
                    admitted.append(event['observation_id'])

            with ExitStack() as stack:
                stack.enter_context(patch('socket.socket',side_effect=AssertionError('network forbidden in offline profiler')))
                stack.enter_context(patch.object(quality_capture,'now',transport.now))
                if instrumented:
                    for obj,name,label in [(ws_store,'archive_frame','archive_frame'),(ws_store,'safe_frame','privacy_screen'),
                        (ws_store,'archive_response','archive_raw'),(ws_store,'record_frame','record_frame'),
                        (ws_store,'validate_observation','validation_status'),(kalshi_ws,'validate_observation','validation_status'),
                        (KalshiBookStream,'apply','stream_apply'),(quality_capture.Journal,'event','journal_event'),
                        (quality_capture.Engine,'event','engine_event'),(quality_capture,'append','journal_append')]:
                        stack.enter_context(patch.object(obj,name,timings.wrap(label,getattr(obj,name))))
                started=time.perf_counter_ns();cpu=time.thread_time_ns()
                with timings.phase('capture'):
                    stats=kalshi_ws.capture(con,pair['kalshi_id'],OfflineCredentials(),seconds=3600,
                        max_messages=len(case['frames']),max_connections=1,directory=output,
                        connect_socket=lambda _:transport,metadata_loader=lambda *_:(run,detail),
                        now=transport.now,monotonic=transport.monotonic,sleep=lambda _:None,
                        on_tick=lambda *_:time.monotonic()>=hard_end,on_state=state,
                        on_receive=lambda r:quality_capture.append(output/'receive.jsonl',r),recovery_policy='inband-snapshot')
                elapsed=time.perf_counter_ns()-started;cpu=time.thread_time_ns()-cpu
            # Post-timing: compare EVERY persisted normalized book and raw frame
            # against its original, not merely the final ladder or a row count.
            observed=real.execute('SELECT r.raw_body,r.body_sha256,r.validation_status,n.result_json FROM ws_frames f JOIN raw_observations r ON r.id=f.observation_id LEFT JOIN normalized_books n ON n.observation_id=r.id ORDER BY r.id').fetchall()
            if len(observed)!=len(case['frames']) or stats['failures'] or transport.delivered!=len(case['frames']):
                raise ValueError('incomplete offline capture')
            results=[]
            for row, expected in zip(observed,case['frames']):
                result=load_json(row[3]) if row[3] else None
                if row[0]!=expected['body'].encode() or row[1]!=expected['sha256'] or row[2]!='VALID' or result!=expected['expected_book']:
                    raise ValueError('raw/normalized parity mismatch')
                results.append(result)
            if len(admitted)!=sum(r is not None for r in results):
                raise ValueError('book publication mismatch')
            if real.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or real.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('profile archive integrity failed')
        head='0'*64;pending=set();books=0
        for n,line in enumerate((output/'events.jsonl').read_text().splitlines(),1):
            e=load_json(line);base={k:v for k,v in e.items() if k!='sha256'}
            if e['number']!=n or e['previous_sha256']!=head or digest(base)!=e['sha256']:
                raise ValueError('profile journal hash mismatch')
            head=e['sha256']
            if e['kind']=='pending':pending.add(e['observation_id'])
            if e['kind']=='book':
                if e['observation_id'] not in pending:raise ValueError('publication without pending barrier')
                pending.remove(e['observation_id']);books+=1
        if books!=len(admitted):raise ValueError('journal publication count mismatch')
        result=dict(schema=VERSION,offline=True,historical_clocks=True,instrumented=instrumented,
            status='PASS',settings=settings,sqlite_version=sqlite3.sqlite_version,frames=len(observed),books=books,
            capture_wall_ns=elapsed,capture_thread_cpu_ns=cpu,receipt_to_callback=distribution(latencies),
            phases=timings.report(),capture_stats=stats,normalized_sha256=digest(results),
            raw_hashes_verified=verify_raw(output/'profile.sqlite3'),journal_chain_verified=True,
            historical_case_sha256=digest(case),trading_authorized=False,
            limitation='Serial unpaced offline prefix; Kalshi-only journal, no other receivers, sampling or network waits. Historical clocks are NOT measured coverage. Commit wall time includes synchronization/checkpoint/scheduling, not isolated device latency.')
        atomic_json(output/'result.json',result)
        atomic_json(output/'status.json',dict(schema=VERSION,status='PASS',offline=True))
        return result
    except BaseException as exc:
        atomic_json(output/'status.json',dict(schema=VERSION,status='FAILED',offline=True,error_type=type(exc).__name__))
        raise
