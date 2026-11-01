"""Bounded, read-only M5M synchronization capture in a new directory."""
import argparse
from pathlib import Path
import signal
import subprocess
import threading
from predarb import soak
from predarb.kalshi_auth import Credentials
from predarb.quote_diagnostics import Diagnostics, MeasuredClient, summarize
from predarb.validation import dumps


def clock_evidence():
    result = {'at': soak.clock().isoformat()}
    for command in (['timedatectl', 'timesync-status'], ['timedatectl', 'show', '-p', 'NTPSynchronized', '-p', 'TimeUSec']):
        try:
            r = subprocess.run(command, capture_output=True, text=True, timeout=5)
            result[' '.join(command)] = {'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
        except (OSError, subprocess.TimeoutExpired): result[' '.join(command)] = {'error': 'PROBE_UNAVAILABLE'}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--kalshi-ticker',required=True);p.add_argument('--us-slug',required=True)
    p.add_argument('--seconds',type=int,default=3600)
    p.add_argument('--credentials-file',default='~/.config/predarb/kalshi-readonly.json')
    a=p.parse_args()
    config=dict(kalshi_ticker=a.kalshi_ticker,us_slug=a.us_slug,seconds=a.seconds,poll_seconds=5,
                segment_seconds=300,backup_seconds=3600,min_free_mb=1024,max_storage_mb=4096,protocol='clocked')
    soak.validate_config(config,soak.clock())
    credentials=Credentials.load(a.credentials_file)
    a.output.mkdir(parents=True,exist_ok=False)
    d=Diagnostics(a.output/'timing.jsonl',config)
    stopped=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda signum,frame:stopped.set())
    soak.atomic_json(a.output/'clock-before.json',clock_evidence())
    try:
        result=soak.run(a.output/'capture',config,credentials,stop=stopped,capture_fn=d.capture,
                       client_factory=lambda con,venue,**kw:MeasuredClient(con,venue,emit=d.emit,**kw))
    finally:
        d.close()
        soak.atomic_json(a.output/'clock-after.json',clock_evidence())
    summary=summarize(a.output/'timing.jsonl');summary['capture_status']=result
    soak.atomic_json(a.output/'results.json',summary)
    print(dumps(summary))
    return 0 if result['status']=='COMPLETED' else 2

if __name__=='__main__':raise SystemExit(main())
