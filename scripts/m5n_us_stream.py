"""Read-only authenticated US market-data probe, never economic eligibility."""
import argparse
import signal
import threading
from predarb.us_stream_probe import Credentials, capture, replay
from predarb.validation import dumps

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--credentials',help='protected existing key file outside the checkout')
    p.add_argument('--output',help='new isolated capture directory')
    p.add_argument('--slug',action='append',help='one or two exact US market slugs')
    p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--replay',help='verify an existing archive offline; no credentials needed')
    a=p.parse_args(argv)
    if a.replay:
        if a.credentials or a.output or a.slug: p.error('--replay cannot be combined with capture arguments')
        print(dumps(replay(a.replay)))
        return 0
    if not a.credentials or not a.output or not a.slug:
        p.error('capture requires --credentials, --output and --slug')
    stopped=threading.Event()
    handlers={sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        for sig in handlers: signal.signal(sig,lambda signum,frame:stopped.set())
        result=capture(a.output,Credentials.load(a.credentials),a.slug,seconds=a.seconds,stop=stopped)
        print(dumps(result))
        return 0 if result['capture_complete'] else 2
    finally:
        for sig,handler in handlers.items(): signal.signal(sig,handler)


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,ImportError):
        # Never print exception bodies from credential or transport libraries.
        print(dumps({'error':'INVALID_INPUT_OR_ARCHIVE','economic_eligibility':False}))
        raise SystemExit(1)
