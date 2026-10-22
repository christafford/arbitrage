"""M4 registry/fee/scanner integration. All approvals and favorable books hypothetical."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from io import StringIO
import csv
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from predarb import cli, registry as r
from predarb.fee_store import current_profile, import_profile
from predarb.research import (archive_replay, export_csv, prune_details, scan_once,
                              start_session, summary)
from predarb.store import connect
from predarb.validation import dumps, load_json, utc_time
from helpers import FIXTURES, drop_m4_tables
from test_registry import hypothetical_review


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=str(self.root/'isolated.sqlite3')
        self.db=connect(self.path);self.addCleanup(self.db.close)
        self.raw=(FIXTURES/'m4-hypothetical.json').read_bytes()
        self.data=load_json(self.raw);self.now=utc_time(self.data['clock'])
        r.load_hypothetical(self.db,self.data['registry'],now=self.now)
        self.pair=r.propose(self.db,'HYPOTHETICAL-K','HYPOTHETICAL-P','HYPOTHETICAL proposer',now=self.now)
        r.approve(self.db,self.pair,hypothetical_review(self.db,self.pair,now=self.now,inverse=True),human_attested=True,now=self.now)
        (self.root/'HYPOTHETICAL-fees.txt').write_text('HYPOTHETICAL fee applicability; not observed venue terms.\n')
        for profile in self.data['fee_profiles']:self.import_fee(profile)
        self.replay=archive_replay(self.db,self.raw,now=self.now)
        self.session=start_session(self.db,self.data['policy'],now=self.now,hypothetical=True,interval_seconds=30)

    def import_fee(self,profile,**kwargs):
        return import_profile(self.db,dumps(profile).encode(),base=self.root,now=self.now,attested=True,**kwargs)

    def cycle(self,*,now=None):
        return scan_once(self.db,self.session,now=now or self.now,replay_id=self.replay)

    def test_positive_replay_has_raw_hash_registry_fee_provenance_and_durable_details(self):
        result=self.cycle()
        self.assertEqual(result['modeled_edges'],1)
        digest,encoded=self.db.execute('SELECT e.detail_sha256,d.detail_json FROM research_evaluations e JOIN research_details d ON d.evaluation_id=e.id').fetchone()
        self.assertEqual(digest,sha256(encoded.encode()).hexdigest())
        detail=load_json(encoded)
        self.assertEqual(detail['registry']['status'],'APPROVED')
        self.assertEqual(detail['replay_sha256'],sha256(self.raw).hexdigest())
        self.assertEqual(len(detail['fee_profiles']),2)
        self.assertEqual(detail['economics']['best']['contracts'],'200')
        self.assertTrue(detail['hypothetical'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0],0)

    def test_resume_clock_cadence_equal_samples_staleness_and_not_thirty_days(self):
        self.cycle()
        with self.assertRaisesRegex(ValueError,'advance'):self.cycle()
        self.db.close();self.db=connect(self.path);self.addCleanup(self.db.close)
        self.cycle(now=self.now+timedelta(seconds=30))
        report=summary(self.db,self.session)
        self.assertEqual(report['cycles'],2)
        self.assertEqual(report['equal_quote_samples'][0]['seconds_between_equal_samples'],30)
        self.assertFalse(report['thirty_day_acceptance'])
        self.assertFalse(report['observed_window_qualifies_for_audit'])
        self.assertEqual(self.cycle(now=self.now+timedelta(seconds=61))['rejected'],1)
        report=summary(self.db,self.session)
        self.assertTrue(any('STALE' in key for key in report['rejection_counts']))
        self.assertFalse(report['continuous_quote_lifespan_verified'])

    def test_revoked_or_expired_pairs_never_reach_economic_calculation(self):
        r.decide(self.db,self.pair,'REVOKED','HYPOTHETICAL reviewer','HYPOTHETICAL withdrawal',now=self.now)
        with patch('predarb.research.evaluate',side_effect=AssertionError('must not evaluate')):
            self.assertEqual(self.cycle()['rejected'],1)
        self.assertIn('PAIR_NOT_CURRENTLY_APPROVED',dumps(summary(self.db,self.session)))

    def test_missing_expired_newer_failed_and_future_fee_profiles_fail_closed(self):
        profile=deepcopy(self.data['fee_profiles'][0]);profile['effective_from']='2030-01-01T12:30:00Z'
        self.import_fee(profile)
        self.assertEqual(self.cycle()['rejected'],1)
        # A failed refresh for the identity must not fall back to an earlier profile.
        bad=deepcopy(profile);bad['kind']='unknown'
        with self.assertRaises(ValueError):self.import_fee(bad)
        with self.assertRaisesRegex(ValueError,'SUPERSEDED'):
            current_profile(self.db,'kalshi','HYPOTHETICAL-K','YES',now=self.now,hypothetical=True)
        self.assertEqual(self.db.execute('SELECT status FROM fee_imports ORDER BY id DESC LIMIT 1').fetchone()[0],'REJECTED')
        with self.assertRaises(ValueError):
            current_profile(self.db,'polymarket_us','HYPOTHETICAL-P','NO',now=self.now,hypothetical=True)
        with self.assertRaisesRegex(ValueError,'STALE'):
            current_profile(self.db,'polymarket_us','HYPOTHETICAL-P','YES',now=self.now+timedelta(hours=2),hypothetical=True)

    def test_fee_source_archival_missing_attestation_bad_host_and_time(self):
        raw=dumps(self.data['fee_profiles'][0]).encode()
        with self.assertRaisesRegex(ValueError,'attestation'):
            import_profile(self.db,raw,base=self.root,now=self.now)
        self.assertEqual(self.db.execute('SELECT raw_bytes FROM fee_imports ORDER BY id DESC LIMIT 1').fetchone()[0],raw)
        for change in ('host','stale','future','expiry','file','hypothetical'):
            profile=deepcopy(self.data['fee_profiles'][0])
            if change=='host':profile['documents'][0]['url']='https://polymarket.com/fees'
            if change=='stale':profile['documents'][0]['retrieved_at']='2029-01-01T00:00:00Z'
            if change=='future':profile['documents'][0]['retrieved_at']='2030-01-02T00:00:00Z'
            if change=='expiry':profile['expires_at']='2030-01-03T00:00:00Z'
            if change=='file':profile['documents'][0]['path']='missing.txt'
            if change=='hypothetical':profile['hypothetical']=False
            with self.subTest(change=change),self.assertRaises((ValueError,OSError)):self.import_fee(profile)

    def test_audit_fee_and_summary_immutable_and_retention_preserves_evidence(self):
        self.cycle()
        for table in ('research_sessions','research_cycles','research_evaluations','research_audit','fee_profiles','fee_documents','research_replays'):
            with self.subTest(table=table),self.assertRaises(sqlite3.IntegrityError):self.db.execute('DELETE FROM '+table)
            self.db.rollback()
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE fee_imports SET raw_bytes=x'00'")
        self.db.rollback()
        later=self.now+timedelta(days=32)
        self.assertEqual(prune_details(self.db,now=later)['candidate_details'],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_details').fetchone()[0],1)
        self.assertTrue(prune_details(self.db,now=later,apply=True)['applied'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_details').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_evaluations').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM fee_documents').fetchone()[0],2)
        self.assertEqual(summary(self.db,self.session)['cycles'],1)
        with self.assertRaises(ValueError):prune_details(self.db,keep_days=30)

    def test_csv_and_ranking_are_independent_alternatives_without_repeated_profit_sum(self):
        self.cycle();self.cycle(now=self.now+timedelta(seconds=30))
        rows=list(csv.DictReader(StringIO(export_csv(self.db,self.session))))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['contracts'],'200')
        self.assertEqual(Decimal(rows[0]['net_profit_bound']),Decimal('16.54'))
        report=summary(self.db,self.session)
        self.assertEqual(len(report['latest_ranked_independent_alternatives']),1)
        self.assertNotIn('total_profit',report)

    def test_failed_cycle_leaves_attempt_audit_and_disk_guard(self):
        with patch('predarb.research.replay_books',side_effect=ValueError('HYPOTHETICAL malformed frame')):
            with self.assertRaises(ValueError):self.cycle()
        self.assertEqual(summary(self.db,self.session)['unfinished_cycle_attempts'],1)
        with patch('predarb.research.disk_usage') as disk:
            disk.return_value.free=1
            with self.assertRaisesRegex(ValueError,'disk'):self.cycle()

    def test_schema_three_migration_preserves_raw_and_registry_without_fabricated_scans(self):
        drop_m4_tables(self.db);self.db.execute('PRAGMA user_version=3');self.db.commit();self.db.close()
        self.db=connect(self.path);self.addCleanup(self.db.close)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],5)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_cycles').fetchone()[0],0)

    def invoke(self,*args):
        out,err=StringIO(),StringIO()
        with patch('sys.argv',['predarb','research',*args,'--db',self.path]),redirect_stdout(out),redirect_stderr(err):
            status=cli.main()
        return status,out.getvalue(),err.getvalue()

    def test_cli_reports_exports_refuses_simulated_polling_and_invalid_arguments(self):
        self.cycle()
        self.assertEqual(self.invoke('summary',str(self.session))[0],0)
        output=self.root/'out.csv'
        self.assertEqual(self.invoke('csv',str(self.session),'--output',str(output))[0],0)
        self.assertEqual(self.invoke('csv',str(self.session),'--output',str(output))[0],1)
        self.assertEqual(self.invoke('scan',str(self.session))[0],1)
        self.assertEqual(self.invoke('prune','--keep-days','30')[0],1)
        profile=self.root/'profile.json';profile.write_text(dumps(self.data['fee_profiles'][0]))
        self.assertEqual(self.invoke('fees-import',str(profile))[0],1)
        self.assertNotIn('Traceback',self.invoke('summary','9999')[2])


class LiveEmptySessionTests(unittest.TestCase):
    def test_cli_start_poll_resume_limits_and_read_only_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);db=str(root/'empty.sqlite3')
            policy_path=root/'policy.json'
            policy_path.write_text((Path(__file__).parents[1]/'examples/M4_RESEARCH_POLICY.json').read_text())
            def invoke(*args):
                out,err=StringIO(),StringIO()
                with patch('sys.argv',['predarb','research',*args,'--db',db]),redirect_stdout(out),redirect_stderr(err):
                    code=cli.main()
                return code,out.getvalue()
            code,out=invoke('start','--policy',str(policy_path),'--interval','1')
            self.assertEqual(code,0);sid=str(json.loads(out)['session_id'])
            with patch('predarb.research_cli.time.sleep') as sleep:
                code,out=invoke('scan',sid,'--cycles','2','--refresh')
                self.assertEqual(code,0);self.assertEqual(len(out.splitlines()),2);sleep.assert_called_once()
            self.assertEqual(invoke('scan',sid,'--cycles','0')[0],1)
            self.assertEqual(invoke('scan',sid,'--cycles','2678401')[0],1)
            self.assertEqual(invoke('summary',sid)[0],0)

    def test_empty_live_cli_session_scan_and_resume_never_fetches_without_approved_pairs(self):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'live.sqlite3')
            data={'max_contracts':'10','kalshi_budget':'0','polymarket_us_budget':'0','reserve_per_leg':'.005','min_profit':'.01'}
            with connect(path) as con:
                now=utc_time('2026-10-21T12:00:00Z')
                sid=start_session(con,data,now=now)
                with patch('predarb.research._refresh',side_effect=AssertionError('no unapproved collection')):
                    result=scan_once(con,sid,now=now,refresh=True)
                self.assertTrue(result['no_pairs'])
                self.assertFalse(summary(con,sid)['thirty_day_acceptance'])
                with self.assertRaises(ValueError):scan_once(con,sid,now=now,replay_id=1)
