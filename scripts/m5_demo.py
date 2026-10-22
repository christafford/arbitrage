"""HYPOTHETICAL M5 paper stress replay. No live feed, orders, positions or funds."""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from m4_demo import run as m4_demo
from predarb.paper_store import archive_ticks, compare, create_intent, report
from predarb.store import connect
from predarb.validation import dumps, load_json, utc_time


def run(output):
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    raw=Path('tests/fixtures/m5-hypothetical.json').read_bytes()
    (root/'scenarios.json').write_bytes(raw)  # Preserve original bytes before parsing.
    scenarios=load_json(raw);assert scenarios['hypothetical'] is True
    with redirect_stdout(StringIO()):m4_demo(root/'base')
    case=load_json((root/'base/inputs.json').read_bytes());now=utc_time(case['clock'])
    results=[]
    with connect(str(root/'base/research.sqlite3')) as con:
        intent=create_intent(con,1,scenarios['policy'],now=now)
        for scenario in scenarios['cases']:
            data=deepcopy(case)
            ktime=now+timedelta(milliseconds=scenario['kalshi_ms']);ptime=now+timedelta(milliseconds=scenario['us_ms'])
            delta=ktime-datetime(1970,1,1,tzinfo=timezone.utc)
            data['kalshi_ws_snapshot']['sending_ts_ms']=(delta.days*86400+delta.seconds)*1000+delta.microseconds//1000
            data['polymarket_us_rest']['marketData']['transactTime']=ptime.isoformat()
            data['polymarket_us_rest']['marketData']['offers']=[{'px':{'value':scenario['us_price'],'currency':'USD'},'qty':scenario['us_quantity']}]
            inputs={'schema':'paper-ticks/m5-v1','hypothetical':True,'scenario':scenario['name'],
                    'metadata_received_at':case['clock'],'kalshi_received_at':ktime.isoformat(),'us_received_at':ptime.isoformat(),
                    'kalshi_metadata':data['kalshi_metadata'],'polymarket_us_metadata':data['polymarket_us_metadata'],
                    'kalshi_ws_snapshot':data['kalshi_ws_snapshot'],'polymarket_us_rest':data['polymarket_us_rest'],
                    'outages':scenario['outages']}
            observed=archive_ticks(con,dumps(inputs).encode(),now=now)
            result=compare(con,intent,tick_input_id=observed,now=now+timedelta(seconds=2))
            assert result['status']=='STRESS_MODELED'
            results.append({'scenario':scenario['name'],'result':result})
        assert results[0]['result']['unhedged_contracts']==0
        assert results[1]['result']['downside_bound']==85
        assert results[2]['result']['unhedged_contracts']==160
        assert 'MAX_HEDGE_LATENCY_EXCEEDED' in results[5]['result']['flags']
        assert all(leg['filled']==0 for leg in results[6]['result']['legs'])
        summary=report(con)
    output={'hypothetical':True,'historical_replay':True,'cases':results,'report':summary,
            'actual_fills_verified':False,'multiweek_acceptance':False,'trading_authorized':False}
    (root/'results.json').write_text(dumps(output)+'\n')
    print(dumps(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    run(parser.parse_args().output)
