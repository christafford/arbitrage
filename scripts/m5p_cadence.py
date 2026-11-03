"""Offline replay and update-cadence ranking of one completed M5P window."""
import argparse
from pathlib import Path
from predarb.cadence import screen
from predarb.soak import atomic_json

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('new evidence path required')
    report=screen(args.source);atomic_json(args.output,report)
    for r in report['ranked']:
        print(r['pair']['id'],r['decision'])
