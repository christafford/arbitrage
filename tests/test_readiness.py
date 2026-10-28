"""M5A E. Positive gate compositions are explicitly HYPOTHETICAL mocks, not live acceptance."""
from contextlib import ExitStack, closing, redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from predarb import cli, readiness as e, registry as r
from predarb.backups import readonly, fingerprint
from predarb.models import AskLevel
from predarb.research import archive_replay, replay_books, start_session
from predarb.runtime import writer_lock
from predarb.store import connect
from predarb.validation import dumps, load_json, utc_time
from helpers import FIXTURES
from test_registry import hypothetical_review


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'HYPOTHETICAL.sqlite3'
        self.con = connect(str(self.path)); self.addCleanup(self.con.close)
        self.fixture = load_json((FIXTURES / 'm5e-hypothetical.json').read_bytes())
        self.now = utc_time(self.fixture['clock'])
        self.raw = (FIXTURES / 'm4-hypothetical.json').read_bytes()
        self.case = load_json(self.raw)

    def seed_pair(self, *, approve=False):
        r.load_hypothetical(self.con, self.case['registry'], now=self.now)
        pair = r.propose(self.con, 'HYPOTHETICAL-K', 'HYPOTHETICAL-P', 'HYPOTHETICAL operator', now=self.now)
        if approve:
            r.approve(self.con, pair, hypothetical_review(self.con, pair, now=self.now, inverse=True),
                      human_attested=True, now=self.now)
        return pair

    def invoke(self, *args):
        out, err = StringIO(), StringIO()
        with patch.object(sys, 'argv', ['predarb', 'research', 'readiness', '--db', str(self.path), *args]), \
                redirect_stdout(out), redirect_stderr(err), patch.object(e, 'clock', return_value=self.now):
            code = cli.main()
        return code, out.getvalue(), err.getvalue()

    def test_empty_archive_json_text_and_writer_lock_are_readonly(self):
        before = fingerprint(self.con)
        with writer_lock(str(self.path)):
            code, text, err = self.invoke('--format', 'json')
        result = load_json(text)
        self.assertEqual((code, err), (2, ''))
        self.assertEqual(result['ready_pair_count'], 0)
        self.assertFalse(result['prerequisites_pass'])
        self.assertIn('2026-10-29', text)
        self.assertEqual(fingerprint(self.con), before)
        code, text, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn('Research readiness: BLOCKED', text)
        self.assertIn('Next:', text)
        self.assertIn('Multiweek acceptance: not established', text)

    def test_hypothetical_approval_never_qualifies_live_readiness(self):
        self.seed_pair(approve=True)
        sid = start_session(self.con, self.case['policy'], now=self.now, hypothetical=True)
        with patch('predarb.operations.clock_sync', return_value={'synchronized': True}):
            result = e.report(self.con, now=self.now, session_id=sid)
        codes = {c['code']: c['status'] for c in result['checks']}
        self.assertEqual(codes['LIVE_ARCHIVE'], 'BLOCKED')
        self.assertEqual(codes['SESSION'], 'BLOCKED')
        self.assertFalse(result['pairs'][0]['ready_now'])
        self.assertFalse(result['multiweek_acceptance'])
        self.assertFalse(result['trading_authorized'])

    def test_readonly_review_recomputes_expiry_without_mutating_or_auditing(self):
        pair = self.seed_pair(approve=True)
        before = fingerprint(self.con)
        with closing(readonly(self.path)) as reader:
            result = r.review(reader, pair, now=self.now + timedelta(days=2), persist=False)
        self.assertEqual(result['status'], 'EXPIRED')
        self.assertEqual(fingerprint(self.con), before)
        # Existing writer behavior still records the same invalidation.
        result = r.review(self.con, pair, now=self.now + timedelta(days=2))
        self.assertEqual(result['status'], 'EXPIRED')
        self.assertNotEqual(fingerprint(self.con), before)

    def test_readonly_review_recomputes_evidence_change_without_writes(self):
        pair = self.seed_pair(approve=True)
        self.con.execute("UPDATE pairs SET evidence_sha256='HYPOTHETICAL changed' WHERE id=?", (pair,))
        self.con.commit()
        before = fingerprint(self.con)
        with closing(readonly(self.path)) as reader:
            result = r.review(reader, pair, now=self.now, persist=False)
        self.assertEqual(result['status'], 'INVALIDATED')
        self.assertEqual(fingerprint(self.con), before)

    def test_missing_file_invalid_input_and_old_schema_never_create_or_migrate(self):
        for args in (('--session-id', '0'), ('--horizon-days', '0'), ('--horizon-days', '32'), ('--session-id', '999')):
            code, text, err = self.invoke(*args)
            self.assertIn(code, (1, 2))
        missing = self.path.parent / 'does-not-exist.sqlite3'
        code, _, err = self.invoke('--db', str(missing))
        self.assertEqual(code, 1); self.assertFalse(missing.exists())
        self.con.execute('PRAGMA user_version=6'); self.con.commit()
        code, text, err = self.invoke('--format', 'json')
        self.assertEqual(code, 2)
        self.assertEqual(load_json(text)['checks'][0]['code'], 'DATABASE_SCHEMA')
        self.assertEqual(self.con.execute('PRAGMA user_version').fetchone()[0], 6)
        self.con.execute('PRAGMA user_version=10'); self.con.commit()
        self.assertEqual(self.invoke()[0], 1)

    def test_registry_bound_and_malformed_pair_do_not_hide_other_results(self):
        self.con.executemany('''INSERT INTO pairs(kalshi_id,polymarket_us_id,hypothetical,created_at,status,evidence_sha256,reason)
            VALUES(?,?,0,?,'UNVERIFIED','HYPOTHETICAL','HYPOTHETICAL broken registry')''',
            [('HYPOTHETICAL-K-' + str(i), 'HYPOTHETICAL-P-' + str(i), self.now.isoformat()) for i in range(51)])
        self.con.commit()
        result = e.report(self.con, now=self.now)
        self.assertEqual(len(result['pairs']), 50)
        self.assertTrue(result['registry']['truncated'])
        self.assertFalse(result['prerequisites_pass'])
        self.assertTrue(all(not row['ready_now'] for row in result['pairs']))

    def test_live_session_host_clock_backup_and_budget_gates(self):
        config = dict(self.case['policy'], kalshi_budget='0')
        sid = start_session(self.con, config, now=self.now)
        before = fingerprint(self.con)
        with patch('predarb.operations.clock_sync', return_value={'synchronized': None}):
            result = e.report(self.con, now=self.now, session_id=sid)
        checks = {c['code']: c for c in result['checks']}
        for code in ('RESEARCH_BUDGETS', 'HOST_HEALTH', 'BACKUP_OBSERVED'):
            self.assertEqual(checks[code]['status'], 'BLOCKED')
        self.assertEqual(fingerprint(self.con), before)
        self.assertIn('CLOCK_SYNC_UNCONFIRMED', dumps(result))
        self.assertFalse(result['run_evidence']['sustained_run_audited'])

    def test_snapshot_preserves_outer_transaction(self):
        self.con.execute("INSERT INTO discovery_state(id,refreshed_at,report_json) VALUES(1,?,'{}')", (self.now.isoformat(),))
        self.assertTrue(self.con.in_transaction)
        e.report(self.con, now=self.now)
        self.assertTrue(self.con.in_transaction)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM discovery_state').fetchone()[0], 1)
        self.con.rollback()
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM discovery_state').fetchone()[0], 0)

    def test_archived_venue_books_use_raw_provenance_and_current_time(self):
        """Offline sanitized venue replay; only the pair-review result is mocked."""
        from predarb import kalshi, polymarket_us
        from predarb.collector import collect
        from predarb.provider import HttpClient
        from helpers import fixture, Replay, Response
        last_receipt = None
        for adapter, prefix in ((kalshi, 'kalshi'), (polymarket_us, 'poly')):
            capture = fixture(prefix + '-scoped-acceptance')
            frames = capture['responses']
            replay = Replay(*(Response(item['body'].encode(), item['status'], item['headers']) for item in frames))
            clock = iter(item['retrieved_at'] for item in frames)
            client = HttpClient(self.con, adapter.VENUE, opener=replay, sleep=lambda delay: None, utc_now=lambda: next(clock))
            scope = load_json(capture['run']['scope_json'])
            collect(self.con, adapter, page_size=scope['page_size'], max_pages=scope['max_pages'], scope=scope['filter'],
                    books=scope['books'], client=client, now=utc_time(capture['run']['finished_at']))
            last_receipt = frames[-1]['retrieved_at']
        captures = dict(self.con.execute('''SELECT r.venue,b.source_id FROM book_captures b
            JOIN raw_observations r ON r.id=b.observation_id ORDER BY b.observation_id'''))
        row = (1, captures['kalshi'], captures['polymarket_us'], 'UNVERIFIED', 0)
        now = utc_time(last_receipt) + timedelta(milliseconds=10)
        before = fingerprint(self.con)
        with patch.object(e.registry, 'review', return_value=self.fixture['simulated_review']), closing(readonly(self.path)) as reader:
            result = e._pair(reader, row, now, timedelta(days=21))
            checks = {c['code']: c for c in result['checks']}
            self.assertIn('UNKNOWN_SOURCE_TIME', dumps(checks['kalshi.BOOK']))
            self.assertEqual(checks['polymarket_us.BOOK']['status'], 'PASS')
            self.assertFalse(result['ready_now'])  # Real fee evidence is absent; mock review cannot bypass it.
            stale = e._pair(reader, row, now + timedelta(seconds=61), timedelta(days=21))
            self.assertIn('STALE', dumps(stale))
        self.assertEqual(fingerprint(self.con), before)
        self.con.execute("UPDATE raw_observations SET body_sha256='HYPOTHETICAL corrupt' WHERE id IN (SELECT observation_id FROM book_captures)")
        self.con.commit()
        with patch.object(e.registry, 'review', return_value=self.fixture['simulated_review']):
            corrupt = e._pair(self.con, row, now, timedelta(days=21))
        self.assertIn('hash mismatch', dumps(corrupt))
        self.assertFalse(corrupt['ready_now'])

    def test_hypothetical_positive_report_composition_and_protocol_failure(self):
        """Mocks stand in for approved real data; production fixtures remain hypothetical."""
        self.seed_pair()
        # Simulate the registry's live-row classification only within this isolated unit test.
        self.con.execute('UPDATE pairs SET hypothetical=0'); self.con.commit()
        sid = start_session(self.con, self.case['policy'], now=self.now)
        pair = {'pair_id': 1, 'ready_now': True, 'horizon_supported': True, 'common_lot': '1',
                'valid_until': (self.now + timedelta(seconds=5)).isoformat(), 'checks': []}
        with patch.object(e, '_pair', return_value=pair), patch.object(e, 'health', return_value=self.fixture['simulated_host']):
            result = e.report(self.con, now=self.now, session_id=sid)
            self.assertTrue(result['prerequisites_pass'])
            self.assertFalse(result['deployment_verified'])
            self.assertFalse(result['fees_or_profit_evaluated'])
            self.assertEqual(self.invoke('--session-id', str(sid))[0], 0)
            pair['horizon_supported'] = False
            result = e.report(self.con, now=self.now, session_id=sid)
            self.assertTrue(result['ready_now']); self.assertFalse(result['prerequisites_pass'])
            pair['horizon_supported'] = True
            config = dict(self.case['policy'], max_contracts='.01')
            small_sid = start_session(self.con, config, now=self.now)
            result = e.report(self.con, now=self.now, session_id=small_sid)
            self.assertFalse(result['prerequisites_pass'])
            self.assertIn('SEARCH_LIMIT', dumps(result))


class HypotheticalPairGateTests(unittest.TestCase):
    """Mock provenance/approvals only; real normalization and depth gates are exercised."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.con = connect(str(Path(self.tmp.name) / 'HYPOTHETICAL.sqlite3')); self.addCleanup(self.con.close)
        self.fixture = load_json((FIXTURES / 'm5e-hypothetical.json').read_bytes())
        self.now = utc_time(self.fixture['clock'])
        raw = (FIXTURES / 'm4-hypothetical.json').read_bytes()
        self.case = load_json(raw)
        replay = archive_replay(self.con, raw, now=self.now)
        books, _ = replay_books(self.con, replay, now=self.now)
        self.books = [replace(books[0], transport='KALSHI_AUTHENTICATED_WS'), books[1]]
        self.row = (1, 'HYPOTHETICAL-K', 'HYPOTHETICAL-P', 'APPROVED', 0)
        self.db = Mock()
        self.schema = e.PROTOCOL_SCHEMAS['clocked']
        self.db.execute.side_effect = lambda sql, params: Mock(fetchone=lambda: (1 if params[0] == 'kalshi' else 2, self.schema))
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.review = self.stack.enter_context(patch.object(e.registry, 'review', return_value=self.fixture['simulated_review']))
        self.fees = self.stack.enter_context(patch.object(e, 'current_profile', side_effect=lambda con, venue, *args, **kw:
            (None, {'id': 1, 'sha256': 'HYPOTHETICAL', 'profile': self.case['fee_profiles'][0 if venue == 'kalshi' else 1]})))
        self.stack.enter_context(patch.object(e, 'load_book', side_effect=lambda con, observed, **kw: (self.books[observed - 1], 1, 1)))
        self.inspect = self.stack.enter_context(patch.object(e, 'inspect_book', side_effect=lambda con, observed, **kw:
            dict(self.books[observed - 1].as_dict(now=kw['now']), observation_id=observed)))

    def report_pair(self, **kwargs):
        return e._pair(self.db, self.row, kwargs.get('now', self.now), timedelta(days=kwargs.get('days', 21)))

    def test_hypothetical_complete_pair_expiries_and_no_write_review(self):
        result = self.report_pair()
        self.assertTrue(result['ready_now'])
        self.assertTrue(result['horizon_supported'])
        self.assertEqual(utc_time(result['valid_until']), self.now + timedelta(seconds=5))
        self.review.assert_called_once_with(self.db, 1, now=self.now, persist=False)

    def test_approval_mechanics_missing_side_and_unsupported_us_no(self):
        for changes in ({'status': 'EXPIRED'}, {'approval_blocker': 'HYPOTHETICAL rules stale'},
                        {'mechanics_assessment': {'status': 'UNVERIFIED'}}, {'review': None},
                        {'review': {'legs': {'kalshi': 'YES', 'polymarket_us': 'NO'}}}):
            with self.subTest(changes=changes):
                self.review.return_value = dict(self.fixture['simulated_review'], **changes)
                self.assertFalse(self.report_pair()['ready_now'])
        self.review.side_effect = ValueError('HYPOTHETICAL document hash mismatch')
        self.assertFalse(self.report_pair()['ready_now'])

    def test_missing_or_rejected_fee_refresh_blocks(self):
        for reason in ('MISSING_FEE_PROFILE', 'FEE_PROFILE_SUPERSEDED_BY_REFRESH', 'STALE_OR_INAPPLICABLE_FEE_PROFILE', 'fee source hash mismatch'):
            with self.subTest(reason=reason):
                self.fees.side_effect = ValueError(reason)
                result = self.report_pair()
                self.assertFalse(result['ready_now']); self.assertIn(reason, dumps(result))

    def test_missing_book_unknown_schema_transport_and_identity(self):
        self.db.execute.side_effect = lambda *args: Mock(fetchone=lambda: None)
        self.assertIn('MISSING_BOOK', dumps(self.report_pair()))
        self.db.execute.side_effect = lambda sql, params: Mock(fetchone=lambda: (1 if params[0] == 'kalshi' else 2, self.schema))
        self.schema = 'unknown-v99'
        self.assertFalse(self.report_pair()['ready_now'])
        self.schema = e.PROTOCOL_SCHEMAS['clocked']
        self.books[0] = replace(self.books[0], transport='REST')
        self.assertIn('TIMESTAMPED_KALSHI_STREAM_REQUIRED', dumps(self.report_pair()))
        self.books[0] = replace(self.books[0], source_id='HYPOTHETICAL-wrong')
        self.assertIn('PAIR_BOOK_IDENTITY_MISMATCH', dumps(self.report_pair()))

    def test_stale_future_unknown_source_time_and_source_or_receipt_skew(self):
        original = self.books[1]
        for changes in ({'received_at': (self.now - timedelta(seconds=61)).isoformat()},
                        {'source_ts': (self.now + timedelta(seconds=6)).isoformat()}, {'source_ts': None},
                        {'source_ts': (self.now - timedelta(seconds=3)).isoformat()},
                        {'received_at': (self.now + timedelta(seconds=3)).isoformat()}):
            with self.subTest(changes=changes):
                self.books[1] = replace(original, **changes)
                self.assertFalse(self.report_pair()['ready_now'])
        self.books[1] = original
        self.inspect.side_effect = ValueError('HYPOTHETICAL raw provenance hash mismatch')
        self.assertFalse(self.report_pair()['ready_now'])

    def test_invalid_prices_missing_fields_and_partial_liquidity(self):
        from predarb.orderbooks import normalize_rest
        for mutation in ('invalid', 'missing'):
            payload = deepcopy(self.case['polymarket_us_rest'])
            if mutation == 'invalid': payload['marketData']['offers'][0]['px']['value'] = '1.50'
            else: payload['marketData'].pop('offers')
            self.books[1] = normalize_rest('polymarket_us', 'HYPOTHETICAL-P', payload, self.case['polymarket_us_metadata'],
                received_at=self.now.isoformat(), metadata_received_at=self.now.isoformat(), now=self.now)
            self.assertFalse(self.report_pair()['ready_now'])
        self.books[1] = replace(self.books[0], venue='polymarket_us', source_id='HYPOTHETICAL-P',
                               mechanism_yes='BUY_LONG_FROM_OFFER')
        self.books[0] = replace(self.books[0], yes_asks=(AskLevel(Decimal('.4'), Decimal('.01')),))
        self.books[1] = replace(self.books[1], quantity_step=Decimal('1'))
        result = self.report_pair()
        self.assertFalse(result['ready_now']); self.assertIn('COMMON_LOT_DEPTH', dumps(result))

    def test_sequence_cutoff_horizon_is_distinct_from_current_data(self):
        self.schema = e.PROTOCOL_SCHEMAS['sequence-v1']
        # Dates are synthetic, including an artificial policy deadline for this isolated test.
        with patch.object(e, 'SEQUENCE_PROTOCOL_END', self.now + timedelta(days=5)):
            self.assertTrue(self.report_pair(days=4)['horizon_supported'])
            result = self.report_pair(days=5)
            self.assertTrue(result['ready_now']); self.assertFalse(result['horizon_supported'])
            self.assertFalse(self.report_pair(days=21)['horizon_supported'])


if __name__ == '__main__':
    unittest.main()
