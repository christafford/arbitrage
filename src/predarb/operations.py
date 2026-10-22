"""Local monitoring and bounded zero-money research/shadow runner. No alert delivery."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shutil import disk_usage
import subprocess
import threading
import time

from .paper_store import compare, create_intent
from .backups import read_manifest
from .research import scan_once, session
from .runtime import writer_lock
from .store import connect
from .validation import dumps, field, load_json, object_value, text_field, utc_time


def clock():
    return datetime.now(timezone.utc)


def clock_sync():
    try:
        result = subprocess.run(['timedatectl', 'show', '--property=NTPSynchronized', '--value'],
                                capture_output=True, text=True, timeout=3, check=False)
        text = result.stdout.strip()
        if result.returncode == 0 and text in {'yes', 'no'}:
            return {'synchronized': text == 'yes', 'probe': 'timedatectl.NTPSynchronized', 'offset_measured': False}
        return {'synchronized': None, 'probe': 'timedatectl', 'error': 'synchronization state unavailable', 'offset_measured': False}
    except (OSError, subprocess.TimeoutExpired):
        return {'synchronized': None, 'probe': 'timedatectl', 'error': 'probe failed or timed out', 'offset_measured': False}


def event(con, severity, action, detail, now):
    con.execute('INSERT INTO ops_events(ts_utc,severity,action,detail_json) VALUES(?,?,?,?)',
                (now.isoformat(), severity, action, dumps(detail)))
    con.commit()


def backup_alerts(directory, now):
    """Observe bounded manifests and snapshot existence, without costly full hashing."""
    codes = set()
    latest = None
    if directory is not None:
        try:
            for path in Path(directory).glob('*.manifest.json'):
                try:
                    manifest = read_manifest(path)
                    snapshot = Path(str(path).removesuffix('.manifest.json'))
                    if not snapshot.is_file() or snapshot.stat().st_size == 0:
                        codes.add('BACKUP_SNAPSHOT_MISSING')
                        continue
                    stamp = utc_time(manifest['created_at'])
                    if stamp > now:
                        codes.add('BACKUP_STALE_OR_FUTURE')
                        continue
                    latest = stamp if latest is None else max(latest, stamp)
                except (ValueError, OSError):
                    codes.add('BACKUP_MANIFEST_UNREADABLE')
        except OSError:
            codes.add('BACKUP_MANIFEST_UNREADABLE')
    if latest is None:
        codes.add('BACKUP_NOT_OBSERVED')
    # Daily timer jitter and verification time must not cause a warning every day.
    elif now - latest > timedelta(hours=26):
        codes.add('BACKUP_STALE_OR_FUTURE')
    return sorted(codes)


def research_observation(con, session_id, now, interval):
    """Describe recorded coverage; never treat a heartbeat as economic evidence."""
    row = con.execute('''SELECT id,evaluated_at,summary_json FROM research_cycles
        WHERE session_id=? ORDER BY id DESC LIMIT 1''', (session_id,)).fetchone()
    result = {'cycle_id': None, 'evaluated_at': None, 'status': 'NO_CYCLES',
              'pairs': 0, 'rejected': 0, 'modeled_edges': 0, 'economics_evaluated': 0}
    if row is None:
        return result
    result.update(cycle_id=row[0], evaluated_at=row[1])
    pairs = field(load_json(row[2]), 'pairs_observed', int)
    if not 0 <= pairs <= 50:
        raise ValueError('invalid research cycle pair count')
    # Stop at the recorded count, so each current-cycle check does not scan the
    # entire growing evaluation history. Cycles/evaluations commit atomically.
    evaluations = con.execute('''SELECT status,summary_json FROM research_evaluations
        WHERE cycle_id=? ORDER BY id DESC LIMIT ?''', (row[0], pairs)).fetchall() if pairs else []
    if len(evaluations) != pairs:
        raise ValueError('incomplete research cycle evidence')
    result.update(pairs=pairs,
                  rejected=sum(status == 'REJECTED' for status, _ in evaluations),
                  modeled_edges=sum(status == 'MODELED_EDGE' for status, _ in evaluations),
                  economics_evaluated=sum(bool(object_value(load_json(body)).get('quote_sha256'))
                                          for _, body in evaluations))
    age = (now - utc_time(row[1])).total_seconds()
    result['status'] = ('FUTURE' if age < -5 else 'STALE' if age > max(120, interval * 2)
                        else 'NO_PAIRS' if not result['pairs']
                        else 'DATA_GATED' if not result['economics_evaluated']
                        else 'RECENT_ECONOMICS')
    return result


def health(con, session_id, *, now=None, min_free_bytes=209715200, max_db_bytes=10737418240, backup_dir=None, record=True):
    now = now or clock()
    for value in (min_free_bytes, max_db_bytes):
        if type(value) is not int or value <= 0:
            raise ValueError('disk limits must be positive integer bytes')
    current = session(con, session_id)
    filename = Path(con.execute('PRAGMA database_list').fetchone()[2])
    free = disk_usage(filename.parent).free
    size = sum(path.stat().st_size for path in (filename, Path(str(filename) + '-wal'), Path(str(filename) + '-shm')) if path.exists())
    sync = clock_sync()
    alerts = []
    def alert(code, severity): alerts.append({'code': code, 'severity': severity})
    if free < min_free_bytes: alert('DISK_SPACE_LOW', 'HIGH')
    if size > max_db_bytes: alert('DATABASE_SIZE_LIMIT', 'HIGH')
    if sync['synchronized'] is not True: alert('CLOCK_SYNC_UNCONFIRMED', 'HIGH')
    if con.execute('PRAGMA quick_check').fetchall() != [('ok',)]: alert('DATABASE_INTEGRITY_FAILED', 'HIGH')
    research = research_observation(con, session_id, now, current['interval_seconds'])
    research_alert = {'NO_CYCLES': ('NO_RESEARCH_CYCLES', 'WARN'),
                      'FUTURE': ('RESEARCH_CLOCK_IN_FUTURE', 'HIGH'),
                      'STALE': ('RESEARCH_HEARTBEAT_STALE', 'WARN'),
                      'NO_PAIRS': ('NO_RESEARCH_PAIRS', 'WARN'),
                      'DATA_GATED': ('NO_RECENT_ECONOMIC_OBSERVATIONS', 'WARN')}
    if research['status'] in research_alert:
        alert(*research_alert[research['status']])
    approved = con.execute("SELECT COUNT(*) FROM pairs WHERE status='APPROVED'").fetchone()[0]
    if approved == 0: alert('NO_CACHED_APPROVED_PAIRS', 'WARN')
    if current['mode'] != 'LIVE_READ_ONLY': alert('HYPOTHETICAL_SESSION', 'WARN')
    failed = con.execute("SELECT COUNT(*) FROM collection_runs WHERE status IN ('FAILED','INTERRUPTED')").fetchone()[0]
    latest_failures = con.execute('''SELECT COUNT(*) FROM collection_runs r WHERE r.id IN
        (SELECT MAX(id) FROM collection_runs GROUP BY venue) AND status IN ('FAILED','INTERRUPTED')''').fetchone()[0]
    if latest_failures: alert('LATEST_COLLECTION_FAILED', 'WARN')
    for code in backup_alerts(backup_dir, now):
        alert(code, 'WARN')
    metrics = {'disk_free_bytes': free, 'database_bytes': size, 'cached_approved_pairs': approved,
               'research_cycles_total': con.execute('SELECT COUNT(*) FROM research_cycles WHERE session_id=?', (session_id,)).fetchone()[0],
               'collection_failures_total': failed,
               'paper_comparisons_total': con.execute('SELECT COUNT(*) FROM paper_comparisons').fetchone()[0],
               'paper_high_scenarios_total': con.execute("SELECT COUNT(*) FROM ops_events WHERE action='PAPER_DOWNSIDE_SCENARIO'").fetchone()[0]}
    metrics.update({'research_latest_' + key: research[key]
                    for key in ('pairs', 'rejected', 'modeled_edges', 'economics_evaluated')})
    result = {'evaluated_at': now.isoformat(), 'session_id': session_id, 'ready': not any(a['severity'] == 'HIGH' for a in alerts),
              'clock': sync, 'metrics': metrics, 'research': research, 'alerts': alerts, 'trading_authorized': False}
    if record:
        con.execute('INSERT INTO ops_checks(ts_utc,session_id,report_json) VALUES(?,?,?)', (now.isoformat(), session_id, dumps(result)))
        for item in alerts: con.execute('INSERT INTO ops_events(ts_utc,severity,action,detail_json) VALUES(?,?,?,?)',
                                       (now.isoformat(), item['severity'], 'HEALTH_ALERT', dumps(item)))
        con.commit()
    return result


def metrics_text(report):
    rows = {'health_ready': int(report['ready']), **report['metrics']}
    return ''.join(f'predarb_{name} {value}\n' for name, value in rows.items())


def run_cycles(config, *, stop=None):
    object_value(config)
    required = {'db', 'session_id', 'cycles', 'refresh', 'shadow_policy', 'min_free_bytes', 'max_db_bytes', 'backup_dir', 'max_clock_jump_ms'}
    if set(config) != required: raise ValueError('unknown or missing runner configuration field')
    field(config, 'refresh', bool)
    text_field(config, 'db')
    if config['backup_dir'] is not None: text_field(config, 'backup_dir')
    for key in ('session_id', 'cycles', 'min_free_bytes', 'max_db_bytes', 'max_clock_jump_ms'):
        if field(config, key, int) <= 0: raise ValueError('runner limits must be positive')
    if config['max_clock_jump_ms'] > 5000: raise ValueError('clock jump threshold capped at 5000ms')
    stop = stop or threading.Event()
    with writer_lock(config['db']), connect(config['db']) as con:
        current = session(con, config['session_id'])
        if current['mode'] != 'LIVE_READ_ONLY': raise ValueError('monitor runner requires a live read-only session')
        if config['cycles'] * current['interval_seconds'] > 2678400: raise ValueError('runner invocation bounded to 31 days')
        if config['shadow_policy'] is not None:
            from .paper import policy
            policy(config['shadow_policy'])
        event(con, 'INFO', 'RUN_STARTED', {'config': config}, clock())
        if not config['refresh']:
            detail = {'session_id': config['session_id'],
                      'reason': 'This monitor will not fetch new venue observations.'}
            event(con, 'WARN', 'RUN_REFRESH_DISABLED', detail, clock())
            print(dumps({'alert': 'RUN_REFRESH_DISABLED', **detail}), flush=True)
        previous_wall, previous_mono = clock(), time.monotonic()
        def clock_jump(now, monotonic, phase, cycle_id=None):
            jump_ms = abs((now - previous_wall).total_seconds() - (monotonic - previous_mono)) * 1000
            if jump_ms <= config['max_clock_jump_ms']:
                return False
            detail = {'difference_ms': str(jump_ms), 'phase': phase, 'cycle_id': cycle_id,
                      'cycle_evidence_requires_review': cycle_id is not None}
            event(con, 'HIGH', 'WALL_CLOCK_JUMP', detail, now)
            print(dumps({'alert': 'WALL_CLOCK_JUMP', **detail}), flush=True)
            return True
        completed = 0
        try:
            for _ in range(config['cycles']):
                if stop.is_set(): break
                started = time.monotonic()
                now = clock()
                if clock_jump(now, started, 'BEFORE_SCAN'):
                    return 2
                previous_wall, previous_mono = now, started
                status = health(con, config['session_id'], now=now, min_free_bytes=config['min_free_bytes'],
                                max_db_bytes=config['max_db_bytes'], backup_dir=config['backup_dir'])
                print(dumps({'health': status}), flush=True)
                if not status['ready']:
                    event(con, 'HIGH', 'RUN_HEALTH_STOP', {'completed_cycles': completed}, clock())
                    return 2
                result = scan_once(con, config['session_id'], refresh=config['refresh'])
                if clock_jump(clock(), time.monotonic(), 'AFTER_SCAN', result['cycle_id']):
                    return 2
                if config['shadow_policy'] is not None:
                    # Compare prior intents to later observations before creating this cycle's intents.
                    pending = con.execute('''SELECT p.id FROM paper_intents p JOIN research_evaluations e ON e.id=p.evaluation_id
                        JOIN research_cycles c ON c.id=e.cycle_id WHERE c.session_id=? AND p.created_at>=? AND NOT EXISTS
                        (SELECT 1 FROM paper_comparisons o WHERE o.intent_id=p.id AND json_extract(o.result_json,'$.status')='STRESS_MODELED')
                        ORDER BY p.id LIMIT 51''', (config['session_id'], (clock()-timedelta(seconds=180)).isoformat())).fetchall()
                    if len(pending) > 50:
                        event(con, 'WARN', 'PAPER_QUEUE_SATURATED', {'processed_limit': 50, 'coverage_incomplete': True}, clock())
                        pending = pending[:50]
                    for (intent_id,) in pending: compare(con, intent_id)
                    for (evaluation_id,) in con.execute("SELECT id FROM research_evaluations WHERE cycle_id=? AND status='MODELED_EDGE'", (result['cycle_id'],)).fetchall():
                        try: create_intent(con, evaluation_id, config['shadow_policy'])
                        except ValueError as exc:
                            event(con, 'WARN', 'PAPER_INTENT_REJECTED', {'evaluation_id': evaluation_id, 'reason': str(exc)}, clock())
                    if clock_jump(clock(), time.monotonic(), 'AFTER_SHADOW', result['cycle_id']):
                        return 2
                completed += 1
                event(con, 'INFO', 'RUN_CYCLE_FINISHED', result, clock())
                print(dumps({'cycle': result}), flush=True)
                if completed < config['cycles']:
                    stop.wait(max(0, current['interval_seconds'] - (time.monotonic() - started)))
        except KeyboardInterrupt:
            con.rollback()
            event(con, 'INFO', 'RUN_SIGNAL_STOP', {'completed_cycles': completed}, clock())
            return 0
        except BaseException as exc:
            con.rollback()
            event(con, 'HIGH', 'RUN_FAILED', {'error': str(exc)[:500], 'completed_cycles': completed}, clock())
            raise
        event(con, 'INFO', 'RUN_FINISHED', {'completed_cycles': completed}, clock())
        return 0
