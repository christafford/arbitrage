"""Bounded M5O read-only observation and deterministic offline segment replay."""
import argparse
from pathlib import Path
import signal
import threading

from predarb import continuous_research as run
from predarb.validation import dumps, load_json


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('run'); a.add_argument('--candidates',type=Path,required=True)
    a.add_argument('--output',type=Path,required=True); a.add_argument('--seconds',type=int,default=86400)
    a.add_argument('--report-path',type=Path,help='write the evolving and final Markdown results here')
    a.add_argument('--credentials',default=str(Path.home()/'.config/predarb/kalshi-readonly.json'))
    a=sub.add_parser('worker'); a.add_argument('--config',type=Path,required=True)
    a.add_argument('--pair',required=True); a.add_argument('--credentials',required=True)
    a=sub.add_parser('replay'); a.add_argument('--config',type=Path,required=True)
    a.add_argument('--pair',required=True); a.add_argument('--segment',type=Path,required=True)
    a=sub.add_parser('report'); a.add_argument('directory',type=Path)
    args=p.parse_args(); stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,lambda *_:stop.set())
    if args.command=='run':
        result=run.supervise(args.output,load_json(args.candidates.read_bytes()),args.credentials,seconds=args.seconds,stop=stop,report_path=args.report_path)
        print(dumps(result)); return 0 if result['status']=='DEADLINE_REACHED' else 2
    if args.command in {'worker','replay'}:
        config=load_json(args.config.read_bytes()); run.validate_config(config)
        if args.command=='worker':
            run.worker(args.config.parent/args.pair,config,args.pair,args.credentials,stop); return 0
        pair=next(x for x in config['pairs'] if x['id']==args.pair)
        print(dumps(run.replay_segment(args.segment,pair))); return 0
    root=args.directory
    print(dumps(run.render(root,load_json((root/'config.json').read_bytes()),load_json((root/'status.json').read_bytes()))))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
