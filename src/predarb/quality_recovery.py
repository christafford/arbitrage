"""M5P offline evidence accounting. Historical archives are always read-only."""
from collections import Counter
from contextlib import closing
from datetime import timedelta
from decimal import Decimal
import csv
import hashlib
from pathlib import Path

from .backups import readonly
from .continuous_research import archived_visibility, observation
from .book_store import inspect_book
from .validation import dumps, load_json, utc_time

VERSION = 'market-data-quality-recovery/m5p-v1'


def reasons(row):
    return sorted(set(row.get('quality', {}).get('rejections', row.get('rejections', []))))


def primary_reason(row):
    """Deterministic reporting attribution, NOT a claim of causal independence.

    Processing errors precede integrity/continuity, structure, age, then skew.
    Within each group use lexical order. All simultaneous reasons remain counted.
    """
    codes = reasons(row)
    if not codes:
        return 'PASS' if row.get('quality', {}).get('timestamp_depth_overlap') else 'UNKNOWN'
    def rank(code):
        if code.startswith(('ValueError:', 'OSError:', 'KeyError:')): return (0, code)
        if any(x in code for x in ('DISCONNECT', 'CONTINUITY', 'INVALID', 'CLOCK', 'LIVENESS')): return (1, code)
        if any(x in code for x in ('PARTIAL', 'EMPTY', 'MISSING', 'MARKET_', 'METADATA')): return (2, code)
        if 'SKEW' not in code: return (3, code)
        return (4, code)
    return min(codes, key=rank)


def tally(rows):
    primary, all_codes, additional, venue, combinations = (Counter() for _ in range(5))
    n = valid = masked = 0
    for row in rows:
        n += 1
        good = bool(row.get('quality', {}).get('timestamp_depth_overlap'))
        valid += good
        codes = reasons(row)
        if good and codes: raise ValueError('passing row has rejections')
        main = primary_reason(row); primary[main] += 1
        all_codes.update(codes); additional.update(c for c in codes if c != main)
        combinations[' | '.join(codes) or main] += 1
        venue.update(set(c.split(':', 1)[0] if c.startswith(('kalshi:', 'polymarket_us:'))
                         else 'collector' if c.startswith(('ValueError:', 'OSError:', 'KeyError:'))
                         else 'cross_venue' for c in codes))
        masked += row.get('status') == 'POLL_OR_BOOK_ERROR'
    return dict(samples=n, valid_samples=valid, valid_percent=str(Decimal(valid)*100/n) if n else None,
                primary=dict(primary), all_reasons=dict(all_codes), additional=dict(additional),
                venue_failed_samples=dict(venue), simultaneous_combinations=dict(combinations),
                unassessed_after_processing_error=masked)


def json_lines(path):
    with Path(path).open() as handle:
        for line in handle: yield load_json(line)


def verify_raw(path):
    count = 0
    with closing(readonly(path)) as con:
        for raw, digest in con.execute('SELECT raw_body,body_sha256 FROM raw_observations'):
            if raw is None or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('raw hash mismatch: '+str(path))
            count += 1
        for table in ('pairs', 'fee_profiles', 'research_sessions', 'paper_intents'):
            if con.execute('SELECT count(*) FROM '+table).fetchone()[0]:
                raise ValueError('unexpected economic/approval records')
    return count


def stopped_worker(root):
    status = load_json((root/'status.json').read_bytes())
    segment = root/status['segments'][-1]['directory']
    final = load_json((segment/'status.json').read_bytes())
    samples = list(json_lines(segment/'observations.jsonl'))
    consecutive = []
    for row in reversed(samples):
        if row.get('status') != 'POLL_OR_BOOK_ERROR': break
        consecutive.append({'at': row['at'], 'rejections': reasons(row)})
    rejected = []
    with closing(readonly(segment/'kalshi.sqlite3')) as con:
        for oid, at, raw, digest, error in con.execute('''SELECT r.id,r.ts_utc,r.raw_body,r.body_sha256,r.validation_error
                FROM ws_frames f JOIN raw_observations r ON r.id=f.observation_id
                WHERE r.validation_status!='VALID' ORDER BY r.id'''):
            f = load_json(raw); msg = f.get('msg', {})
            rejected.append(dict(observation_id=oid, received_at=at, sha256=digest, error=error,
                type=f.get('type'), omitted_sides=[s for s in ('yes_dollars_fp','no_dollars_fp')
                    if f.get('type') == 'orderbook_snapshot' and s not in msg]))
        metadata = []
        for oid, at, raw, digest in con.execute("SELECT id,ts_utc,raw_body,body_sha256 FROM raw_observations WHERE endpoint LIKE '%/markets/%' AND http_status=200 ORDER BY id"):
            m = load_json(raw).get('market')
            if m: metadata.append(dict(observation_id=oid, received_at=at, sha256=digest,
                                       status=m['status'], close_time=m['close_time']))
    return dict(status=status['status'], segment=str(segment), finished_at=final['finished_at'],
        terminal_consecutive_errors=list(reversed(consecutive)), rejected_frames=rejected,
        last_metadata=metadata[-1] if metadata else None,
        explanation='Omitted empty snapshot ladder rejected by launch-time parser; terminal book inspection errors reached limit.'
                    if rejected and all(x['omitted_sides'] for x in rejected) else 'REQUIRES_REVIEW')


def brooklyn(root, pair):
    folder = root/pair['id']; found = []
    for path in sorted(folder.glob('segment-*/observations.jsonl')):
        rows = list(json_lines(path))
        for i, row in enumerate(rows):
            if any(c['positive_conditional_discrepancy'] for c in row.get('capital_cases', [])):
                found.append((path.parent, rows[max(0,i-1):i+2]))
    results = []
    for segment, rows in found:
        reconstructed = []
        with closing(readonly(segment/'kalshi.sqlite3')) as kc, closing(readonly(segment/'us.sqlite3')) as uc:
            for row in rows:
                at = utc_time(row['at'])
                with archived_visibility(kc, row['archive_visibility']['kalshi']), archived_visibility(uc, row['archive_visibility']['polymarket_us']):
                    replay = observation(kc, uc, pair, at, synchronized=row['clock_synchronized'])
                if load_json(dumps(replay)) != {k:row[k] for k in replay}:
                    raise ValueError('Brooklyn sample replay mismatch')
                # Preserve full depth and exact raw pointers, not only the best price.
                reconstructed.append(replay)
            positive = next(r for r in rows if r['quality']['timestamp_depth_overlap'])
            oid = positive['sources']['kalshi']['book']['observation_id']
            neighbors = []
            for target in (oid-1, oid, oid+1):
                raw = kc.execute('SELECT id,ts_utc,raw_body,body_sha256,validation_status,schema_version FROM raw_observations WHERE id=?', (target,)).fetchone()
                neighbor = dict(zip(('observation_id','received_at','body','sha256','validation_status','schema_version'),
                                    (raw[0],raw[1],raw[2].decode(),*raw[3:])))
                state = inspect_book(kc,target,now=utc_time(raw[1]))
                neighbor['reconstructed_state'] = {k:state[k] for k in
                    ('received_at','source_ts','sequence','yes_asks','no_asks','rejections')}
                neighbors.append(neighbor)
            us_id = positive['sources']['polymarket_us']['book']['observation_id']
            uraw = uc.execute('SELECT ts_utc,raw_body,body_sha256,schema_version FROM raw_observations WHERE id=?',(us_id,)).fetchone()
            results.append(dict(segment=str(segment), sample_replays=reconstructed, adjacent_kalshi_raw=neighbors,
                us_raw=dict(observation_id=us_id,received_at=uraw[0],body=uraw[1].decode(),sha256=uraw[2],schema_version=uraw[3]),
                conclusion='One contemporaneous strict timestamp/depth sample; no demonstrated persistence, fills, net profit or settlement equivalence.'))
    return results


def analyze_history(root, output):
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    config = load_json((root/'config.json').read_bytes())
    report = dict(schema=VERSION, source=str(root), historical_archives_modified=False,
        attribution='PROCESSING, INTEGRITY/CONTINUITY, STRUCTURE/METADATA, AGE, SKEW; lexical within group. Attribution is not causal independence.',
        wall_clock_coverage='UNKNOWN: historical sample commit frontiers do not record every availability transition. Do not multiply pass count by polling interval.',
        pairs={}, raw_hashes_verified=0, original_segment_audits=Counter(), stops={})
    with (output/'rejections.csv').open('w') as f:
        writer = csv.writer(f); writer.writerow(['pair','reason','primary_count','additional_count','all_count'])
        for pair in config['pairs']:
            folder = root/pair['id']
            files = sorted(folder.glob('segment-*/observations.jsonl'))
            stats = tally(row for path in files for row in json_lines(path))
            report['pairs'][pair['id']] = stats
            for code in sorted(set(stats['all_reasons']) | set(stats['primary'])):
                writer.writerow([pair['id'],code,stats['primary'].get(code,0),stats['additional'].get(code,0),stats['all_reasons'].get(code,0)])
            state = load_json((folder/'status.json').read_bytes())
            if stats['samples'] != state['summary']['samples'] or stats['valid_samples'] != state['summary']['quality_passes']:
                raise ValueError('historical sample totals mismatch')
            if state['status'] != 'DEADLINE_REACHED': report['stops'][pair['id']] = stopped_worker(folder)
            for path in files:
                audit = load_json((path.parent/'audit.json').read_bytes())
                report['original_segment_audits'][audit['replay']] += 1
                count = sum(verify_raw(path.parent/name) for name in ('kalshi.sqlite3','us.sqlite3'))
                if count != audit['raw_hashes_verified']: raise ValueError('historical raw count mismatch')
                report['raw_hashes_verified'] += count
            print(pair['id'], stats['samples'], stats['valid_samples'], flush=True)
    report['brooklyn'] = brooklyn(root, next(p for p in config['pairs'] if p['id']=='nba-brooklyn'))
    (output/'analysis.json').write_text(dumps(report)+'\n')
    return report
