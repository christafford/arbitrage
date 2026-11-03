"""Read-only forensic reconstruction of the immutable M5O run."""
import argparse
from predarb.quality_recovery import analyze_history

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', default='data/m5o/run-20261101')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    analyze_history(a.source, a.output)
