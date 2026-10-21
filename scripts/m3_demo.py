"""HYPOTHETICAL M3 acceptance replay. No network, credentials, approvals or orders.

Run from repository root with a fresh output directory:
  .venv/bin/python scripts/m3_demo.py --output data/my-m3-demo
"""
import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import hashlib
from pathlib import Path

from predarb.book_stream import KalshiBookStream
from predarb.orderbooks import normalize_rest, walk_depth
from predarb.validation import dumps, load_json, utc_time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True)
args=parser.parse_args()
root=Path(args.output);root.mkdir(parents=True,exist_ok=False)
source=Path('tests/fixtures/m3-hypothetical.json').read_bytes()
(root/'inputs.json').write_bytes(source)  # Archive bytes before decoding.
case=load_json(source)
assert case['hypothetical'] is True
now=utc_time(case['clock'])
stream=KalshiBookStream(case['kalshi_metadata']['ticker'],case['kalshi_metadata'],metadata_received_at=case['clock'])
trace=[]
frames=root/'stream-frames.jsonl'


def frame(seq,clock,*,delta=False):
    value=deepcopy(case['kalshi_ws_snapshot']);value.update(seq=seq)
    value['msg']['clock']=clock
    value['sending_ts_ms']+=len(trace)
    if delta:
        value['type']='orderbook_delta'
        value['msg']={key:item for key,item in value['msg'].items() if key not in {'yes_dollars_fp','no_dollars_fp'}}
        value['msg'].update(side='yes',price_dollars='.42',delta_fp='-.50')
    return value


def apply(value,*,expected):
    received=now+timedelta(milliseconds=len(trace))
    raw=dumps(value).encode()
    with frames.open('ab') as archive: archive.write(raw+b'\n')
    try:
        book=stream.apply(load_json(raw),received_at=received.isoformat(),now=received,generation=stream.generation)
        status='SYNCED'
        assert not book.issues(now=received)
        detail={'yes_asks':asdict(book)['yes_asks'],'no_asks':asdict(book)['no_asks'],
                'source_ts':book.source_ts,'timestamp_kind':book.timestamp_kind}
    except ValueError as exc:
        status='REJECTED';detail={'reason':str(exc)}
        assert stream.current is None
    assert status==expected,(status,expected,detail)
    trace.append({'seq':value['seq'],'generation':stream.generation,'status':status,
                  'input_sha256':hashlib.sha256(raw).hexdigest(),**detail})


apply(frame(10,100),expected='SYNCED')
apply(frame(11,101,delta=True),expected='SYNCED')
apply(frame(13,103,delta=True),expected='REJECTED')
apply(frame(14,104,delta=True),expected='REJECTED')
apply(frame(15,105),expected='SYNCED')
stream.disconnect();assert stream.current is None
stream.reconnect()
apply(frame(1,1,delta=True),expected='REJECTED')
apply(frame(2,2),expected='SYNCED')
kalshi_rest=normalize_rest('kalshi',case['kalshi_metadata']['ticker'],case['kalshi_rest'],case['kalshi_metadata'],
                           received_at=case['clock'],metadata_received_at=case['clock'],now=now)
us=normalize_rest('polymarket_us',case['polymarket_us_metadata']['slug'],case['polymarket_us_rest'],case['polymarket_us_metadata'],
                   received_at=case['clock'],metadata_received_at=case['clock'],now=now)
assert kalshi_rest.issues(now=now)==('UNKNOWN_SOURCE_TIME',)
assert not us.issues(now=now)
covered=walk_depth(us,'YES','3',now=now)
exhausted=walk_depth(us,'YES','5',now=now)
assert str(covered.quote_cost)=='1.45000000' or covered.quote_cost==load_json('1.45')
assert not exhausted.complete and exhausted.reason=='DEPTH_EXHAUSTED'
summary={'hypothetical':True,'historical_replay':True,'input_sha256':hashlib.sha256(source).hexdigest(),
         'kalshi_rest_rejections':kalshi_rest.issues(now=now),'us_no_mechanism':us.mechanism_no,
         'depth_coverage':asdict(covered),'depth_exhaustion':asdict(exhausted),
         'stale_rejections':us.issues(now=now+timedelta(seconds=61)),
         'stream_states':[entry['status'] for entry in trace],'stream_trace':trace,
         'source_frames':str(frames),'fees_or_profit_evaluated':False,'trading_authorized':False}
(root/'results.json').write_text(dumps(summary)+'\n')
print(dumps(summary))
