"""Read-only audit of a completed M5M capture; no quotes are evaluated economically."""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
from predarb.backups import readonly
from predarb.book_store import inspect_book
from predarb.quote_diagnostics import VERSION, compare, distribution, summarize
from predarb.validation import dumps, load_json, utc_time


def analyze(root):
    status=load_json((root/'capture/status.json').read_bytes())
    if status['status']!='COMPLETED' or status['stop_reason']!='DURATION_COMPLETE':
        raise ValueError('capture has not completed its fixed duration')
    report=summarize(root/'timing.jsonl')
    records=[load_json(line) for line in (root/'timing.jsonl').read_text().splitlines()]
    comparisons=[x for x in records if x['kind']=='comparison']
    requests=[x for x in records if x['kind']=='http_request']
    receives=[x for x in records if x['kind']=='ws_receive']
    observed_books={x['observation_id']:x for x in records if x['kind']=='book_observation'}
    change_ages={v:[] for v in ('kalshi','polymarket_us')};unknown_change_times=Counter()
    transitions=Counter();previous_us=None
    for r in records:
        if r['kind']=='book_observation' and r['venue']=='polymarket_us':
            if previous_us:
                same_depth=r['changes']['depth_sha256']==previous_us['changes']['depth_sha256']
                same_source=r['source_ts']==previous_us['source_ts']
                transitions[('SAME_DEPTH' if same_depth else 'CHANGED_DEPTH')+':'+('SAME_SOURCE_TIME' if same_source else 'CHANGED_SOURCE_TIME')]+=1
                if r['source_ts'] and previous_us['source_ts'] and utc_time(r['source_ts'])<utc_time(previous_us['source_ts']):transitions['SOURCE_TIME_REGRESSION']+=1
            previous_us=r
    for r in comparisons:
        for venue,book in r['books'].items():
            observed=observed_books.get(book['observation_id'],{})
            last_change=observed.get('changes',{}).get('last_observed_change_monotonic')
            if last_change is None:unknown_change_times[venue]+=1
            else:change_ages[venue].append(r['sample_monotonic']-last_change)
    cache=Counter();ages=[];received_ids=set();timing_errors=[]
    for x in requests:
        if x['venue']=='polymarket_us' and x['url'].endswith('/book'):
            cache[x.get('cache_control') or 'MISSING']+=1
            if x.get('http_age') is not None:
                try:
                    age=int(x['http_age'])
                    if age<0:raise ValueError('negative cache age')
                    ages.append(age)
                except (ValueError,TypeError):cache['INVALID_AGE']+=1
        if x.get('observation_id') is not None:received_ids.add(x['observation_id'])
        if x.get('receive_monotonic') is not None:
            if not x['call_monotonic']<=x['request_monotonic']<=x['headers_monotonic']<=x['receive_monotonic']<=x['call_finished_monotonic']:
                timing_errors.append(x['observation_id'])
    received_ids.update(x['observation_id'] for x in receives)
    raw_status=Counter();schemas=Counter();connections=[];seq_errors=[];replay_errors=[]
    with closing(readonly(str(root/'capture/capture.sqlite3'))) as con:
        for row in con.execute('SELECT id,raw_body,body_sha256,validation_status,schema_version FROM raw_observations'):
            if hashlib.sha256(row[1]).hexdigest()!=row[2]:raise ValueError('raw source hash mismatch')
            if row[0] not in received_ids:timing_errors.append(row[0])
            raw_status[row[3]]+=1;schemas[row[4]]+=1
        for x in requests:
            if x.get('observation_id') is None:continue
            row=con.execute('SELECT body_sha256 FROM raw_observations WHERE id=?',(x['observation_id'],)).fetchone()
            if not row or row[0]!=x['body_sha256']:raise ValueError('request/raw provenance mismatch')
        for cid,start,end,reason in con.execute('SELECT id,started_at,ended_at,end_reason FROM ws_connections ORDER BY id'):
            frames=[];last_seq=None;last_clock=None
            for oid,body,validation in con.execute('SELECT r.id,r.raw_body,r.validation_status FROM ws_frames f JOIN raw_observations r ON r.id=f.observation_id WHERE f.connection_id=? ORDER BY r.id',(cid,)):
                frame=load_json(body)
                if frame['type']=='subscribed':continue
                if validation!='VALID':continue
                seq=frame.get('seq');clock=frame.get('msg',{}).get('clock')
                if type(seq) is not int or type(clock) is not int or (last_seq is not None and seq!=last_seq+1) or (last_clock is not None and clock<last_clock):seq_errors.append(oid)
                last_seq,last_clock=seq,clock;frames.append(oid)
            connections.append({'connection_id':cid,'started_at':start,'ended_at':end,'end_reason':reason,
                                'duration_seconds':(utc_time(end)-utc_time(start)).total_seconds() if end else None,
                                'validated_book_frames':len(frames)})
        # Independently reconstruct a systematic sample using original raw bytes,
        # recorded assessment clocks and stream generation/end boundaries.
        step=max(1,len(comparisons)//100)
        sampled=comparisons[::step]
        for x in sampled:
            at=utc_time(x['at']);books={}
            for venue,saved in x['books'].items():
                try:
                    book=inspect_book(con,saved['observation_id'],now=at)
                    books[venue]={k:book[k] for k in ('observation_id','data_usable','rejections','source_ts','received_at')}
                except (ValueError,KeyError,TypeError):
                    books[venue]={'observation_id':saved['observation_id'],'data_usable':False,'rejections':['MISSING_OR_INVALID_BOOK'],'source_ts':None,'received_at':None}
                # Latest collection failure is an additional coordinator barrier;
                # retain its recorded state rather than infer historical run state.
                if 'LATEST_COLLECTION_FAILED' in saved['rejections']:
                    books[venue]['rejections']=list(books[venue]['rejections'])+['LATEST_COLLECTION_FAILED'];books[venue]['data_usable']=False
            actual=compare(books,at)
            if actual['strict_rejections']!=x['strict_rejections'] or actual['strict_observation_valid']!=x['strict_observation_valid']:
                replay_errors.append({'at':x['at'],'saved':x['strict_rejections'],'replayed':actual['strict_rejections']})
        counts={table:con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('pairs','fee_profiles','research_sessions','paper_intents')}
    gaps=[(utc_time(b['started_at'])-utc_time(a['ended_at'])).total_seconds() for a,b in zip(connections,connections[1:]) if a['ended_at']]
    # Queuing evidence: message send-to-application receipt can include source
    # processing, clock error and network; correlate with synchronous HTTP windows.
    overlap=[];outside=[];event_to_send=[];event_to_receipt=[];sample_gaps=[];wall_mono_offsets=[]
    for a,b in zip(comparisons,comparisons[1:]):sample_gaps.append(b['sample_monotonic']-a['sample_monotonic'])
    if comparisons:
        base=comparisons[0]
        for r in comparisons:
            wall_mono_offsets.append((utc_time(r['at'])-utc_time(base['at'])).total_seconds()-float(r['sample_monotonic']-base['sample_monotonic']))
    for r in records:
        if r['kind']!='book_observation' or r['venue']!='kalshi' or not r['source_ts']:continue
        lag=(utc_time(r['received_at'])-utc_time(r['source_ts'])).total_seconds()
        event_ms=r.get('exchange_event_ts_ms')
        if type(event_ms) is int:
            from datetime import datetime,timezone
            event_time=datetime.fromtimestamp(event_ms//1000,timezone.utc).replace(microsecond=(event_ms%1000)*1000)
            event_to_send.append((utc_time(r['source_ts'])-event_time).total_seconds())
            event_to_receipt.append((utc_time(r['received_at'])-event_time).total_seconds())
        near_http=any(x.get('call_finished_monotonic') is not None and 0<=r['receive_monotonic']-x['call_finished_monotonic']<=.5 and x['venue']=='polymarket_us' for x in requests)
        (overlap if near_http else outside).append(lag)
    report.update(capture_status=status,raw_hashes_verified=sum(raw_status.values()),raw_validation_status=dict(raw_status),
                  schemas=dict(schemas),timing_association_errors=timing_errors,sequence_or_clock_errors=seq_errors,
                  connections=connections,connection_end_reasons=dict(Counter(x['end_reason'] for x in connections)),
                  connection_duration_seconds=distribution([x['duration_seconds'] for x in connections]),
                  between_connection_gap_seconds=distribution(gaps),
                  us_book_cache_control=dict(cache),us_http_age_seconds=distribution(ages),
                  source_lag_after_us_http_seconds=distribution(overlap),source_lag_other_seconds=distribution(outside),
                  kalshi_event_to_send_seconds=distribution(event_to_send),kalshi_event_to_receipt_seconds=distribution(event_to_receipt),
                  diagnostic_sample_gap_seconds=distribution(sample_gaps),wall_minus_monotonic_elapsed_seconds=distribution(wall_mono_offsets),
                  since_last_observed_depth_change_at_samples_seconds={v:distribution(x) for v,x in change_ages.items()},
                  unknown_preceding_depth_change_samples=dict(unknown_change_times),us_depth_source_transitions=dict(transitions),
                  replay_sample_count=len(sampled),replay_errors=replay_errors,approval_and_economics_row_counts=counts,
                  clock_before=load_json((root/'clock-before.json').read_bytes()),clock_after=load_json((root/'clock-after.json').read_bytes()),
                  capture_code_hashes=load_json((root/'code/manifest.json').read_bytes()) if (root/'code/manifest.json').exists() else None,
                  artifacts={str(root/p):hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ('timing.jsonl','capture/config.json','capture/status.json','clock-before.json','clock-after.json')})
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=analyze(a.directory)
    with a.output.open('x') as f:f.write(dumps(result)+'\n')
    print(dumps({'status':result['capture_status']['status'],'counts':result['counts'],'replay_errors':len(result['replay_errors'])}))
