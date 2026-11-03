"""M5P bounded research streams and event-time quality accounting.

No registry approvals or production economic integration. A passing local state
does not prove continuous exchange validity; US gap detection remains UNKNOWN.
"""
from collections import Counter
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
import shutil
import threading
import time

from . import kalshi_ws, polymarket_us as us, us_stream_probe, ws_store
from .backups import readonly
from .book_stream import KalshiBookStream
from .conditional_research import contract_fingerprint, quote_cases, quality
from .continuous_research import DeadlineClient, append
from .kalshi_auth import Credentials as KalshiCredentials
from .orderbooks import normalize_rest
from .quality_recovery import VERSION, json_lines, tally, verify_raw
from .soak import atomic_json
from .store import connect
from .stream_comparison import clock_evidence, comparison
from .validation import dumps, load_json, utc_time

CHANNELS = ('kalshi', 'us_ws', 'us_rest')


def now():
    return datetime.now(timezone.utc)


def seconds(delta):
    return Decimal(delta.days*86400)+Decimal(delta.seconds)+Decimal(delta.microseconds)/1000000


def validate_window(seconds_requested, pairs):
    if type(seconds_requested) is not int or not 10 <= seconds_requested <= 900:
        raise ValueError('M5P duration must be 10..900 seconds; no automatic extension')
    if not 2 <= len(pairs) <= 3 or len({p['id'] for p in pairs}) != len(pairs):
        raise ValueError('two or three distinct pairs required')
    for key in ('kalshi_id', 'polymarket_us_id'):
        if len({p[key] for p in pairs}) != len(pairs): raise ValueError('duplicate instrument')
    from .conditional_research import classification
    from .validation import identifier
    for p in pairs:
        classification(p)
        for key in ('id','kalshi_id','polymarket_us_id'): identifier(p[key])
        if set(p['contract_fingerprints']) != {'kalshi','polymarket_us'}:
            raise ValueError('source-bound fingerprints required')


def validate_config(config):
    if config.get('schema') != VERSION: raise ValueError('unknown M5P configuration schema')
    validate_window(config['seconds'],config['pairs'])
    if seconds(utc_time(config['deadline_at'])-utc_time(config['started_at'])) != config['seconds']:
        raise ValueError('fixed deadline differs from bounded duration')
    from .snapshot_recovery import POLICIES
    if config.get('kalshi_recovery_policy','reconnect') not in POLICIES:
        raise ValueError('unknown recovery policy')


class State:
    """Seven separate clocks. Observed mutation time is never exchange mutation time."""
    def __init__(self):
        self.book = None
        self.blocker = 'MISSING_BOOK'
        self.generation = None
        self.last_mutation_observed_at = None
        self.last_verified_snapshot_at = None
        self.last_authenticated_validated_activity_at = None
        self.last_continuity_loss_at = None
        self.local_receipt_at = None
        self.source_timestamp = None
        self.request_response_interval = None
        self.depth = None
        self.source_changed = False

    def apply(self, event, book=None):
        at, kind = event['at'], event['kind']
        if kind in {'disconnect','invalid','pending','metadata_invalid'}:
            self.blocker = event.get('reason', kind.upper())
            if kind != 'pending':
                self.last_continuity_loss_at = at
                self.depth = None  # Never infer mutation across an unknown interval.
            return
        if kind in {'heartbeat','control'}:
            self.last_authenticated_validated_activity_at = event['received_at']
            return  # A heartbeat does not refresh or rehabilitate the book.
        if kind != 'book' or book is None: raise ValueError('unknown quality event')
        generation = event.get('generation', event.get('connection_id'))
        depth = hashlib.sha256(dumps([[(x.price,x.quantity) for x in levels]
            for levels in (book.yes_asks,book.no_asks)]).encode()).hexdigest()
        structurally_valid = all(r in {'EMPTY_BOOK','PARTIAL_BOOK'} for r in book.rejections)
        if generation != self.generation:
            self.depth = None
            self.last_mutation_observed_at = None
        if structurally_valid and self.depth is not None and depth != self.depth:
            self.last_mutation_observed_at = book.received_at
        self.generation, self.depth, self.book = generation, depth if structurally_valid else None, book
        self.blocker = None
        self.source_changed = event.get('source_changed', False)
        if structurally_valid and event.get('snapshot'): self.last_verified_snapshot_at = at
        if structurally_valid and event['channel'] != 'us_rest': self.last_authenticated_validated_activity_at = book.received_at
        if not structurally_valid: self.last_continuity_loss_at = at
        self.local_receipt_at, self.source_timestamp = book.received_at, book.source_ts
        self.request_response_interval = event.get('request_response_interval')

    def report(self):
        return {k:v for k,v in self.__dict__.items() if k not in {'book','depth'}} | {
            'mutation_time_meaning':'LOCAL_OBSERVED_DEPTH_CHANGE; initial/generation interval left-censored',
            'exchange_mutation_time':'UNKNOWN', 'depth_sha256':self.depth}


class Engine:
    def __init__(self, pair, start, deadline):
        self.pair, self.start, self.deadline = pair, utc_time(start), utc_time(deadline)
        self.previous = self.start
        self.states = {c:State() for c in CHANNELS}
        self.coverage = {c:Decimal(0) for c in ('us_ws','us_rest')}
        self.reason_seconds = {c:Counter() for c in ('us_ws','us_rest')}
        self.synchronized = True
        self.event_count = 0

    def assess(self, channel, at, economics=False):
        states = [self.states[c] for c in ('kalshi',channel)]
        reports = {}
        for venue, state in zip(('kalshi','polymarket_us'),states):
            b = state.book
            if b is None:
                reports[venue] = None
                continue
            rejects = list(b.issues(now=at))
            if state.blocker: rejects.append(state.blocker)
            if not self.synchronized: rejects.append('LOCAL_CLOCK_UNVERIFIED')
            reports[venue] = dict(source_ts=b.source_ts, received_at=b.received_at,
                rejections=rejects, data_usable=not rejects, connected=state.blocker is None)
        checked = comparison(reports,at)
        result = dict(quality=checked, at=at.isoformat(), strict_arbitrage_eligible=False,
                      trading_authorized=False)
        if economics and all(s.book for s in states):
            p = dict(self.pair)
            if any(s.source_changed for s in states): p['classification'] = 'DISCOVERY'
            result.update(quote_cases([s.book for s in states],p,now=at,
                inspected=[reports['kalshi'],reports['polymarket_us']]))
        return result

    def advance(self, at):
        at = min(utc_time(at),self.deadline)
        if at < self.previous: raise ValueError('event clock regressed')
        cuts = {self.previous,at}
        for state in self.states.values():
            b = state.book
            if b is None: continue
            stamps = [(b.received_at,2),(b.source_ts,2),(b.metadata_received_at,60),(b.market_close_at,0)]
            for stamp, age in stamps:
                if stamp:
                    expiry = utc_time(stamp)+timedelta(seconds=age)
                    if self.previous < expiry < at: cuts.add(expiry)
                    if self.previous < utc_time(stamp) < at: cuts.add(utc_time(stamp))
        ordered = sorted(cuts)
        for left, right in zip(ordered,ordered[1:]):
            width = seconds(right-left)
            # Midpoint avoids treating an inclusive two-second boundary as an interval.
            midpoint = left+(right-left)/2
            for channel in self.coverage:
                q = self.assess(channel,midpoint)['quality']
                if q['timestamp_depth_overlap']: self.coverage[channel] += width
                for code in q['rejections']: self.reason_seconds[channel][code] += width
        self.previous = at

    def event(self, event, book=None):
        self.advance(event['at'])
        if utc_time(event['at']) >= self.deadline: return
        self.event_count += 1
        if event['kind'] == 'clock': self.synchronized = event['synchronized']
        else: self.states[event['channel']].apply(event,book)

    def finish(self):
        self.advance(self.deadline.isoformat())
        total = seconds(self.deadline-self.start)
        return dict(schema=VERSION, events=self.event_count, planned_wall_seconds=total,
            valid_local_market_state_seconds=self.coverage,
            valid_local_market_state_percent={c:v*100/total for c,v in self.coverage.items()},
            simultaneous_rejection_seconds=self.reason_seconds,
            metric='Event availability intervals, capped at unchanged source/receipt/metadata expiry; startup, disconnect and worker gaps included.',
            continuous_exchange_validity='UNKNOWN; US has no consumed gap-detection sequence',
            economic_eligibility=False, trading_authorized=False)


class Journal:
    def __init__(self, root, pair, config):
        self.root, self.pair = root, pair
        self.engine = Engine(pair,config['started_at'],config['deadline_at'])
        self.lock = threading.RLock()
        self.head = '0'*64
        self.number = 0
        self.latest_metadata = None
        self.rows = {'us_ws':[], 'us_rest':[]}

    def event(self, event, book=None):
        with self.lock:
            if now() >= self.engine.deadline: return
            self.number += 1
            row = dict(event, at=now().isoformat(), monotonic=time.monotonic(),
                       number=self.number, previous_sha256=self.head)
            # Canonical Decimal/string representation must survive the exact
            # parser used by offline replay (JSON floats otherwise re-encode
            # differently after Decimal parsing).
            row = load_json(dumps(row))
            self.head = hashlib.sha256(dumps(row).encode()).hexdigest()
            append(self.root/'events.jsonl',dict(row,sha256=self.head))
            self.engine.event(row,book)

    def sample(self):
        with self.lock:
            at = now()
            if at >= self.engine.deadline: return
            for channel in self.rows:
                row = self.engine.assess(channel,at,economics=True)
                row.update(channel=channel,event_number=self.number,event_sha256=self.head,
                    clocks={c:self.engine.states[c].report() for c in ('kalshi',channel)})
                append(self.root/'samples.jsonl',row); self.rows[channel].append(row)


def rest_failure(journal, *, metadata_confirmed):
    """A REST book-request failure must not invalidate independently valid metadata."""
    journal.event(dict(kind='disconnect',channel='us_rest',reason='REST_REQUEST_OR_METADATA_ERROR'))
    if not metadata_confirmed:
        with journal.lock: journal.latest_metadata = None
        journal.event(dict(kind='metadata_invalid',channel='us_ws',reason='METADATA_UNAVAILABLE'))


def worker(root, pair, config, kcredentials, ucredentials, stop):
    validate_config(config)
    if not utc_time(config['started_at']) <= now() < utc_time(config['deadline_at']):
        raise ValueError('worker outside original fixed window')
    root = Path(root); root.mkdir(parents=True,exist_ok=False)
    root.chmod(0o700)
    (root/'events.jsonl').touch(); (root/'samples.jsonl').touch()
    journal = Journal(root,pair,config)
    started = time.monotonic(); wall_started = now()
    deadline = utc_time(config['deadline_at'])
    duration = max(0,(deadline-wall_started).total_seconds())
    errors = []; receiver_results = {}; local_stop = threading.Event()
    def guard(*_):
        return stop.is_set() or local_stop.is_set() or now()>=deadline or time.monotonic()-started>=duration
    def loss(channel, reason): journal.event(dict(kind='disconnect',channel=channel,reason=reason))

    def kalshi_receiver():
        try:
            with connect(str(root/'kalshi.sqlite3')) as con:
                client = DeadlineClient(con,'kalshi',emit=lambda r:append(root/'kalshi-timing.jsonl',r),
                                        attempts=1,timeout=3,interval=1,guard=guard)
                def state(db,event,book):
                    event = dict(event,channel='kalshi')
                    if book:
                        raw = db.execute('SELECT raw_body,body_sha256 FROM raw_observations WHERE id=?',
                                         (event['metadata_observation_id'],)).fetchone()
                        event['source_changed'] = contract_fingerprint('kalshi',load_json(raw[0])['market']) != pair['contract_fingerprints']['kalshi']
                        event['metadata_sha256'] = raw[1]
                    journal.event(event,book)
                receiver_results['kalshi'] = kalshi_ws.capture(con,pair['kalshi_id'],kcredentials,
                    seconds=max(1,int(duration)),max_connections=120,max_messages=100000,directory=root,
                    metadata_loader=lambda db,sid:kalshi_ws.refresh_metadata(db,sid,client=client),
                    on_tick=guard,on_state=state,
                    recovery_policy=config.get('kalshi_recovery_policy','reconnect'),
                    on_receive=lambda r:append(root/'kalshi-timing.jsonl',r))
        except Exception as exc: errors.append({'channel':'kalshi','error_type':type(exc).__name__})
        finally: loss('kalshi','RECEIVER_ENDED')

    def rest_receiver():
        try:
            with connect(str(root/'us.sqlite3')) as con:
                client = DeadlineClient(con,'polymarket_us',emit=lambda r:append(root/'us-timing.jsonl',r),
                                        attempts=1,timeout=3,interval=1,guard=guard)
                while not guard():
                    before = time.monotonic()
                    metadata_confirmed = False
                    try:
                        meta = client.get(us.detail_url(pair['polymarket_us_id']),us.SCHEMA_VERSION,us.validate_detail)
                        from .orderbooks import market_rules
                        market_rules('polymarket_us',pair['polymarket_us_id'],meta.data['market'],now=now())
                        with journal.lock: journal.latest_metadata = meta
                        metadata_confirmed = True
                        raw = client.get(us.book_url(pair['polymarket_us_id']),us.SCHEMA_VERSION,us.validate_book)
                        book = normalize_rest('polymarket_us',pair['polymarket_us_id'],raw.data,meta.data['market'],
                            received_at=raw.received_at,metadata_received_at=meta.received_at,now=utc_time(raw.received_at))
                        journal.event(dict(kind='book',channel='us_rest',snapshot=True,
                            observation_id=raw.id,metadata_observation_id=meta.id,
                            request_response_interval={k:client.current.get(k) for k in ('request_started_at','received_at','request_monotonic','receive_monotonic')},
                            source_changed=contract_fingerprint('polymarket_us',meta.data['market'])!=pair['contract_fingerprints']['polymarket_us']),book)
                    except (ValueError,OSError,KeyError):
                        rest_failure(journal,metadata_confirmed=metadata_confirmed)
                    local_stop.wait(max(0,min(5-(time.monotonic()-before),(deadline-now()).total_seconds())))
        except Exception as exc: errors.append({'channel':'us_rest','error_type':type(exc).__name__})
        finally: loss('us_rest','RECEIVER_ENDED')

    def us_receiver():
        try:
            credential = ucredentials
            receiver_results['us_ws'] = []
            for generation in range(1,21):
                if guard(): break
                folder = root/f'us-stream-{generation:03d}'
                def event(row):
                    ref = dict(channel='us_ws',generation=generation,raw_file=str(folder.name+'/'+row['raw_file']),
                               archive_sha256=row['archive_sha256'])
                    if row.get('rejection'):
                        journal.event(dict(ref,kind='invalid',reason=row['rejection'])); return
                    if row.get('kind')=='heartbeat':
                        journal.event(dict(ref,kind='heartbeat',received_at=row['received_at'])); return
                    with journal.lock: meta = journal.latest_metadata
                    if meta is None:
                        journal.event(dict(ref,kind='invalid',reason='METADATA_UNAVAILABLE')); return
                    book = normalize_rest('polymarket_us',pair['polymarket_us_id'],load_json((folder/row['raw_file']).read_bytes()),
                        meta.data['market'],received_at=row['received_at'],metadata_received_at=meta.received_at,now=utc_time(row['received_at']))
                    # Isolated full-frame normalization; never writes production books.
                    extra = tuple(r for r in row['rejections'] if r not in {'SOURCE_AGE_GT_2S','PARTIAL_OR_EMPTY_BOOK'})
                    book = replace(book,transport='US_AUTHENTICATED_WS_RESEARCH',continuity='UNKNOWN',rejections=book.rejections+extra)
                    journal.event(dict(ref,kind='book',snapshot=True,metadata_observation_id=meta.id,
                        source_changed=contract_fingerprint('polymarket_us',meta.data['market'])!=pair['contract_fingerprints']['polymarket_us']),book)
                result = us_stream_probe.capture(folder,credential,[pair['polymarket_us_id']],
                    seconds=max(1,min(450,int((deadline-now()).total_seconds()))),stop=local_stop,on_event=event)
                receiver_results['us_ws'].append(dict(directory=folder.name,reason=result['reason']))
                loss('us_ws',result['reason'])
                if result['reason'] in {'LOW_DISK','WALL_CLOCK_JUMP','UNSAFE_OR_UNKNOWN_FRAME'}: break
                if guard(): break
                local_stop.wait(min(2,(deadline-now()).total_seconds()))
        except Exception as exc: errors.append({'channel':'us_ws','error_type':type(exc).__name__})
        finally: loss('us_ws','RECEIVER_ENDED')

    threads = [threading.Thread(target=fn,daemon=True,name=name) for name,fn in
               [('kalshi',kalshi_receiver),('us_rest',rest_receiver),('us_ws',us_receiver)]]
    for thread in threads: thread.start()
    next_sample = started; next_clock = started; reason = 'DEADLINE_REACHED'
    early = {}
    try:
        while not guard():
            mono = time.monotonic()
            if abs((now()-wall_started).total_seconds()-(mono-started))>1:
                reason='WALL_CLOCK_JUMP';break
            if mono >= next_clock:
                clock = clock_evidence(); append(root/'clock-checks.jsonl',clock)
                journal.event(dict(kind='clock',synchronized=clock['synchronized']))
                if not clock['synchronized']: reason='LOCAL_CLOCK_UNVERIFIED';break
                if shutil.disk_usage(root).free < 2*1024**3: reason='LOW_DISK';break
                from .soak import storage_bytes
                if storage_bytes(root)>2*1024**3: reason='STORAGE_LIMIT';break
                next_clock=mono+30
            for thread in threads:
                if not thread.is_alive() and (deadline-now()).total_seconds()>2:
                    early.setdefault(thread.name,now().isoformat())
            if mono >= next_sample:
                journal.sample(); next_sample=mono+1
            stop.wait(.05)
    finally:
        local_stop.set()
        for thread in threads: thread.join(timeout=15)
        if any(t.is_alive() for t in threads): reason='RECEIVER_STOP_TIMEOUT'
        if stop.is_set() and now()<deadline: reason='INTERRUPTED'
        # Missing final receiver callbacks cannot extend a state to the deadline.
        for c in CHANNELS: loss(c,'WORKER_STOP')
        with journal.lock:
            report = journal.engine.finish()
            report.update(pair_id=pair['id'],status=reason,errors=errors,early_receivers=early,
                receiver_results=receiver_results,event_sha256=journal.head,event_count=journal.number,
                samples={c:tally(rows) for c,rows in journal.rows.items()},
                positive_gross_samples={c:sum(any(x['positive_conditional_discrepancy'] for x in r.get('capital_cases',[]))
                    for r in rows) for c,rows in journal.rows.items()})
            atomic_json(root/'result.json',report)
    return report


def replay(root, pair, config, *, event_observer=None):
    """Rebuild every admitted book from archived raw data, then all event intervals.

    Receive time and local availability time are distinct. No later message is
    allowed to replace the state available to an earlier sample.
    """
    validate_config(config)
    root = Path(root)
    result = load_json((root/'result.json').read_bytes())
    events = list(json_lines(root/'events.jsonl'))
    samples = list(json_lines(root/'samples.jsonl'))
    engine = Engine(pair,config['started_at'],config['deadline_at'])
    stream = None; generation = None; sid = None
    head = '0'*64; sample_index = 0; verified_us = {}; us_rows = {}; acknowledged=set()
    for folder in sorted(root.glob('us-stream-*')):
        verified_us[folder.name] = us_stream_probe.replay(folder)
        for r in json_lines(folder/'timing.jsonl'): us_rows[folder.name+'/'+r['raw_file']] = r
    def raw(con, oid):
        row = con.execute('SELECT raw_body,body_sha256,ts_utc,validation_status,schema_version,endpoint FROM raw_observations WHERE id=?',(oid,)).fetchone()
        if row is None or hashlib.sha256(row[0]).hexdigest()!=row[1]: raise ValueError('raw provenance mismatch')
        return load_json(row[0]),row
    def check_samples(number, next_at):
        nonlocal sample_index
        while sample_index < len(samples) and samples[sample_index]['event_number']==number:
            saved=samples[sample_index]; at=utc_time(saved['at'])
            if not engine.previous <= at < next_at or saved['event_sha256']!=head:
                raise ValueError('sample visibility mismatch')
            computed=engine.assess(saved['channel'],at,economics=True)
            if load_json(dumps(computed)) != {k:saved[k] for k in computed}:
                raise ValueError('sample replay mismatch')
            clocks={c:engine.states[c].report() for c in ('kalshi',saved['channel'])}
            if load_json(dumps(clocks)) != saved['clocks']: raise ValueError('instrumentation clock mismatch')
            sample_index+=1
    with closing(readonly(root/'kalshi.sqlite3')) as kc, closing(readonly(root/'us.sqlite3')) as uc:
        for i,event in enumerate(events,1):
            check_samples(i-1,utc_time(event['at']))
            digest=event['sha256']; base={k:v for k,v in event.items() if k!='sha256'}
            if event['number']!=i or event['previous_sha256']!=head or hashlib.sha256(dumps(base).encode()).hexdigest()!=digest:
                raise ValueError('event journal integrity mismatch')
            if not utc_time(config['started_at']) <= utc_time(event['at']) < utc_time(config['deadline_at']):
                raise ValueError('event outside fixed deadline')
            head=digest; book=None
            channel=event.get('channel'); kind=event['kind']
            if channel=='kalshi' and kind in {'pending','book','control'}:
                payload,r=raw(kc,event['observation_id'])
                frame=kc.execute('SELECT connection_id,wire_sha256,archive_kind FROM ws_frames WHERE observation_id=?',(event['observation_id'],)).fetchone()
                if not frame or frame[0]!=event['connection_id'] or r[4]!=ws_store.PROTOCOL_SCHEMAS['clocked']:
                    raise ValueError('Kalshi frame identity mismatch')
                if frame[2]=='EXACT_WIRE' and frame[1]!=r[1]: raise ValueError('wire hash mismatch')
                if kind=='pending' and payload.get('type')=='subscribed' and r[3]=='VALID':
                    sid=payload['msg']['sid']
                if kind=='control':
                    from .snapshot_recovery import acknowledge, load_command
                    if config.get('kalshi_recovery_policy')!='inband-snapshot' or stream is None or generation!=event['connection_id'] or r[3]!='VALID':
                        raise ValueError('unapproved control replay context')
                    request=load_command(kc,event['command_observation_id'],generation,pair['kalshi_id'],sid,r[2])
                    key=(generation,request['id'])
                    if key in acknowledged or event['received_at']!=r[2]:raise ValueError('control provenance mismatch')
                    acknowledge(stream,payload,request);acknowledged.add(key)
                if kind=='book':
                    meta,mr=raw(kc,event['metadata_observation_id'])
                    if r[3]!='VALID' or mr[3]!='VALID' or mr[1]!=event['metadata_sha256'] or payload.get('sid')!=sid:
                        raise ValueError('invalid admitted Kalshi provenance')
                    if generation!=event['connection_id']:
                        stream=KalshiBookStream(pair['kalshi_id'],meta['market'],metadata_received_at=mr[2])
                        generation=event['connection_id'];stream.generation=generation
                    book=stream.apply(payload,received_at=r[2],now=utc_time(r[2]),generation=generation)
                    book=replace(book,transport='KALSHI_AUTHENTICATED_WS')
                    changed=contract_fingerprint('kalshi',meta['market'])!=pair['contract_fingerprints']['kalshi']
                    if changed!=event['source_changed']: raise ValueError('source fingerprint mismatch')
            elif channel in {'us_ws','us_rest'} and kind=='book':
                meta,mr=raw(uc,event['metadata_observation_id'])
                if mr[3]!='VALID': raise ValueError('invalid US metadata')
                if channel=='us_rest':
                    payload,r=raw(uc,event['observation_id']);received=r[2]
                    if r[3]!='VALID' or r[4]!=us.SCHEMA_VERSION or r[5]!=us.book_url(pair['polymarket_us_id']):
                        raise ValueError('invalid US REST provenance')
                else:
                    r=us_rows[event['raw_file']]
                    if r['archive_sha256']!=event['archive_sha256'] or r.get('kind')!='book':
                        raise ValueError('invalid US stream provenance')
                    payload=load_json((root/event['raw_file']).read_bytes());received=r['received_at']
                book=normalize_rest('polymarket_us',pair['polymarket_us_id'],payload,meta['market'],
                    received_at=received,metadata_received_at=mr[2],now=utc_time(received))
                if channel=='us_ws':
                    extra=tuple(v for v in r['rejections'] if v not in {'SOURCE_AGE_GT_2S','PARTIAL_OR_EMPTY_BOOK'})
                    book=replace(book,transport='US_AUTHENTICATED_WS_RESEARCH',continuity='UNKNOWN',rejections=book.rejections+extra)
                if (contract_fingerprint('polymarket_us',meta['market'])!=pair['contract_fingerprints']['polymarket_us'])!=event['source_changed']:
                    raise ValueError('source fingerprint mismatch')
            elif channel=='us_ws' and kind=='heartbeat':
                if us_rows[event['raw_file']].get('kind')!='heartbeat': raise ValueError('heartbeat provenance mismatch')
            if book and utc_time(book.received_at)>utc_time(event['at']): raise ValueError('book used before receipt')
            engine.event(event,book)
            if event_observer is not None:event_observer(event,book)
        check_samples(len(events),utc_time(config['deadline_at']))
        if sample_index!=len(samples): raise ValueError('unreplayed samples')
        if kc.execute('SELECT count(*) FROM ws_connections WHERE ended_at IS NULL').fetchone()[0]:
            raise ValueError('unfinished connection')
    computed=engine.finish()
    if load_json(dumps(computed))!={k:result[k] for k in computed}: raise ValueError('interval coverage mismatch')
    if head!=result['event_sha256'] or len(events)!=result['event_count']: raise ValueError('journal frontier mismatch')
    for c in ('us_ws','us_rest'):
        if tally(s for s in samples if s['channel']==c)!=result['samples'][c]: raise ValueError('sample tally mismatch')
    return dict(schema=VERSION,replay='PASS',events=len(events),samples=len(samples),
        raw_hashes_verified=sum(verify_raw(root/name) for name in ('kalshi.sqlite3','us.sqlite3')),
        us_frames_verified=sum(v['verified_frames'] for v in verified_us.values()),
        interval_coverage_recomputed=True,trading_authorized=False)
