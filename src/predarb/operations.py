"""Local monitoring and bounded zero-money research/shadow runner. No alert delivery."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shutil import disk_usage
import subprocess
import threading
import time

from .paper_store import compare, create_intent
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
    rows = con.execute('SELECT evaluated_at FROM research_cycles WHERE session_id=? ORDER BY id DESC LIMIT 1', (session_id,)).fetchone()
    if rows is None:
        alert('NO_RESEARCH_CYCLES', 'WARN')
    else:
        age = (now - utc_time(rows[0])).total_seconds()
        if age < -5: alert('RESEARCH_CLOCK_IN_FUTURE', 'HIGH')
        if age > max(120, current['interval_seconds'] * 2): alert('RESEARCH_HEARTBEAT_STALE', 'WARN')
    approved = con.execute("SELECT COUNT(*) FROM pairs WHERE status='APPROVED'").fetchone()[0]
    if approved == 0: alert('NO_CACHED_APPROVED_PAIRS', 'WARN')
    if current['mode'] != 'LIVE_READ_ONLY': alert('HYPOTHETICAL_SESSION', 'WARN')
    failed = con.execute("SELECT COUNT(*) FROM collection_runs WHERE status IN ('FAILED','INTERRUPTED')").fetchone()[0]
    latest_failures = con.execute('''SELECT COUNT(*) FROM collection_runs r WHERE r.id IN
        (SELECT MAX(id) FROM collection_runs GROUP BY venue) AND status IN ('FAILED','INTERRUPTED')''').fetchone()[0]
    if latest_failures: alert('LATEST_COLLECTION_FAILED', 'WARN')
    if backup_dir is None or not Path(backup_dir).exists():
        alert('BACKUP_NOT_OBSERVED', 'WARN')
    else:
        files = list(Path(backup_dir).glob('*.manifest.json'))
        if not files: alert('BACKUP_NOT_OBSERVED', 'WARN')
        else:
            try:
                # This is an age monitor, not a substitute for full backup verification.
                latest = max(utc_time(text_field(object_value(load_json(p.read_bytes())), 'created_at')) for p in files)
                if (now - latest).total_seconds() > 86400 or latest > now:
                    alert('BACKUP_STALE_OR_FUTURE', 'WARN')
            except (ValueError, KeyError, OSError): alert('BACKUP_MANIFEST_UNREADABLE', 'WARN')
    metrics = {'disk_free_bytes': free, 'database_bytes': size, 'cached_approved_pairs': approved,
               'research_cycles_total': con.execute('SELECT COUNT(*) FROM research_cycles WHERE session_id=?', (session_id,)).fetchone()[0],
               'collection_failures_total': failed,
               'paper_comparisons_total': con.execute('SELECT COUNT(*) FROM paper_comparisons').fetchone()[0],
               'paper_high_scenarios_total': con.execute("SELECT COUNT(*) FROM ops_events WHERE action='PAPER_DOWNSIDE_SCENARIO'").fetchone()[0]}
    result = {'evaluated_at': now.isoformat(), 'session_id': session_id, 'ready': not any(a['severity'] == 'HIGH' for a in alerts),
              'clock': sync, 'metrics': metrics, 'alerts': alerts, 'trading_authorized': False}
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
        previous_wall, previous_mono = clock(), time.monotonic()
        completed = 0
        try:
            for _ in range(config['cycles']):
                if stop.is_set(): break
                started = time.monotonic()
                now = clock()
                jump_ms = abs((now - previous_wall).total_seconds() - (started - previous_mono)) * 1000
                if jump_ms > config['max_clock_jump_ms']:
                    event(con, 'HIGH', 'WALL_CLOCK_JUMP', {'difference_ms': str(jump_ms)}, now)
                    return 2
                previous_wall, previous_mono = now, started
                status = health(con, config['session_id'], now=now, min_free_bytes=config['min_free_bytes'],
                                max_db_bytes=config['max_db_bytes'], backup_dir=config['backup_dir'])
                print(dumps({'health': status}), flush=True)
                if not status['ready']:
                    event(con, 'HIGH', 'RUN_HEALTH_STOP', {'completed_cycles': completed}, clock())
                    return 2
                result = scan_once(con, config['session_id'], refresh=config['refresh'])
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
