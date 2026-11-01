"""Isolated bounded two-process stream observation; never economic eligibility."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from . import kalshi, polymarket_us as us, us_stream_probe
from .backups import readonly
from .book_store import inspect_book
from .provider import HttpClient
from .store import connect
from .validation import identifier, utc_time

VERSION = 'dual-stream-diagnostic/m5n-v1'
SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/m5n_us_stream.py'


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def clock_evidence():
    result = {'checked_at': datetime.now(timezone.utc).isoformat()}
    for command in (['timedatectl', 'show', '-p', 'NTPSynchronized'],
                    ['timedatectl', 'timesync-status']):
        process = subprocess.run(command, capture_output=True, text=True, timeout=5)
        result[' '.join(command)] = {'exit_code': process.returncode, 'output': process.stdout}
    result['synchronized'] = result['timedatectl show -p NTPSynchronized'] == {
        'exit_code': 0, 'output': 'NTPSynchronized=yes\n'}
    return result


def preflight(root, ticker, slugs):
    """Raw metadata is archived before open-state/schema checks; no approvals."""
    metadata = {}
    with connect(str(root/'metadata.sqlite3')) as con:
        for venue, adapter, ids in (('kalshi', kalshi, [ticker]), ('polymarket_us', us, slugs)):
            client = HttpClient(con, venue, interval=1, timeout=10, attempts=1)
            for source in ids:
                observed = client.get(adapter.detail_url(source), adapter.SCHEMA_VERSION, adapter.validate_detail)
                market = observed.data['market']
                if market[adapter.ID_FIELD] != source:
                    raise ValueError('metadata identity mismatch')
                if venue == 'kalshi':
                    opened = market['status'] == 'active'
                else:
                    opened = market['active'] and not market['closed'] and market['status'] == 'MARKET_STATUS_OPEN'
                if not opened: raise ValueError('selected market is not open')
                metadata[source] = {'venue': venue, 'observation_id': observed.id,
                                    'received_at': observed.received_at}
    write_json(root/'metadata.json', metadata)


def run(root, ticker, slugs, *, seconds=900, us_credentials, kalshi_credentials,
        stop, prepare=preflight, probe_clock=clock_evidence, launch=subprocess.Popen,
        monotonic=time.monotonic, wall=lambda: datetime.now(timezone.utc), sleep=time.sleep):
    """Children receive independently. The supervisor only samples clocks/status."""
    if type(seconds) is not int or not 1 <= seconds <= 900:
        raise ValueError('comparison duration must be 1..900 seconds')
    identifier(ticker); us_stream_probe.subscription(slugs)
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    before = probe_clock(); write_json(root/'clock-before.json', before)
    if not before['synchronized']: raise ValueError('local clock synchronization is required')
    prepare(root, ticker, slugs)
    start = monotonic(); started = wall(); deadline = start + seconds
    config = {'schema': VERSION, 'ticker': ticker, 'slugs': slugs, 'seconds': seconds,
              'started_at': started.isoformat(), 'deadline_at': (started+timedelta(seconds=seconds)).isoformat(),
              'start_monotonic': start, 'deadline_monotonic': deadline,
              'us_segment_seconds': 300, 'max_us_connections': 20, 'max_kalshi_connections': 120}
    config['code_sha256'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (Path(__file__), SCRIPT, Path(us_stream_probe.__file__))}
    write_json(root/'config.json', config)
    children = []; us_process = None; us_number = 0; next_us = start; reason = 'DURATION_COMPLETE'
    def spawn(name, argv):
        output = (root/(name+'.stdout')).open('w')
        error = (root/(name+'.stderr')).open('w')
        try:
            process = launch(argv, stdout=output, stderr=error)
        finally:
            output.close(); error.close()
        children.append((name, process))
        return process
    kalshi_process = None; sample_count = 0
    try:
        kalshi_process = spawn('kalshi', [sys.executable, '-m', 'predarb.cli', 'stream-kalshi', ticker,
            '--credentials-file', str(kalshi_credentials), '--db', str(root/'kalshi.sqlite3'),
            '--seconds', str(seconds), '--max-connections', '120', '--max-messages', '100000'])
        with (root/'samples.jsonl').open('w') as samples:
            while monotonic() < deadline:
                now = monotonic(); at = wall()
                if stop.is_set(): reason = 'INTERRUPTED'; break
                if abs((at-started).total_seconds()-(now-start)) > 1: reason = 'WALL_CLOCK_JUMP'; break
                if shutil.disk_usage(root).free < 1024**3: reason = 'LOW_DISK'; break
                if sample_count % 10 == 0 and sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > 512*1024**2:
                    reason = 'STORAGE_LIMIT'; break
                if kalshi_process.poll() is not None:
                    reason = 'KALSHI_ENDED_EARLY'; break
                if us_process is not None and us_process.poll() is not None:
                    segment = root/f'us-{us_number:03d}'/'results.json'
                    if not segment.exists(): reason = 'US_MISSING_RESULT'; break
                    result = json.loads(segment.read_text())
                    if result['reason'] != 'BUDGET_COMPLETE':
                        if result['reason'] != 'CAPTURE_ERROR' or result.get('http_status') is not None:
                            reason = 'US_REJECTED_CAPTURE'; break
                        next_us = now + 2
                    us_process = None
                if us_process is None and now >= next_us:
                    if us_number >= 20: reason = 'US_CONNECTION_LIMIT'; break
                    # Never give a new child a deadline beyond the original budget.
                    duration = min(300, int(deadline-now))
                    if duration >= 1:
                        us_number += 1
                        argv = [sys.executable, str(SCRIPT), '--credentials', str(us_credentials),
                                '--output', str(root/f'us-{us_number:03d}'), '--seconds', str(duration)]
                        for slug in slugs: argv += ['--slug', slug]
                        us_process = spawn(f'us-{us_number:03d}', argv)
                samples.write(json.dumps({'at': at.isoformat(), 'monotonic': now,
                    'us_segment': us_number if us_process is not None else None,
                    'kalshi_running': kalshi_process.poll() is None})+'\n')
                samples.flush(); sample_count += 1
                sleep(min(1, max(0, deadline-monotonic())))
    except Exception:
        reason = 'SUPERVISOR_ERROR'
        raise
    finally:
        for name, child in children:
            if child.poll() is None: child.terminate()
        for name, child in children:
            try: child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5); reason = 'FORCED_CHILD_STOP'
        result = {'schema': VERSION, 'reason': reason, 'samples': sample_count,
                  'finished_at': wall().isoformat(), 'elapsed_seconds': monotonic()-start,
                  'children': [{'name': name, 'exit_code': child.returncode} for name, child in children],
                  'economic_eligibility': False}
        write_json(root/'status.json', result)
        write_json(root/'clock-after.json', probe_clock())
    return result


def comparison(books, at):
    """Strictly two-second diagnostic ages/skews, separately UNKNOWN continuity."""
    rejections = []
    for venue in ('kalshi','polymarket_us'):
        book = books.get(venue)
        if book is None:
            rejections.append(venue+':MISSING_BOOK'); continue
        rejections.extend(venue+':'+reason for reason in book['rejections'])
        for field, label in (('source_ts','SOURCE'), ('received_at','RECEIPT')):
            age = (at-utc_time(book[field])).total_seconds() if book.get(field) else None
            if age is None or not 0 <= age <= 2: rejections.append(venue+':'+label+'_NOT_WITHIN_2S')
        if not book['connected']: rejections.append(venue+':DISCONNECTED')
        if not book['data_usable'] and not book['rejections']: rejections.append(venue+':UNUSABLE_BOOK')
    source_skew = receipt_skew = None
    if all(books.get(v) for v in ('kalshi','polymarket_us')):
        k, u = books['kalshi'], books['polymarket_us']
        if k.get('source_ts') and u.get('source_ts'):
            source_skew = abs((utc_time(k['source_ts'])-utc_time(u['source_ts'])).total_seconds())
        receipt_skew = abs((utc_time(k['received_at'])-utc_time(u['received_at'])).total_seconds())
    for value, label in ((source_skew,'SOURCE_SKEW'),(receipt_skew,'RECEIPT_SKEW')):
        if value is None: rejections.append(label+'_UNKNOWN')
        elif value > 2: rejections.append(label+'_GT_2S')
    return {'timestamp_depth_overlap': not rejections, 'rejections': sorted(set(rejections)),
            'source_skew_seconds': source_skew, 'receipt_skew_seconds': receipt_skew,
            'us_continuity': 'UNKNOWN', 'economic_eligibility': False}
