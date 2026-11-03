"""Offline source/receipt-age and skew distributions; no freshness reinterpretation."""
import argparse
from collections import Counter
from pathlib import Path

from predarb.quality_recovery import json_lines
from predarb.quote_diagnostics import distribution
from predarb.validation import dumps,load_json,utc_time


def metrics(paths,channel=None):
    values={};counts=Counter()
    def add(key,value):
        if value is not None:values.setdefault(key,[]).append(value)
    for path in paths:
        for row in json_lines(path):
            if channel is not None and row['channel']!=channel:continue
            counts['samples']+=1
            at=utc_time(row['at'])
            q=row.get('quality',{})
            counts['quality_passes']+=q.get('timestamp_depth_overlap',False)
            for key in ('source_skew_seconds','receipt_skew_seconds'):add(key,q.get(key))
            if 'displayed_books' in row:
                clocks={b['venue']:dict(source_timestamp=b['source_ts'],local_receipt_at=b['received_at']) for b in row['displayed_books']}
            else:clocks=row.get('clocks',{})
            for venue,clocks in clocks.items():
                for field,label in [('source_timestamp','source_age_seconds'),('local_receipt_at','receipt_age_seconds')]:
                    if clocks.get(field):add(venue+':'+label,(at-utc_time(clocks[field])).total_seconds())
    return dict(counts=dict(counts),metrics={k:distribution(v) for k,v in values.items()},
                missing_clock_samples='Excluded from age distributions, retained in sample/rejection denominator.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['m5o','m5p'],required=True)
    a=p.parse_args();config=load_json((a.source/'config.json').read_bytes());out={}
    for pair in config['pairs']:
        folder=a.source/pair['id']
        if a.mode=='m5o':out[pair['id']]=metrics(sorted(folder.glob('segment-*/observations.jsonl')))
        else:out[pair['id']]={c:metrics([folder/'samples.jsonl'],c) for c in ('us_ws','us_rest')}
    a.output.write_text(dumps(dict(schema='m5p-quality-metrics/v1',source=str(a.source),mode=a.mode,pairs=out))+'\n')
