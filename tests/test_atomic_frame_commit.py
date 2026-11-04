"""Atomic finalization on genuine bytes with HYPOTHETICAL storage/crash faults."""
from contextlib import closing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from predarb import persistence_profile as profile, store, ws_store
from predarb.backups import readonly
from predarb.book_store import load_book
from predarb.research import _latest
from predarb.validation import dumps, load_json

FIXTURE = Path(__file__).parent / 'fixtures/m5p-profile-live.json'
STATE_SQL = '''SELECT r.validation_status,r.source_ts,b.source_ts,b.freshness,
 b.liquidity,n.result_json FROM raw_observations r
 JOIN book_captures b ON b.observation_id=r.id
 LEFT JOIN normalized_books n ON n.observation_id=r.id WHERE r.id=?'''
FAULTS = load_json((FIXTURE.parent/'m5p-atomic-faults-hypothetical.json').read_bytes())
PENDING = ('PENDING', None, None, 'UNVERIFIED_STREAM', 'UNKNOWN', None)


class HookConnection:
    """HYPOTHETICAL fault/reader probes; real SQLite statements and commits."""
    def __init__(self, con, hook):
        self.con, self.hook = con, hook

    def execute(self, sql, *args):
        result = self.con.execute(sql, *args)
        if sql.startswith('UPDATE raw_observations'): stage = 'status'
        elif sql.startswith('UPDATE book_captures'): stage = 'capture'
        elif sql.startswith('INSERT INTO normalized_books'): stage = 'normalized'
        else: stage = None
        if stage: self.hook(stage, self.con)
        return result

    def commit(self):
        self.hook('commit_entry', self.con)
        result = self.con.commit()
        self.hook('committed', self.con)
        return result

    def __getattr__(self, name):
        return getattr(self.con, name)


class AtomicFrameCommitTests(unittest.TestCase):
    def setUp(self):
        self.case = load_json(FIXTURE.read_bytes())['case']
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_independent_readers_see_pending_until_one_complete_final_commit(self):
        dest = self.root/'visibility'
        original = ws_store.record_frame
        stages = []
        def record(con, observed, book, *, now):
            with closing(readonly(dest/'profile.sqlite3')) as reader:
                reader.execute('BEGIN')
                self.assertEqual(reader.execute(STATE_SQL, (observed,)).fetchone(), PENDING)
                def hook(stage, writer):
                    stages.append(stage)
                    # A pinned snapshot cannot observe any part of finalization.
                    self.assertEqual(reader.execute(STATE_SQL, (observed,)).fetchone(), PENDING)
                    with closing(readonly(dest/'profile.sqlite3')) as fresh:
                        row = fresh.execute(STATE_SQL, (observed,)).fetchone()
                        if stage != 'committed':
                            self.assertEqual(row, PENDING)
                            self.assertEqual(_latest(fresh, 'kalshi', book.source_id, now), observed)
                            with self.assertRaises(ValueError): load_book(fresh, observed, now=now)
                        else:
                            self.assertEqual(row[:5], ('VALID', book.source_ts, book.source_ts, 'FRESH', 'TWO_SIDED'))
                            self.assertEqual(load_json(row[5]), load_json(dumps(book.as_dict(now=now))))
                            self.assertEqual(fresh.execute('PRAGMA integrity_check').fetchone(), ('ok',))
                original(HookConnection(con, hook), observed, book, now=now)
                reader.rollback()
                self.assertEqual(reader.execute(STATE_SQL, (observed,)).fetchone()[0], 'VALID')
        with patch.object(ws_store, 'record_frame', record):
            result = profile.run_case(self.case, dest)
        self.assertEqual(result['books'], 3)
        self.assertEqual(stages, ['status','capture','normalized','commit_entry','committed']*3)

    def test_storage_failures_rollback_before_cleanup_and_never_publish(self):
        original = ws_store.record_frame
        for stage in FAULTS['storage_failure_stages']:
            with self.subTest(stage=stage):
                dest = self.root/stage
                checked = []
                def record(con, observed, book, *, now):
                    def hook(at, writer):
                        if stage == 'sqlite_commit' and at == 'normalized':
                            # Real deferred FK violation: INSERT succeeds, COMMIT fails.
                            writer.execute('PRAGMA defer_foreign_keys=ON')
                            writer.execute('UPDATE normalized_books SET metadata_observation_id=-1')
                        if at == stage: raise OSError('HYPOTHETICAL storage failure')
                        if stage == 'interrupt' and at == 'normalized': raise KeyboardInterrupt()
                    try:
                        original(HookConnection(con, hook), observed, book, now=now)
                    finally:
                        self.assertFalse(con.in_transaction)
                        self.assertEqual(con.execute(STATE_SQL, (observed,)).fetchone(), PENDING)
                        checked.append(observed)
                expected = KeyboardInterrupt if stage == 'interrupt' else ValueError
                with patch.object(ws_store, 'record_frame', record), self.assertRaises(expected):
                    profile.run_case(self.case, dest)
                self.assert_failed_archive(dest)
                self.assertEqual(len(checked), 1)

    def assert_failed_archive(self, dest, *, committed=False):
        with closing(readonly(dest/'profile.sqlite3')) as con:
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(), [])
            observed = con.execute('SELECT max(observation_id) FROM ws_frames').fetchone()[0]
            row = con.execute(STATE_SQL, (observed,)).fetchone()
            if committed:
                self.assertEqual(row[0], 'VALID');self.assertIsNotNone(row[-1])
            else:
                self.assertEqual(row, PENDING)
                self.assertEqual(con.execute('SELECT count(*) FROM normalized_books').fetchone()[0], 0)
            raw = con.execute('SELECT raw_body,body_sha256 FROM raw_observations WHERE id=?', (observed,)).fetchone()
            self.assertEqual(raw, (self.case['frames'][1]['body'].encode(), self.case['frames'][1]['sha256']))
        events = [load_json(line) for line in (dest/'events.jsonl').read_text().splitlines()]
        self.assertTrue(any(e['kind']=='pending' and e['observation_id']==observed for e in events))
        self.assertFalse(any(e['kind']=='book' for e in events))
        self.assertFalse((dest/'result.json').exists())

    def test_failure_after_durable_commit_cannot_publish_or_leave_half_a_book(self):
        original = ws_store.record_frame
        dest = self.root/'after'
        def record(con, observed, book, *, now):
            def hook(stage, writer):
                if stage == 'committed': raise OSError('HYPOTHETICAL lost commit acknowledgment')
            original(HookConnection(con, hook), observed, book, now=now)
        with patch.object(ws_store, 'record_frame', record), self.assertRaises(ValueError):
            profile.run_case(self.case, dest)
        self.assert_failed_archive(dest, committed=True)
        with closing(readonly(dest/'profile.sqlite3')) as con:
            self.assertIsNotNone(con.execute('SELECT ended_at FROM ws_connections').fetchone()[0])

    def test_process_death_preserves_raw_pending_or_whole_final_transaction(self):
        # No Python finally/close runs. COMMIT VM entry is a real SQLite progress
        # callback; this tests process death, not device/power-loss fault tolerance.
        script = '''
import os, sys
from pathlib import Path
from unittest.mock import patch
from predarb import persistence_profile as profile, ws_store
from predarb.validation import load_json
from test_atomic_frame_commit import HookConnection
case=load_json(Path(sys.argv[1]).read_bytes())['case']
original=ws_store.record_frame
stage=sys.argv[3]
def record(con, observed, book, *, now):
    def hook(at, writer):
        if at==stage: os._exit(73)
        if stage=='commit_vm' and at=='commit_entry':
            writer.set_progress_handler(lambda: os._exit(73),1)
    original(HookConnection(con,hook),observed,book,now=now)
with patch.object(ws_store,'record_frame',record): profile.run_case(case,Path(sys.argv[2]))
'''
        for fault in FAULTS['process_death_stages']:
            stage = fault['stage']
            with self.subTest(stage=stage):
                dest = self.root/stage
                env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(FIXTURE.parent.parent.resolve()),str(Path('src').resolve())]))
                run = subprocess.run([sys.executable,'-c',script,str(FIXTURE.resolve()),str(dest),stage],
                                     env=env, capture_output=True, timeout=15)
                self.assertEqual(run.returncode,73,run.stderr.decode())
                self.assert_failed_archive(dest, committed=fault['committed'])
                self.assertEqual(load_json((dest/'status.json').read_bytes())['status'], 'RUNNING')

    def test_finalization_refuses_uncommitted_raw_and_does_not_commit_caller_work(self):
        original = ws_store.record_frame
        checked = []
        def record(con, observed, book, *, now):
            con.execute("UPDATE raw_observations SET validation_error='HYPOTHETICAL_UNCOMMITTED' WHERE id=?", (observed,))
            with self.assertRaisesRegex(ValueError,'committed raw/pending'):
                original(con, observed, book, now=now)
            self.assertTrue(con.in_transaction)
            con.rollback();checked.append(observed)
            original(con, observed, book, now=now)
        with patch.object(ws_store, 'record_frame', record):
            profile.run_case(self.case,self.root/'caller')
        self.assertEqual(len(checked),3)

    def test_missing_pending_or_frame_provenance_rolls_back_status(self):
        original = ws_store.record_frame
        for table, message in [('book_captures','missing pending'),('ws_frames','missing stream')]:
            with self.subTest(table=table):
                checked = []
                def record(con, observed, book, *, now):
                    # HYPOTHETICAL corrupt context: remove one required link.
                    con.execute(f'DELETE FROM {table} WHERE observation_id=?',(observed,));con.commit()
                    with self.assertRaisesRegex(ValueError,message):
                        original(con, observed, book, now=now)
                    self.assertFalse(con.in_transaction)
                    self.assertEqual(con.execute('SELECT validation_status FROM raw_observations WHERE id=?',(observed,)).fetchone(),('PENDING',))
                    self.assertEqual(con.execute('SELECT count(*) FROM normalized_books').fetchone()[0],0)
                    checked.append(observed)
                    raise OSError('HYPOTHETICAL stop after assertion')
                with patch.object(ws_store,'record_frame',record),self.assertRaises(ValueError):
                    profile.run_case(self.case,self.root/table)
                self.assertEqual(len(checked), 1)

    def test_deferred_status_requires_explicit_transaction_default_still_commits(self):
        with store.connect(str(self.root/'status.sqlite3')) as con:
            oid=store.archive_response(con,'kalshi','HYPOTHETICAL',b'{}',200,{},'2026-11-04T00:00:00+00:00','HYPOTHETICAL')
            with self.assertRaisesRegex(ValueError,'active transaction'):
                store.validate_observation(con,oid,'VALID',None,commit=False)
            con.execute('BEGIN IMMEDIATE')
            store.validate_observation(con,oid,'VALID',None,commit=False)
            self.assertTrue(con.in_transaction);con.rollback()
            self.assertEqual(con.execute('SELECT validation_status FROM raw_observations').fetchone(),('PENDING',))
            store.validate_observation(con,oid,'REJECTED','HYPOTHETICAL')
            self.assertFalse(con.in_transaction)
            with closing(readonly(self.root/'status.sqlite3')) as reader:
                self.assertEqual(reader.execute('SELECT validation_status FROM raw_observations').fetchone(),('REJECTED',))
