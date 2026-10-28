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

from predarb.backups import backup, fingerprint, read_manifest, readonly, restore, verify
from predarb import cli
from predarb.operations import backup_alerts, clock_sync, health, metrics_text, run_cycles
from predarb.research import scan_once, start_session
from predarb.runtime import writer_lock
from predarb.store import connect
from predarb.validation import dumps, load_json, utc_time
from helpers import drop_m5_tables, fixture
from m5_helpers import seed

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
        with patch('predarb.operations.clock',side_effect=[self.now,self.now,self.now,self.now+timedelta(seconds=10)]),patch('predarb.operations.time.monotonic',return_value=0):
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
        manifest=dict(fixture('m5-operations-hypothetical')['manifest'],created_at=(self.now-timedelta(days=2)).isoformat())
        (destination/'old.manifest.json').write_text(dumps(manifest))
        (destination/'old').write_bytes(b'HYPOTHETICAL snapshot existence only; not verified contents')
        with patch('predarb.operations.clock_sync',return_value=SYNC):
            result=health(self.con,self.session,now=self.now,backup_dir=destination)
        self.assertIn('BACKUP_STALE_OR_FUTURE',[row['code'] for row in result['alerts']])
        (destination/'bad.manifest.json').write_text('malformed HYPOTHETICAL input')
        with patch('predarb.operations.clock_sync',return_value=SYNC):
            result=health(self.con,self.session,now=self.now,backup_dir=destination)
        self.assertIn('BACKUP_MANIFEST_UNREADABLE',[row['code'] for row in result['alerts']])

    def test_empty_cycles_warn_even_with_a_healthy_heartbeat(self):
        scan_once(self.con,self.session,now=self.now)
        with patch('predarb.operations.clock_sync',return_value=SYNC):
            result=health(self.con,self.session,now=self.now)
        self.assertTrue(result['ready'])
        self.assertEqual(result['research']['status'],'NO_PAIRS')
        self.assertIn('NO_RESEARCH_PAIRS',[a['code'] for a in result['alerts']])
        self.assertEqual(result['metrics']['research_latest_economics_evaluated'],0)

    def test_economic_coverage_distinguishes_no_edge_from_blocked_stale_and_other_sessions(self):
        case,now,pair,sid,evaluation=seed(self.con,self.root)
        with patch('predarb.operations.clock_sync',return_value=SYNC):
            result=health(self.con,sid,now=now,record=False)
            self.assertEqual(result['research']['status'],'RECENT_ECONOMICS')
            self.assertEqual(result['metrics']['research_latest_modeled_edges'],1)
            # Zero-budget economics still evaluates usable quotes, with no edge.
            zero=start_session(self.con,POLICY,now=now,hypothetical=True)
            replay=self.con.execute('SELECT id FROM research_replays').fetchone()[0]
            scan_once(self.con,zero,now=now,replay_id=replay)
            result=health(self.con,zero,now=now,record=False)
            self.assertEqual(result['research']['status'],'RECENT_ECONOMICS')
            self.assertEqual(result['metrics']['research_latest_rejected'],1)
            self.assertEqual(result['metrics']['research_latest_economics_evaluated'],1)
            self.assertNotIn('NO_RECENT_ECONOMIC_OBSERVATIONS',[a['code'] for a in result['alerts']])
            # A later replay with stale books is a different kind of rejection.
            later=now+timedelta(seconds=90)
            scan_once(self.con,zero,now=later,replay_id=replay)
            result=health(self.con,zero,now=later,record=False)
            self.assertEqual(result['research']['status'],'DATA_GATED')
            self.assertIn('NO_RECENT_ECONOMIC_OBSERVATIONS',[a['code'] for a in result['alerts']])
            result=health(self.con,zero,now=later+timedelta(seconds=121),record=False)
            self.assertEqual(result['research']['status'],'STALE')
            result=health(self.con,zero,now=now,record=False)
            self.assertEqual(result['research']['status'],'FUTURE')
            self.assertFalse(result['ready'])
            # Another session's observations must not hide this empty session.
            result=health(self.con,self.session,now=self.now,record=False)
            self.assertEqual(result['research']['status'],'NO_CYCLES')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ops_checks').fetchone()[0],0)

    def test_runner_warns_when_refresh_is_disabled(self):
        with patch('predarb.operations.clock_sync',return_value=SYNC),redirect_stdout(StringIO()) as output:
            self.assertEqual(run_cycles(self.config),0)
        self.assertIn('RUN_REFRESH_DISABLED',output.getvalue())
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ops_events WHERE action='RUN_REFRESH_DISABLED'").fetchone()[0],1)

    def test_final_shadow_phase_clock_divergence_is_detected(self):
        config=dict(self.config,shadow_policy={'max_hedge_latency_ms':1000,'cancel_after_ms':1000,
                    'cancel_ack_delay_ms':250,'participation':'1','max_price_drift':'.02'})
        with patch('predarb.operations.clock',return_value=self.now),patch('predarb.operations.time.monotonic',side_effect=[0,0,0,10]),patch('predarb.operations.clock_sync',return_value=SYNC),redirect_stdout(StringIO()):
            self.assertEqual(run_cycles(config),2)
        detail=load_json(self.con.execute("SELECT detail_json FROM ops_events WHERE action='WALL_CLOCK_JUMP'").fetchone()[0])
        self.assertEqual(detail['phase'],'AFTER_SHADOW')
        self.assertTrue(detail['cycle_evidence_requires_review'])

    def test_missing_invalid_and_incomplete_cycle_summary_fails_closed(self):
        for index,summary in enumerate(({}, {'pairs_observed':True}, {'pairs_observed':51}, {'pairs_observed':1})):
            with self.subTest(summary=summary):
                stamp=(self.now+timedelta(seconds=index)).isoformat()
                self.con.execute('''INSERT INTO research_cycles(session_id,evaluated_at,recorded_at,status,summary_json)
                    VALUES(?,?,?,'COMPLETE',?)''',(self.session,stamp,stamp,dumps(summary)))
                self.con.commit()
                with patch('predarb.operations.clock_sync',return_value=SYNC),self.assertRaises(ValueError):
                    health(self.con,self.session,now=self.now,record=False)

    def test_clock_jump_during_final_scan_stops_before_shadow_and_retains_cycle(self):
        for jump in fixture('m5-operations-hypothetical')['clock_jumps_seconds']:
            with self.subTest(jump=jump):
                current=[self.now]
                def scanning(con,sid,**kwargs):
                    result=scan_once(con,sid,now=current[0])
                    current[0]+=timedelta(seconds=jump)
                    return result
                config=dict(self.config,shadow_policy={'max_hedge_latency_ms':1000,'cancel_after_ms':1000,
                            'cancel_ack_delay_ms':250,'participation':'1','max_price_drift':'.02'})
                before=self.con.execute('SELECT COUNT(*) FROM research_cycles').fetchone()[0]
                with patch('predarb.operations.clock',side_effect=lambda:current[0]),patch('predarb.operations.time.monotonic',return_value=0),patch('predarb.operations.clock_sync',return_value=SYNC),patch('predarb.operations.scan_once',side_effect=scanning),patch('predarb.operations.create_intent',side_effect=AssertionError('must not create intent')),patch('predarb.operations.compare',side_effect=AssertionError('must not compare')),redirect_stdout(StringIO()) as output:
                    self.assertEqual(run_cycles(config),2)
                self.assertIn('WALL_CLOCK_JUMP',output.getvalue())
                detail=load_json(self.con.execute("SELECT detail_json FROM ops_events WHERE action='WALL_CLOCK_JUMP' ORDER BY id DESC LIMIT 1").fetchone()[0])
                self.assertEqual(detail['phase'],'AFTER_SCAN')
                self.assertTrue(detail['cycle_evidence_requires_review'])
                self.assertIsInstance(detail['cycle_id'],int)
                self.assertEqual(self.con.execute('SELECT COUNT(*) FROM research_cycles').fetchone()[0],before+1)
                self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ops_events WHERE action='RUN_FINISHED'").fetchone()[0],0)
                self.now+=timedelta(seconds=1)

    def test_slow_scan_without_clock_jump_completes(self):
        current=[self.now];elapsed=[0]
        def scanning(con,sid,**kwargs):
            result=scan_once(con,sid,now=current[0])
            current[0]+=timedelta(seconds=20);elapsed[0]+=20
            return result
        with patch('predarb.operations.clock',side_effect=lambda:current[0]),patch('predarb.operations.time.monotonic',side_effect=lambda:elapsed[0]),patch('predarb.operations.clock_sync',return_value=SYNC),patch('predarb.operations.scan_once',side_effect=scanning),redirect_stdout(StringIO()):
            self.assertEqual(run_cycles(self.config),0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ops_events WHERE action='WALL_CLOCK_JUMP'").fetchone()[0],0)

    def test_schema_four_migration_preserves_session_and_adds_no_fake_observations(self):
        drop_m5_tables(self.con);self.con.execute('PRAGMA user_version=4');self.con.commit();self.con.close()
        self.con=connect(self.path);self.addCleanup(self.con.close)
        self.assertEqual(self.con.execute('PRAGMA user_version').fetchone()[0],9)
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
        self.con.execute('PRAGMA user_version=10');self.con.commit()
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


class BackupMonitorTests(unittest.TestCase):
    """Synthetic files test age/existence monitoring, never full backup validity."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.case=fixture('m5-operations-hypothetical')
        self.now=utc_time(self.case['clock'])

    def write_snapshot(self,name,age=timedelta()):
        path=self.root/name
        path.write_bytes(b'HYPOTHETICAL snapshot; not a verified SQLite database')
        manifest=Path(str(path)+'.manifest.json')
        manifest.write_text(dumps(dict(self.case['manifest'],created_at=(self.now-age).isoformat())))
        return path,manifest

    def test_valid_metadata_and_daily_jitter_do_not_claim_content_verification(self):
        self.write_snapshot('recent.sqlite3',timedelta(hours=24,minutes=10))
        self.assertEqual(backup_alerts(self.root,self.now),[])
        self.assertEqual(backup_alerts(self.root,self.now+timedelta(hours=2)),['BACKUP_STALE_OR_FUTURE'])

    def test_orphan_and_empty_snapshot_cannot_hide_stale_backup(self):
        self.write_snapshot('old.sqlite3',timedelta(days=2))
        path,_=self.write_snapshot('orphan.sqlite3');path.unlink()
        path,_=self.write_snapshot('empty.sqlite3');path.write_bytes(b'')
        self.assertEqual(backup_alerts(self.root,self.now),['BACKUP_SNAPSHOT_MISSING','BACKUP_STALE_OR_FUTURE'])

    def test_missing_future_or_unreadable_backups_do_not_suppress_other_faults(self):
        self.assertEqual(backup_alerts(None,self.now),['BACKUP_NOT_OBSERVED'])
        self.assertEqual(backup_alerts(self.root/'missing',self.now),['BACKUP_NOT_OBSERVED'])
        self.write_snapshot('future.sqlite3',timedelta(seconds=-1))
        (self.root/'bad.manifest.json').write_text('HYPOTHETICAL malformed JSON')
        self.assertEqual(backup_alerts(self.root,self.now),
                         ['BACKUP_MANIFEST_UNREADABLE','BACKUP_NOT_OBSERVED','BACKUP_STALE_OR_FUTURE'])
        self.write_snapshot('old.sqlite3',timedelta(days=2))
        self.assertEqual(backup_alerts(self.root,self.now),['BACKUP_MANIFEST_UNREADABLE','BACKUP_STALE_OR_FUTURE'])
        with patch('predarb.operations.read_manifest',side_effect=PermissionError('HYPOTHETICAL denied')):
            self.assertIn('BACKUP_MANIFEST_UNREADABLE',backup_alerts(self.root,self.now))

    def test_manifest_missing_fields_invalid_types_hashes_and_oversize_fail_closed(self):
        _,path=self.write_snapshot('test.sqlite3')
        cases=[{},None,[]]
        for key in self.case['manifest']:
            missing=dict(self.case['manifest']);missing.pop(key);cases.append(missing)
        for key,value in [('format','unknown'),('created_at','bad'),('schema_version',True),
                          ('schema_version',10),('file_sha256','bad'),('logical_sha256','bad'),
                          ('row_counts',{}),('row_counts',{'t':True}),('row_counts',{'t':-1})]:
            cases.append(dict(self.case['manifest'],**{key:value}))
        for value in cases:
            with self.subTest(value=value):
                path.write_text(dumps(value))
                with self.assertRaises(ValueError):read_manifest(path)
                self.assertIn('BACKUP_MANIFEST_UNREADABLE',backup_alerts(self.root,self.now))
        path.write_bytes(b' '*2000001)
        with self.assertRaisesRegex(ValueError,'size limit'):read_manifest(path)
