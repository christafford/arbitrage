"""Historical replay of isolated dual-stream observations. No economic outputs."""
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import statistics

from .backups import readonly
from .book_store import inspect_book
from .stream_comparison import VERSION, comparison
from . import us_stream_probe
from .validation import load_json, utc_time


def distribution(values):
    return {'count':len(values),'min':min(values),'median':statistics.median(values),'max':max(values)} if values else None


def sample_us(segment, slug, sample):
    """Never carry a prior generation into a new segment or look ahead in time."""
    if segment is None: return None
    result, rows = segment
    eligible = [row for row in rows if row.get('kind') == 'book' and row['market'] == slug
                and row['receive_monotonic'] <= sample['monotonic']
                and utc_time(row['received_at']) <= utc_time(sample['at'])]
    if not eligible: return None
    row = eligible[-1]
    end = min(result['start_monotonic']+result['requested_seconds'],
              result['start_monotonic']+result['elapsed_seconds'])
    invalid = any('rejection' in item and item['receive_monotonic'] <= sample['monotonic'] for item in rows)
    return {'source_ts':row['source_ts'], 'received_at':row['received_at'],
            'rejections':row['rejections'], 'data_usable':row['timestamp_depth_diagnostic_pass'],
            'connected':sample['monotonic'] < end and not invalid,
            'frame':row['frame'],'depth_sha256':row['depth_sha256']}


def audit(root):
    root=Path(root)
    config=json.loads((root/'config.json').read_text())
    status=json.loads((root/'status.json').read_text())
    if config.get('schema') != VERSION or status.get('schema') != VERSION:
        raise ValueError('unsupported comparison archive')
    clocks={name:json.loads((root/f'clock-{name}.json').read_text()) for name in ('before','after')}
    synchronized=all(value.get('synchronized') is True for value in clocks.values())
    samples=[json.loads(line) for line in (root/'samples.jsonl').read_text().splitlines()]
    if len(samples) != status['samples'] or len(samples)>901: raise ValueError('invalid sample count')
    last=config['start_monotonic']-1
    for sample in samples:
        mono=sample['monotonic']
        if not config['start_monotonic'] <= mono < config['deadline_monotonic'] or mono <= last:
            raise ValueError('sample clock outside deadline or regressed')
        if abs((utc_time(sample['at'])-utc_time(config['started_at'])).total_seconds()-(mono-config['start_monotonic']))>1:
            raise ValueError('sample wall/monotonic clock mismatch')
        last=mono
    # Require every launched US child result; a partial archive is never silently omitted.
    segments={};us_reports=[]
    for child in status['children']:
        name=child['name']
        if name == 'kalshi':continue
        if not name.startswith('us-') or name != f"us-{int(name[3:]):03d}":
            raise ValueError('invalid segment path')
        index=int(name[3:]);folder=root/name
        if index in segments:raise ValueError('duplicate segment')
        verified=us_stream_probe.replay(folder)
        result=json.loads((folder/'results.json').read_text())
        if result['slugs'] != config['slugs']:raise ValueError('segment scope mismatch')
        rows=[json.loads(line) for line in (folder/'timing.jsonl').read_text().splitlines()]
        segments[index]=(result,rows)
        us_reports.append({'segment':index,'verified_frames':verified['verified_frames'],
            'reason':result['reason'],'started_at':result['started_at'],'finished_at':result['finished_at'],
            'last_pong_rtt_seconds':result['last_pong_rtt_seconds'],'markets':result['markets']})
    if any(s['us_segment'] is not None and s['us_segment'] not in segments for s in samples):
        raise ValueError('missing referenced segment')
    report_rows=[];raw_count=0;replay_errors=Counter();connections=[]
    with closing(readonly(root/'kalshi.sqlite3')) as con:
        for raw,sha in con.execute('SELECT raw_body,body_sha256 FROM raw_observations'):
            if raw is None or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Kalshi raw hash mismatch')
            raw_count+=1
        if con.execute('SELECT DISTINCT source_id FROM ws_connections').fetchall() != [(config['ticker'],)]:
            raise ValueError('Kalshi scope mismatch')
        connections=[dict(zip(('id','started_at','ended_at','end_reason'),r)) for r in
            con.execute('SELECT id,started_at,ended_at,end_reason FROM ws_connections ORDER BY id')]
        if any(r['ended_at'] is None for r in connections):raise ValueError('capture still has an open connection')
        books=con.execute('SELECT n.observation_id,r.ts_utc FROM normalized_books n JOIN raw_observations r ON r.id=n.observation_id ORDER BY r.id').fetchall()
        frames=con.execute('SELECT r.ts_utc,r.validation_status FROM ws_frames f JOIN raw_observations r ON r.id=f.observation_id ORDER BY r.id').fetchall()
        for sample in samples:
            at=utc_time(sample['at']);k=None
            preceding=[(oid,stamp) for oid,stamp in books if utc_time(stamp)<=at]
            if preceding:
                oid,stamp=preceding[-1]
                try:
                    saved=inspect_book(con,oid,now=at)
                    k={key:saved[key] for key in ('source_ts','received_at','rejections','data_usable')}
                    k['connected']='STREAM_DISCONNECTED' not in saved['rejections']
                    # A rejected newer frame invalidates the older book even before close finishes.
                    if any(utc_time(stamp)<utc_time(t)<=at and valid!='VALID' for t,valid in frames):
                        k['rejections']=list(k['rejections'])+['NEWER_INVALID_FRAME']
                    k['observation_id']=oid
                except (ValueError,KeyError,TypeError):
                    replay_errors['KALSHI_REPLAY_REJECTED']+=1
            u=sample_us(segments.get(sample['us_segment']),config['slugs'][0],sample)
            assessed=comparison({'kalshi':k,'polymarket_us':u},at)
            if not synchronized:
                assessed['timestamp_depth_overlap']=False
                assessed['rejections'].append('LOCAL_CLOCK_UNVERIFIED')
            report_rows.append({'at':sample['at'],'monotonic':sample['monotonic'],
                'kalshi_observation_id':k.get('observation_id') if k else None,
                'us_segment':sample['us_segment'],'us_frame':u.get('frame') if u else None,**assessed})
        counts={table:con.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
                ('pairs','fee_profiles','research_sessions','paper_intents')}
    passes=sum(row['timestamp_depth_overlap'] for row in report_rows)
    gaps=[b['monotonic']-a['monotonic'] for a,b in zip(samples,samples[1:])]
    reasons=Counter(reason for row in report_rows for reason in row['rejections'])
    us_rows=[row for _,rows in segments.values() for row in rows if row.get('kind')=='book']
    market_report={}
    for slug in config['slugs']:
        rows=[row for row in us_rows if row['market']==slug]
        market_report[slug]={'messages':len(rows),'source_age_seconds':distribution([row['source_age_seconds'] for row in rows]),
            'depth_changes':sum(row['changed_from_previous'] is True for row in rows),
            'repeated_depth':sum(row['changed_from_previous'] is False for row in rows),
            'rejections':dict(Counter(r for row in rows for r in row['rejections']))}
    return {'schema':VERSION,'capture_status':status,'config':config,'samples':len(samples),
        'expected_one_second_samples':config['seconds'],'timestamp_depth_overlap_samples':passes,
        'overlap_percent_of_observed_samples':100*passes/len(samples) if samples else None,
        'sample_gaps_seconds':distribution(gaps),'rejections':dict(reasons),
        'source_skew_seconds':distribution([r['source_skew_seconds'] for r in report_rows if r['source_skew_seconds'] is not None]),
        'receipt_skew_seconds':distribution([r['receipt_skew_seconds'] for r in report_rows if r['receipt_skew_seconds'] is not None]),
        'kalshi_raw_hashes_verified':raw_count,'kalshi_connections':connections,
        'kalshi_connection_end_reasons':dict(Counter(r['end_reason'] for r in connections)),
        'kalshi_replay_rejections':dict(replay_errors),'approval_economics_counts':counts,
        'local_clock_checks':clocks,'local_clock_synchronized_before_after':synchronized,
        'us_segments':us_reports,'us_markets':market_report,'sample_comparisons':report_rows,
        'us_sequence_continuity':'UNKNOWN','continuous_interval_coverage':'NOT_ESTABLISHED',
        'us_metadata_grid_validation':'NOT_PERFORMED_BY_STREAM_PROBE',
        'economic_eligibility':False,'trading_authorized':False}
