"""One new 10..900-second M5P read-only validation. Never renews a run."""
import argparse
from datetime import timedelta
import hashlib
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from predarb import kalshi, polymarket_us as us
from predarb.conditional_research import contract_fingerprint
from predarb.kalshi_auth import Credentials as KalshiCredentials
from predarb.us_stream_probe import Credentials as USCredentials
from predarb.orderbooks import market_rules
from predarb.provider import HttpClient
from predarb.quality_capture import VERSION, now, replay, validate_config, validate_window, worker
from predarb.soak import atomic_json
from predarb.store import connect
from predarb.stream_comparison import clock_evidence
from predarb.validation import load_json, utc_time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','worker','replay'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidates',type=Path)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--pair')
    parser.add_argument('--seconds',type=int,default=900)
    parser.add_argument('--kalshi-recovery-policy',choices=['reconnect','inband-snapshot'],default='reconnect')
    parser.add_argument('--kalshi-credentials',default=str(Path.home()/'.config/predarb/kalshi-readonly.json'))
    parser.add_argument('--us-credentials',default=str(Path.home()/'polymarket-us.api'))
    a=parser.parse_args();stop=threading.Event()
    for s in (signal.SIGINT,signal.SIGTERM): signal.signal(s,lambda *_:stop.set())
    if a.command in {'worker','replay'}:
        config=load_json(a.config.read_bytes());pair=next(p for p in config['pairs'] if p['id']==a.pair)
        validate_config(config)
        if a.command=='worker':
            if now()>=utc_time(config['deadline_at']): raise ValueError('expired fixed deadline')
            worker(a.output,pair,config,KalshiCredentials.load(a.kalshi_credentials),USCredentials.load(a.us_credentials),stop)
        audit=replay(a.output,pair,config);atomic_json(a.output/'audit.json',audit)
        print(audit);return
    candidates=load_json(a.candidates.read_bytes());pairs=candidates['pairs']
    validate_window(a.seconds,pairs)
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    before=clock_evidence();atomic_json(root/'clock-before.json',before)
    if not before['synchronized']: raise ValueError('synchronized local clock required')
    # Confirm exact definitions/open state immediately before the fixed window.
    with connect(str(root/'preflight.sqlite3')) as con:
        for p in pairs:
            for v,adapter in [('kalshi',kalshi),('polymarket_us',us)]:
                sid=p[v+'_id'];r=HttpClient(con,v,attempts=1,timeout=5).get(adapter.detail_url(sid),adapter.SCHEMA_VERSION,adapter.validate_detail)
                market_rules(v,sid,r.data['market'],now=now())
                if contract_fingerprint(v,r.data['market'])!=p['contract_fingerprints'][v]:
                    raise ValueError('source definition changed since selection')
    started=now();mono=time.monotonic()
    config=dict(schema=VERSION,seconds=a.seconds,started_at=started.isoformat(),
        deadline_at=(started+timedelta(seconds=a.seconds)).isoformat(),pairs=pairs,
        kalshi_recovery_policy=a.kalshi_recovery_policy,
        selection_sha256=hashlib.sha256(a.candidates.read_bytes()).hexdigest(),
        engineering_targets=dict(valid_sample_percent=50,unexplained_stops=0,audit_failures=0),
        code_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [*Path('src/predarb').glob('*.py'),Path(__file__)]})
    atomic_json(root/'config.json',config)
    children=[]
    try:
        for p in pairs:
            with (root/(p['id']+'.log')).open('w') as log:
                child=subprocess.Popen([sys.executable,__file__,'worker','--output',str(root/p['id']),
                    '--config',str(root/'config.json'),'--pair',p['id'],
                    '--kalshi-credentials',a.kalshi_credentials,'--us-credentials',a.us_credentials],stdout=log,stderr=log)
                children.append((p['id'],child))
        while now()<utc_time(config['deadline_at']) and time.monotonic()-mono<a.seconds and not stop.is_set():
            if abs((now()-started).total_seconds()-(time.monotonic()-mono))>1:stop.set();break
            if all(c.poll() is not None for _,c in children):break
            stop.wait(.25)
    finally:
        if stop.is_set():
            for _,c in children:
                if c.poll() is None:c.terminate()
        for _,c in children:
            try:c.wait(timeout=60)
            except subprocess.TimeoutExpired:c.kill();c.wait()
        atomic_json(root/'clock-after.json',clock_evidence())
        atomic_json(root/'status.json',dict(schema=VERSION,finished_at=now().isoformat(),
            deadline_at=config['deadline_at'],interrupted=stop.is_set(),
            children=[dict(pair=name,exit_code=c.returncode) for name,c in children]))
    if any(c.returncode for _,c in children):raise SystemExit(2)


if __name__=='__main__':main()
