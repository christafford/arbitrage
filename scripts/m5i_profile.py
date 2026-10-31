"""Bounded read-only historical retrieval profile; no inference or venue calls."""
import argparse
from contextlib import closing
import cProfile
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import pstats
import resource
import signal
import sqlite3
import sys
import time

from predarb import semantic
from predarb.backups import readonly
from predarb.validation import utc_time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True);p.add_argument('--index-db',required=True)
    p.add_argument('--at',required=True,help='explicit historical UTC assessment clock')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--query-budget',type=int,default=50)
    p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--cprofile',action='store_true')
    p.add_argument('--implementation',type=Path,help='optional preserved local semantic.py for comparison')
    a=p.parse_args()
    if not 1<=a.query_budget<=250 or not 1<=a.seconds<=600:p.error('bounds: 1..250 queries and 1..600 seconds')
    now=utc_time(a.at);module=semantic
    if a.implementation:
        spec=importlib.util.spec_from_file_location('predarb.profile_baseline',a.implementation)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    implementation=Path(module.__file__)
    def expired(signum,frame):raise TimeoutError('retrieval profile time budget exhausted')
    old_handler=signal.signal(signal.SIGALRM,expired)
    profiler=cProfile.Profile() if a.cprofile else None
    started=time.monotonic();deadline=started+a.seconds
    signal.setitimer(signal.ITIMER_REAL,a.seconds)
    try:
        with closing(readonly(a.db)) as source,closing(readonly(a.index_db)) as index:
            if semantic.state(index,'source_path')!=source.execute('PRAGMA database_list').fetchone()[2]:
                raise ValueError('sidecar belongs to a different source')
            if semantic.state(index,'schema')!=semantic.VERSION:raise ValueError('unknown index schema')
            for con in (source,index):
                con.execute('BEGIN');con.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
            if profiler:profiler.enable()
            report=module.retrieve(source,index,now=now,query_budget=a.query_budget,limit=100,persist=False)
            if profiler:profiler.disable()
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
    elapsed=time.monotonic()-started
    profile_text=None
    if profiler:
        profiler.dump_stats(str(a.output.with_suffix('.prof')))
        stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(40)
        profile_text=stream.getvalue();a.output.with_suffix('.txt').write_text(profile_text)
    result={'mode':'READ_ONLY_HISTORICAL_RETRIEVAL_PROFILE','clock':now.isoformat(),
            'query_budget':a.query_budget,'candidate_cap':256,'persist':False,'includes_saved_reservoir':False,
            'seconds_limit':a.seconds,'elapsed_seconds':elapsed,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'python':sys.version,'sqlite':sqlite3.sqlite_version,'profiler_enabled':bool(profiler),
            'implementation_sha256':hashlib.sha256(implementation.read_bytes()).hexdigest(),
            'network_requests':0,'result':report,'profile':profile_text,
            'qualification':'Bounded hash-order query window plus full coverage scan; not full-catalogue recall. Wall time includes profiling overhead if enabled; filesystem caches are uncontrolled.'}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('result','profile','python')}))


if __name__=='__main__':main()
