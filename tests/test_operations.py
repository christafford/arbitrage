"""M5 local operations tests; probes and faults are explicitly hypothetical."""
from contextlib import redirect_stdout, closing
from datetime import datetime, timedelta, timezone
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from predarb.backups import backup, fingerprint, readonly, restore, verify
from predarb import cli
from predarb.operations import clock_sync, health, metrics_text, run_cycles
from predarb.research import start_session
from predarb.runtime import writer_lock
from predarb.store import connect
from predarb.validation import dumps, load_json
from helpers import drop_m5_tables

SYNC={'synchronized':True,'probe':'HYPOTHETICAL_TEST','offset_measured':False}
POLICY={'max_contracts':'100','kalshi_budget':'0','polymarket_us_budget':'0','reserve_per_leg':'.005','min_profit':'.01'}


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=str(self.root/'research.sqlite3')
        self.con=connect(self.path);self.addCleanup(self.con.close)
        self.now=datetime.now(timezone.utc)
        self.session=start_session(self.con,POLICY,now=self.now)
        self.config={'db':self.path,'session_id':self.session,'cycles':1,'refresh':False,'shadow_policy':None,
                     'min_free_bytes':1,'max_db_bytes':100000000,'backup_dir':None,'max_clock_jump_ms':1000}

    def test_health_metrics_and_persisted_alerts_with_synced_probe(self):
        with patch('predarb.operations.clock_sync',return_value=SYNC):
            result=health(self.con,self.session,now=self.now)
        self.assertTrue(result['ready'])
        self.assertIn('NO_CACHED_APPROVED_PAIRS',[row['code'] for row in result['alerts']])
        self.assertIn('predarb_health_ready 1',metrics_text(result))
        self.assertGreater(result['metrics']['disk_free_bytes'],0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ops_checks').fetchone()[0],1)

    def test_unsynced_unknown_disk_and_size_stop_readiness(self):
        for sync in (False,None):
            with patch('predarb.operations.clock_sync',return_value=dict(SYNC,synchronized=sync)):
                self.assertFalse(health(self.con,self.session,now=self.now)['ready'])
        with patch('predarb.operations.clock_sync',return_value=SYNC),patch('predarb.operations.disk_usage') as disk:
            disk.return_value.free=0
            report=health(self.con,self.session,now=self.now,max_db_bytes=1)
            self.assertFalse(report['ready'])
            self.assertTrue({'DISK_SPACE_LOW','DATABASE_SIZE_LIMIT'} <= {a['code'] for a in report['alerts']})

    def test_clock_probe_failure_timeout_and_no_output_are_unknown(self):
        for error in (OSError('HYPOTHETICAL unavailable'),subprocess.TimeoutExpired('timedatectl',3)):
            with patch('predarb.operations.subprocess.run',side_effect=error):self.assertIsNone(clock_sync()['synchronized'])
        with patch('predarb.operations.subprocess.run') as run:
            run.return_value.returncode=0;run.return_value.stdout='no\n'
            self.assertFalse(clock_sync()['synchronized'])
            run.return_value.stdout='garbage'
            self.assertIsNone(clock_sync()['synchronized'])

    def test_runner_one_cycle_and_sigterm_equivalent_interrupt_are_audited(self):
        with patch('predarb.operations.clock_sync',return_value=SYNC),redirect_stdout(StringIO()):
            self.assertEqual(run_cycles(self.config),0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM research_cycles').fetchone()[0],1)
        with patch('predarb.operations.clock_sync',return_value=SYNC),patch('predarb.operations.scan_once',side_effect=KeyboardInterrupt),redirect_stdout(StringIO()):
            self.assertEqual(run_cycles(self.config),0)
        actions=[row[0] for row in self.con.execute('SELECT action FROM ops_events')]
        self.assertIn('RUN_SIGNAL_STOP',actions)

    def test_shadow_enabled_without_gated_edges_never_invents_intents(self):
        config=dict(self.config,shadow_policy={'max_hedge_latency_ms':1000,'cancel_after_ms':1000,
                    'cancel_ack_delay_ms':250,'participation':'1','max_price_drift':'.02'})
        with patch('predarb.operations.clock_sync',return_value=SYNC),redirect_stdout(StringIO()):
            self.assertEqual(run_cycles(config),0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM paper_intents').fetchone()[0],0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM paper_comparisons').fetchone()[0],0)

    def test_runner_stops_before_scan_on_health_failure_and_clock_step(self):
        with patch('predarb.operations.clock_sync',return_value=dict(SYNC,synchronized=False)),patch('predarb.operations.scan_once',side_effect=AssertionError('must not scan')),redirect_stdout(StringIO()):
            self.assertEqual(run_cycles(self.config),2)
        with patch('predarb.operations.clock',side_effect=[self.now,self.now,self.now+timedelta(seconds=10)]),patch('predarb.operations.time.monotonic',return_value=0):
            self.assertEqual(run_cycles(self.config),2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ops_events WHERE action='WALL_CLOCK_JUMP'").fetchone()[0],1)

    def test_runner_rejects_unbounded_or_unknown_configuration(self):
        for config in (dict(self.config,cycles=2678401),dict(self.config,refresh='yes'),dict(self.config,unknown=True),dict(self.config,max_clock_jump_ms=6000)):
            with self.assertRaises(ValueError):run_cycles(config)

    def test_nonobject_runner_input_and_bad_path_types_fail_clearly(self):
        for config in (None,[],dict(self.config,db=False),dict(self.config,backup_dir=[])):
            with self.assertRaises(ValueError):run_cycles(config)

    def test_heartbeat_and_backup_age_warnings_are_not_claimed_verified_backup(self):
        destination=self.root/'backups';destination.mkdir()
        (destination/'old.manifest.json').write_text(dumps({'created_at':(self.now-timedelta(days=2)).isoformat()}))
        with patch('predarb.operations.clock_sync',return_value=SYNC):
            result=health(self.con,self.session,now=self.now,backup_dir=destination)
        self.assertIn('BACKUP_STALE_OR_FUTURE',[row['code'] for row in result['alerts']])
        (destination/'bad.manifest.json').write_text('malformed HYPOTHETICAL input')
        with patch('predarb.operations.clock_sync',return_value=SYNC):
            result=health(self.con,self.session,now=self.now,backup_dir=destination)
        self.assertIn('BACKUP_MANIFEST_UNREADABLE',[row['code'] for row in result['alerts']])

    def test_schema_four_migration_preserves_session_and_adds_no_fake_observations(self):
        drop_m5_tables(self.con);self.con.execute('PRAGMA user_version=4');self.con.commit();self.con.close()
        self.con=connect(self.path);self.addCleanup(self.con.close)
        self.assertEqual(self.con.execute('PRAGMA user_version').fetchone()[0],5)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM research_sessions').fetchone()[0],1)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM paper_comparisons').fetchone()[0],0)

    def test_lock_reentrancy_other_process_contention_and_release(self):
        program='from predarb.runtime import writer_lock; import sys\nwith writer_lock(sys.argv[1]): print("acquired")'
        with writer_lock(self.path),writer_lock(self.path):
            child=subprocess.run([sys.executable,'-c',program,self.path],capture_output=True,text=True)
            self.assertNotEqual(child.returncode,0)
            self.assertIn('another predarb writer',child.stderr)
        child=subprocess.run([sys.executable,'-c',program,self.path],capture_output=True,text=True)
        self.assertEqual(child.returncode,0,child.stderr)

    def test_readers_remain_available_while_another_writer_is_running(self):
        with writer_lock(self.path):
            child=subprocess.run([sys.executable,'-m','predarb.cli','ops','events','--db',self.path],capture_output=True,text=True)
            self.assertEqual(child.returncode,0,child.stderr)
            child=subprocess.run([sys.executable,'-m','predarb.cli','research','summary',str(self.session),'--db',self.path],capture_output=True,text=True)
            self.assertEqual(child.returncode,0,child.stderr)
        with patch('sys.argv',['predarb','ops','health',str(self.session),'--db',self.path]),patch('predarb.operations.clock_sync',return_value=SYNC),redirect_stdout(StringIO()):
            self.assertEqual(cli.main(),0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ops_checks').fetchone()[0],0)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'source.sqlite3'
        self.con=connect(str(self.path));self.addCleanup(self.con.close)
        self.con.execute("INSERT INTO ops_events(ts_utc,severity,action,detail_json) VALUES('2030-01-01T00:00:00Z','INFO','HYPOTHETICAL_TEST','{}')");self.con.commit()

    def test_online_wal_backup_and_new_path_restore_preserve_all_logical_content(self):
        target=self.root/'backup.sqlite3'
        before=backup(self.path,target)
        self.assertEqual(verify(target)['logical_sha256'],before['logical_sha256'])
        restored=restore(target,self.root/'restored.sqlite3')
        self.assertTrue(restored['restore_verified'])
        with closing(readonly(self.path)) as con:source=fingerprint(con)
        self.assertEqual(source['logical_sha256'],restored['logical_sha256'])
        self.assertEqual(target.stat().st_mode & 0o777,0o600)

    def test_existing_destination_missing_source_timeout_and_corruption_fail_closed(self):
        target=self.root/'backup.sqlite3';backup(self.path,target)
        with self.assertRaises(ValueError):backup(self.path,target)
        with self.assertRaises(ValueError):restore(target,self.path)
        with self.assertRaises(FileNotFoundError):backup(self.root/'missing.sqlite3',self.root/'other.sqlite3')
        with self.assertRaises(TimeoutError):backup(self.path,self.root/'timeout.sqlite3',timeout_seconds=-1)
        self.assertFalse((self.root/'timeout.sqlite3.partial').exists())
        with target.open('ab') as handle:handle.write(b'HYPOTHETICAL corruption')
        with self.assertRaisesRegex(ValueError,'hash'):verify(target)
        with self.assertRaises(ValueError):restore(target,self.root/'bad-restore.sqlite3')
        self.con.execute('PRAGMA user_version=6');self.con.commit()
        with self.assertRaisesRegex(ValueError,'unsupported'):backup(self.path,self.root/'future.sqlite3')

    def test_manifest_hash_or_logical_digest_tampering_is_detected(self):
        target=self.root/'backup.sqlite3';backup(self.path,target)
        manifest=Path(str(target)+'.manifest.json');data=load_json(manifest.read_bytes())
        data['logical_sha256']='HYPOTHETICAL wrong hash';manifest.write_text(dumps(data))
        with self.assertRaisesRegex(ValueError,'logical'):verify(target)

    def test_low_space_refuses_before_creating_partial_or_destination(self):
        with patch('predarb.backups.disk_usage') as disk:
            disk.return_value.free=1
            with self.assertRaisesRegex(ValueError,'space'):backup(self.path,self.root/'no-space.sqlite3')
        self.assertFalse((self.root/'no-space.sqlite3').exists())
        self.assertFalse((self.root/'no-space.sqlite3.partial').exists())

    def test_malformed_manifests_fail_clearly(self):
        target=self.root/'backup.sqlite3';backup(self.path,target)
        for value in (None,[],{}):
            Path(str(target)+'.manifest.json').write_text(dumps(value))
            with self.assertRaises(ValueError):verify(target)
