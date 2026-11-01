"""Prepare bounded non-sports evidence packets; no approvals or economics."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from predarb import collector, fee_capture, kalshi, polymarket_us as us
from predarb.provider import HttpClient
from predarb.store import connect
from predarb.validation import dumps

CANDIDATES = [
 ('cpi-zero','KXCPI-26OCT-T0.0','cpic-uscpi-october-mom-2026-11-10-gt0pt0pct','KXCPI-26OCT'),
 ('cpi-two','KXCPI-26OCT-T0.2','cpic-uscpi-october-mom-2026-11-10-gt0pt2pct','KXCPI-26OCT'),
 ('cpi-five','KXCPI-26OCT-T0.5','cpic-uscpi-october-mom-2026-11-10-gt0pt5pct','KXCPI-26OCT'),
 ('gas-low','KXAAAGASMIN-26DEC31-3.20','aaagaspc-usgas-low-2026-12-31-lt3pt20','KXAAAGASMIN-26DEC31'),
 ('gas-high','KXAAAGASMAX-26DEC31-4.60','aaagaspc-usgas-high-2026-12-31-gt4pt60','KXAAAGASMAX-26DEC31')]


def prepare(directory):
    directory.mkdir(parents=True,exist_ok=False)
    results=[]
    with connect(str(directory/'research.sqlite3')) as con:
        for name,k,u,event in CANDIDATES:
            row=dict(name=name,kalshi_id=k,polymarket_us_id=u,human_review=None,status='UNVERIFIED',trading_authorized=False)
            for adapter,source,scope in [(kalshi,k,event),(us,u,u)]:
                client=HttpClient(con,adapter.VENUE,attempts=1,timeout=10,interval=1)
                try:
                    r=collector.collect(con,adapter,page_size=100,max_pages=3,scope=scope,books=0,selected=(source,),client=client)
                    row[adapter.VENUE+'_collection']=r.as_dict()
                    at=datetime.now(timezone.utc)
                    capture_id=fee_capture.capture(con,adapter.VENUE,source,'NO' if adapter is kalshi else 'YES',now=at,client=client)
                    fee_capture.export_review(con,capture_id,directory/(name+'-'+adapter.VENUE+'-fees'),now=datetime.now(timezone.utc))
                    row[adapter.VENUE+'_fee_capture_id']=capture_id
                except (ValueError,OSError) as exc:
                    row[adapter.VENUE+'_error']=str(exc)
            results.append(row)
            (directory/'manifest.json').write_text(dumps({'schema':'m5m-review-preparation/v1','candidates':results})+'\n')
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    print(dumps(prepare(a.output)))
