#!/usr/bin/env python3
"""Time-limited M5I operational supervisor. Existing CLI owns all data logic.

Run collection and semantic modes as separate local systemd services. The shared
configuration contains a fixed UTC deadline, so restarting cannot extend the run.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from predarb.backups import readonly
from predarb.runtime import writer_lock


class StopRun(Exception):
    pass


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def complete_generation(source):
    """Require completed catalogues before refreshing inference metadata."""
    with readonly(source) as con:
        result = []
        for venue in ('kalshi', 'polymarket_us'):
            row = con.execute("""SELECT id,status FROM collection_runs WHERE venue=?
                AND json_extract(scope_json,'$.filter') IS NULL ORDER BY id DESC LIMIT 1""",
                (venue,)).fetchone()
            if not row or row[1] != 'COMPLETE':
                return None
            result.append(row[0])
        return result


class Run:
    def __init__(self, config, mode):
        self.config, self.mode = config, mode
        self.root = Path(config['directory']).resolve(strict=True)
        self.source = Path(config['source']).resolve(strict=True)
        self.index = Path(config['index']).resolve(strict=True)
        self.deadline = datetime.fromisoformat(config['ends_at'])
        if self.deadline.tzinfo is None:
            raise ValueError('deadline must include timezone')
        self.deadline = self.deadline.timestamp()
        self.cli = [sys.executable, '-m', 'predarb.cli', 'discovery']
        self.checkpoint = self.root / (mode + '-checkpoint.json')
        self.saved = json.loads(self.checkpoint.read_text()) if self.checkpoint.exists() else {}

    def status(self, state, **details):
        report = dict(at=datetime.now(timezone.utc).isoformat(), mode=self.mode,
                      state=state, ends_at=self.config['ends_at'], **details)
        atomic_json(self.root / (self.mode + '-status.json'), report)
        print(json.dumps(report), flush=True)

    def save(self):
        atomic_json(self.checkpoint, self.saved)

    def guard(self):
        if time.time() >= self.deadline:
            raise StopRun('deadline reached')
        for path in (self.source, self.index, self.root):
            if shutil.disk_usage(path.parent).free < 5 * 1024**3:
                raise RuntimeError('less than 5 GiB free disk')
        size = sum(p.stat().st_size for db in (self.source, self.index)
                   for p in (db, Path(str(db) + '-wal')) if p.exists())
        if size >= 80 * 1024**3:
            raise RuntimeError('source/index plus WAL reached 80 GiB')

    def pause(self, seconds):
        end = min(time.time() + seconds, self.deadline)
        while time.time() < end:
            self.guard()
            time.sleep(min(30, max(0, end - time.time())))

    def invoke(self, action, *arguments, allowed=(0,)):
        self.guard()
        name = f'{self.mode}-{time.time_ns()}-{action}'
        output = self.root / (name + '.json')
        errors = self.root / (name + '.stderr')
        command = self.cli + [action, '--db', str(self.source), '--min-free-mb', '5120']
        if action.startswith('index-'):
            command += ['--index-db', str(self.index)]
        command += list(arguments)
        self.status('RUNNING_COMMAND', command=command, output=str(output))
        started = time.monotonic()
        with output.open('w') as stdout, errors.open('w') as stderr:
            child = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = child.wait(timeout=max(.01, min(900, self.deadline - time.time())))
            except BaseException:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGINT)
                    try:
                        child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                raise
        self.status('COMMAND_FINISHED', action=action, exit_code=code,
                    seconds=time.monotonic() - started, output=str(output), stderr=str(errors))
        if code not in allowed:
            raise RuntimeError(f'{action} exited {code}; inspect {errors}')
        if output.stat().st_size > 10 * 1024**2:
            raise RuntimeError('CLI report exceeded 10 MiB')
        return json.loads(output.read_text())

    def collection_step(self):
        due = self.saved.get('next_due', 0)
        if time.time() < due:
            self.status('WAITING_REFRESH', next_due=due)
            self.pause(min(300, due - time.time()))
            return
        done = self.saved.setdefault('completed_venues', [])
        for venue in ('kalshi', 'polymarket_us'):
            if venue in done:
                continue
            # Bound a whole traversal as well as each individual invocation.
            if self.saved.get(venue + '_pages', 0) >= 2000:
                raise RuntimeError(f'{venue} reached 2,000-page traversal ceiling')
            report = self.invoke('catalogue-walk', '--venue', venue, '--page-size', '200',
                                 '--max-pages', '20', allowed=(0, 2))
            self.saved[venue + '_pages'] = report['pages']
            if report['status'] == 'COMPLETE':
                done.append(venue)
            self.save()
        if len(done) == 2:
            self.saved = {'next_due': time.time() + 6 * 3600,
                          'completed_rounds': self.saved.get('completed_rounds', 0) + 1}
            self.save()
            self.status('CATALOGUES_COMPLETE', **self.saved)

    def semantic_step(self):
        generation = complete_generation(self.source)
        if generation is None:
            self.status('WAITING_COMPLETE_CATALOGUES')
            self.pause(60)
            return
        if generation != self.saved.get('synced_generation'):
            for _ in range(100):
                report = self.invoke('index-sync', '--budget', '10000')
                if report['scan_complete']:
                    break
            else:
                raise RuntimeError('metadata sync exceeded 100 bounded invocations')
            if complete_generation(self.source) != generation:
                return  # A refresh began during sync; retry after its completion.
            self.saved['synced_generation'] = generation
            self.save()
            self.invoke('index-coverage')
        pin = ['--expected-identity', self.config['expected_identity']] if self.config.get('expected_identity') else []
        worker = self.invoke('index-work', '--kalshi-budget', '1536', '--us-budget', '1536',
                             '--seconds', '600', '--texts-per-second', '8', *pin, allowed=(0, 2))
        retrieved = self.invoke('index-retrieve', '--query-budget', '250', '--limit', '100')
        # Retrieval already includes a full coverage report. Keep its explicit
        # assessment clock instead of scanning the catalogue a second time.
        coverage = retrieved['coverage']
        self.status('BATCH_COMPLETE', worker=worker, venues=coverage['venues'],
                    coverage_at=coverage['at'])
        # An AI outage does not stop retrieval or the independent collector.
        if worker['status'] == 'FALLBACK' or not sum(worker['completed'].values()):
            self.pause(300)

    def run(self):
        failures = 0
        try:
            with writer_lock(self.root / (self.mode + '-supervisor')):
                while True:
                    self.guard()
                    try:
                        getattr(self, self.mode + '_step')()
                        failures = 0
                    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                        failures += 1
                        self.status('RETRY' if failures < 3 else 'FAILED', reason=str(exc), failures=failures)
                        if failures >= 3:
                            return 1
                        self.pause(60 * 2**(failures - 1))
        except StopRun as exc:
            self.status('STOPPED', reason=str(exc))
            return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--mode', choices=('collection', 'semantic'), required=True)
    args = parser.parse_args()
    def stop(signum, frame):
        raise StopRun(f'signal {signum}')
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    return Run(json.loads(args.config.read_text()), args.mode).run()


if __name__ == '__main__':
    sys.exit(main())
