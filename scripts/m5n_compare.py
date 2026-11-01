"""Bounded independent US/Kalshi stream capture and offline comparison."""
import argparse
from pathlib import Path
import signal
import threading
from predarb.stream_comparison import run
from predarb.validation import dumps


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ticker',required=True)
    p.add_argument('--slug',action='append',required=True)
    p.add_argument('--seconds',type=int,default=900)
    p.add_argument('--us-credentials',default='~/polymarket-us.api')
    p.add_argument('--kalshi-credentials',default='~/.config/predarb/kalshi-readonly.json')
    a=p.parse_args();stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda signum,frame:stop.set())
    result=run(a.output,a.ticker,a.slug,seconds=a.seconds,us_credentials=a.us_credentials,
               kalshi_credentials=a.kalshi_credentials,stop=stop)
    print(dumps(result))
    return 0 if result['reason']=='DURATION_COMPLETE' else 2


if __name__=='__main__':raise SystemExit(main())
