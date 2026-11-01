"""Read-only replay of a stopped dual-stream capture."""
import argparse
from pathlib import Path
from predarb.stream_comparison_audit import audit
from predarb.stream_comparison import write_json

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('output must be new')
    result=audit(args.directory)
    write_json(args.output,result)
    print({key:result[key] for key in ('samples','timestamp_depth_overlap_samples','kalshi_raw_hashes_verified','economic_eligibility')})
