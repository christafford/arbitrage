"""Audited observed-update screening, never settlement or trading approval."""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import hashlib

from .quality_capture import replay, seconds, Engine
from .quality_recovery import json_lines
from .validation import dumps, load_json, utc_time

VERSION='market-cadence-screen/m5p-v1'


def summarize(events, start, end):
    start,end=utc_time(start),utc_time(end)
    stamps=[];counts=Counter();depth=None;previous_source=None;previous_generation=None
    for event,book in events:
        if event.get('channel')!='us_ws':continue
        at=utc_time(event['at'])
        if not start<=at<end:raise ValueError('cadence event outside fixed window')
        if event['kind'] in {'disconnect','invalid','metadata_invalid'}:
            depth=None;counts['loss_events']+=1
        if event['kind']!='book':continue
        counts['books']+=1
        if book is None:raise ValueError('missing reconstructed cadence book')
        if book.rejections:
            counts['rejected_books']+=1;depth=None
            continue
        stamps.append(at)
        if previous_source==book.source_ts:counts['repeated_source_timestamps']+=1
        previous_source=book.source_ts
        if event.get('generation')!=previous_generation:depth=None
        previous_generation=event.get('generation')
        digest=hashlib.sha256(dumps([[(x.price,x.quantity) for x in levels]
            for levels in (book.yes_asks,book.no_asks)]).encode()).hexdigest()
        if depth is not None and digest!=depth:counts['observed_depth_changes']+=1
        depth=digest
    gaps=sorted(seconds(b-a) for a,b in zip(stamps,stamps[1:]))
    boundary=[seconds(b-a) for a,b in zip([start]+stamps,stamps+[end])]
    return dict(counts=dict(counts),interarrival_seconds=dict(
        count=len(gaps),median=(gaps[(len(gaps)-1)//2]+gaps[len(gaps)//2])/2 if gaps else None,
        p95=gaps[(len(gaps)*95+99)//100-1] if gaps else None,max=max(gaps) if gaps else None),
        max_gap_including_startup_and_tail_seconds=max(boundary),
        gap_meaning='Local validated-book availability, including startup/tail; depth changes are observed, not exchange mutation timestamps.')


def decision(result, cadence, duration, halves):
    samples=result['samples']['us_ws'];total=samples['samples']
    sample_percent=Decimal(samples['valid_samples'])*100/total if total else Decimal(0)
    wall=Decimal(result['valid_local_market_state_percent']['us_ws'])
    reasons=[]
    if duration<300:reasons.append('SCREEN_SHORTER_THAN_300S')
    if result['status']!='DEADLINE_REACHED' or result['errors'] or result['early_receivers']:
        reasons.append('INCOMPLETE_OR_FAILED_WORKER')
    if sample_percent<50:reasons.append('SAMPLE_COVERAGE_LT_50_PERCENT')
    if wall<50:reasons.append('WALL_COVERAGE_LT_50_PERCENT')
    if any(v<50 for v in halves):reasons.append('HALF_WINDOW_COVERAGE_LT_50_PERCENT')
    if cadence['counts'].get('observed_depth_changes',0)<5:reasons.append('FEWER_THAN_FIVE_OBSERVED_US_DEPTH_CHANGES')
    return dict(eligible_for_further_observation=not reasons,rejections=reasons,
        sample_percent=sample_percent,wall_percent=wall,half_window_wall_percent=halves,
        verification='UNVERIFIED',trading_authorized=False)


def screen(root):
    root=Path(root);config=load_json((root/'config.json').read_bytes());rows=[]
    duration=seconds(utc_time(config['deadline_at'])-utc_time(config['started_at']))
    midpoint=utc_time(config['started_at'])+(utc_time(config['deadline_at'])-utc_time(config['started_at']))/2
    for pair in config['pairs']:
        events=[]
        audit=replay(root/pair['id'],pair,config,event_observer=lambda e,b:events.append((e,b)))
        result=load_json((root/pair['id']/'result.json').read_bytes())
        cadence=summarize(events,config['started_at'],config['deadline_at'])
        engine=Engine(pair,config['started_at'],config['deadline_at']);first=None
        for event,book in events:
            if first is None and utc_time(event['at'])>=midpoint:
                engine.advance(midpoint.isoformat());first=engine.coverage['us_ws']
            engine.event(event,book)
        if first is None:engine.advance(midpoint.isoformat());first=engine.coverage['us_ws']
        engine.finish();halves=[first*200/duration,(engine.coverage['us_ws']-first)*200/duration]
        rows.append(dict(pair=pair,cadence=cadence,audit=audit,
            decision=decision(result,cadence,duration,halves),
            kalshi_recovery=result['receiver_results']['kalshi'],
            simultaneous_rejection_seconds=result['simultaneous_rejection_seconds']['us_ws']))
    rows.sort(key=lambda r:(-r['decision']['wall_percent'],-r['decision']['sample_percent'],r['pair']['id']))
    return dict(schema=VERSION,source=str(root),started_at=config['started_at'],deadline_at=config['deadline_at'],
        scope='Purposive supplied candidates only; no representative venue-wide claim or future cadence guarantee.',
        ranked=rows,selected_pairs=[r['pair'] for r in rows if r['decision']['eligible_for_further_observation']],
        selection_is_not_approval=True,trading_authorized=False)
