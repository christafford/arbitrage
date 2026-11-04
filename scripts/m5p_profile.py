"""Profile archived Kalshi prefixes offline; no credentials or venue requests."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform
import time

from predarb.persistence_profile import VERSION, digest, run_case, source_case
from predarb.quality_capture import validate_config
from predarb.soak import atomic_json
from predarb.validation import load_json
from predarb.backups import file_hash


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frames',type=int,default=256,choices=range(3,1001),metavar='3..1000')
    p.add_argument('--repeats',type=int,default=3,choices=range(1,4))
    args=p.parse_args()
    config=load_json((args.source/'config.json').read_bytes());validate_config(config)
    args.output.mkdir(parents=True,exist_ok=False)
    cases=[source_case(args.source,pair,args.frames) for pair in config['pairs']]
    atomic_json(args.output/'fixtures.json',dict(schema=VERSION,cases=cases))
    plan=dict(schema=VERSION,registered_at=datetime.now(timezone.utc).isoformat(),source=str(args.source),
        frames=args.frames,repeats=args.repeats,selection='First connection, first bounded prefix for every configured pair; no substitution.',
        mode='OFFLINE_ONLY',live_capture=False,production_changes=False,fixture_sha256=digest(cases),
        schedule='Serial, alternating instrumented/plain order each repetition. No live coverage inference.',
        source_sha256={str(p):file_hash(p) for p in [Path(__file__),*sorted(Path('src/predarb').glob('*.py'))]},
        python=platform.python_version(),platform=platform.platform())
    atomic_json(args.output/'plan.json',plan)
    rows=[];deadline=time.monotonic()+600
    for repetition in range(args.repeats):
        for case in cases:
            for mode in ([True,False] if repetition%2==0 else [False,True]):
                if time.monotonic()>=deadline:raise TimeoutError('offline profile total budget exhausted')
                name=f"{case['pair']['id']}-{repetition+1}-{'instrumented' if mode else 'plain'}"
                result=run_case(case,args.output/name,instrumented=mode,timeout_seconds=min(120,deadline-time.monotonic()))
                rows.append(dict(pair=case['pair']['id'],repetition=repetition+1,directory=name,**result))
                print(name,result['status'],result['frames'],round(result['capture_wall_ns']/1e9,3),'seconds',flush=True)
    for case in cases:
        matches=[r for r in rows if r['pair']==case['pair']['id']]
        if len({r['normalized_sha256'] for r in matches})!=1:raise ValueError('profile/plain parity mismatch')
        if file_hash(case['source'])!=case['source_sha256']:raise ValueError('source archive changed')
    atomic_json(args.output/'report.json',dict(schema=VERSION,plan=plan,status='PASS',runs=rows,
        all_normalized_parity=True,source_archives_unchanged=True,network_requests=0,inference_requests=0,
        performance_improvement_claim=False,live_coverage_claim=False))


if __name__=='__main__':main()
