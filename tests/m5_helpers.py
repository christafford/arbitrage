"""HYPOTHETICAL isolated setup and generated provider-shaped later snapshots."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from predarb import registry as r
from predarb.fee_store import import_profile
from predarb.paper_store import archive_ticks
from predarb.research import archive_replay, scan_once, start_session
from predarb.validation import dumps, load_json, utc_time
from helpers import FIXTURES
from test_registry import hypothetical_review


def seed(con, root):
    raw=(FIXTURES/'m4-hypothetical.json').read_bytes();case=load_json(raw);now=utc_time(case['clock'])
    r.load_hypothetical(con,case['registry'],now=now)
    pair=r.propose(con,'HYPOTHETICAL-K','HYPOTHETICAL-P','HYPOTHETICAL proposer',now=now)
    r.approve(con,pair,hypothetical_review(con,pair,now=now,inverse=True),human_attested=True,now=now)
    (root/'HYPOTHETICAL-fees.txt').write_text('HYPOTHETICAL source declaration only.\n')
    for profile in case['fee_profiles']:import_profile(con,dumps(profile).encode(),base=root,now=now,attested=True)
    replay=archive_replay(con,raw,now=now)
    sid=start_session(con,case['policy'],now=now,hypothetical=True)
    scan_once(con,sid,now=now,replay_id=replay)
    evaluation=con.execute('SELECT id FROM research_evaluations').fetchone()[0]
    return case,now,pair,sid,evaluation


def ticks(case, scenario):
    data=deepcopy(case);start=utc_time(case['clock'])
    ktime=start+timedelta(milliseconds=scenario['kalshi_ms']);ptime=start+timedelta(milliseconds=scenario['us_ms'])
    epoch=ktime-datetime(1970,1,1,tzinfo=timezone.utc)
    data['kalshi_ws_snapshot']['sending_ts_ms']=(epoch.days*86400+epoch.seconds)*1000+epoch.microseconds//1000
    data['polymarket_us_rest']['marketData']['transactTime']=ptime.isoformat()
    data['polymarket_us_rest']['marketData']['offers']=[{'px':{'value':scenario['us_price'],'currency':'USD'},'qty':scenario['us_quantity']}]
    return {'schema':'paper-ticks/m5-v1','hypothetical':True,'scenario':scenario['name'],
            'metadata_received_at':case['clock'],'kalshi_received_at':ktime.isoformat(),'us_received_at':ptime.isoformat(),
            'kalshi_metadata':data['kalshi_metadata'],'polymarket_us_metadata':data['polymarket_us_metadata'],
            'kalshi_ws_snapshot':data['kalshi_ws_snapshot'],'polymarket_us_rest':data['polymarket_us_rest'],
            'outages':scenario['outages']}
