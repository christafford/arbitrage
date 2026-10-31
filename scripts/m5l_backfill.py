"""Build/inspect an isolated economic-priority backfill plan; no inference or orders."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
from shutil import disk_usage
from predarb import backfill,semantic
from predarb.backups import readonly
from predarb.validation import dumps,utc_time
from predarb.runtime import writer_lock


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True);p.add_argument('--index-db',required=True)
    p.add_argument('--scheduler-db',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--at',help='explicit historical replay only');a=p.parse_args()
    paths=[Path(x).resolve() for x in (a.db,a.index_db,a.scheduler_db)]
    if len(set(paths))!=3:raise ValueError('source, index and scheduler paths must differ')
    if disk_usage(paths[2].parent).free<1024**3:raise ValueError('scheduler disk space guard')
    now=utc_time(a.at) if a.at else datetime.now(timezone.utc)
    with writer_lock(a.scheduler_db),closing(readonly(a.db)) as source,closing(readonly(a.index_db)) as index,closing(sqlite3.connect(a.scheduler_db)) as schedule:
        schedule.execute('PRAGMA journal_mode=WAL')
        report=backfill.refresh(source,index,schedule,now=now);report['historical_replay']=bool(a.at)
        report['batches']={}
        for venue in ('kalshi','polymarket_us'):
            docs,token=backfill.select(source,index,schedule,venue,16,now=now)
            report['batches'][venue]={'tasks':[{'source_id':d['source_id'],'version_id':d['version_id'],
                'evidence':json.loads(schedule.execute('SELECT evidence_json FROM backfill_tasks WHERE venue=? AND source_id=?',(venue,d['source_id'])).fetchone()[0])} for d in docs],'token':token}
        report['executed']=False
    a.output.write_text(dumps(report)+'\n');print(dumps(report['counts']))

if __name__=='__main__':main()
