"""Create a new verified backup. No automatic deletion, restore or service changes."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from predarb.backups import backup
from predarb.validation import dumps

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--db',required=True)
parser.add_argument('--directory',required=True)
args=parser.parse_args()
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
destination=Path(args.directory)/('research-'+stamp+'.sqlite3')
print(dumps(backup(args.db,destination)))
