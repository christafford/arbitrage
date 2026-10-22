"""M2 registry checks. All reviews/approvals in this file are HYPOTHETICAL simulations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from predarb import registry as r
from predarb.store import connect
from predarb.validation import dumps

EXAMPLE = Path(__file__).parents[1] / 'examples' / 'M2_HYPOTHETICAL.json'
NOW = datetime(2029, 1, 1, 12, tzinfo=timezone.utc)
K, P, DIFFERENT = 'HYPOTHETICAL-K', 'HYPOTHETICAL-P', 'HYPOTHETICAL-P-DIFFERENT'


def example_data():
    return json.loads(EXAMPLE.read_text())


def hypothetical_review(con, pair_id, *, now=NOW, inverse=False):
    data = r.review_template(con, pair_id, now=now)
    data.update(reviewer='HYPOTHETICAL reviewer (simulated)', human_reviewed=True,
                reason='HYPOTHETICAL ONLY: comparison of synthetic fully specified terms',
                expires_at=(now + timedelta(hours=1)).isoformat(),
                outcome_mapping={'YES': 'NO', 'NO': 'YES'} if inverse else {'YES': 'YES', 'NO': 'NO'},
                legs={'kalshi': 'YES', 'polymarket_us': 'YES' if inverse else 'NO'})
    for key in r.CHECKS:
        data['comparisons'][key] = {'equivalent': True, 'rationale': 'HYPOTHETICAL fixture terms explicitly agree: ' + key}
    for case in r.SCENARIOS:
        normal = case in {'YES', 'NO'}
        data['settlement_scenarios'].append({
            'case': case, 'condition': 'HYPOTHETICAL ' + case + ' under the documented synthetic terms',
            'kalshi_payout': ('1' if case == 'YES' else '0') if normal else '0.50',
            'polymarket_us_payout': ('0' if case == 'YES' else '1') if normal else '0.50',
            'kalshi_settlement_at': '2030-07-04T12:00:00Z',
            'polymarket_us_settlement_at': '2030-07-04T12:00:00Z'})
    return data


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = connect(str(Path(self.temp.name) / 'registry.sqlite3'))
        self.addCleanup(self.db.close)
        r.load_hypothetical(self.db, example_data(), now=NOW)
        self.pair_id = r.propose(self.db, K, P, 'HYPOTHETICAL proposer', now=NOW)

    def approve(self, pair_id=None, data=None):
        pair_id = pair_id or self.pair_id
        return r.approve(self.db, pair_id, data or hypothetical_review(self.db, pair_id),
                         human_attested=True, now=NOW)

    def change(self, venue='kalshi', source_id=K, text='HYPOTHETICAL CHANGED: first report, not final'):
        contract = deepcopy(r._instrument(self.db, venue, source_id))
        value = json.loads(contract['evidence_json'])['contract']
        value['description'] = text
        return r._record_instrument(self.db, venue, source_id, value, observed_at=NOW.isoformat(),
                                    available=True, hypothetical=True, now=NOW)

    def test_metadata_candidates_never_create_or_approve_pairs(self):
        from unittest.mock import patch
        with patch('predarb.registry.now_utc', return_value=NOW):
            rows = r.candidates(self.db)
        self.assertEqual({row['polymarket_us_id'] for row in rows}, {P, DIFFERENT})
        self.assertTrue(all(row['status'] == 'UNVERIFIED' and row['metadata_overlap_bps'] == 10000 for row in rows))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 1)
        self.assertEqual(r.review(self.db, self.pair_id, now=NOW)['status'], 'UNVERIFIED')
        for kwargs in ({'limit': 0}, {'max_instruments': 0}):
            with self.assertRaises(ValueError):
                r.candidates(self.db, **kwargs)

    def test_identical_titles_but_first_vs_final_report_remains_rejected(self):
        pair_id = r.propose(self.db, K, DIFFERENT, 'HYPOTHETICAL reviewer', now=NOW)
        data = hypothetical_review(self.db, pair_id)
        data['comparisons']['thresholds_revisions'] = {
            'equivalent': False, 'rationale': 'Kalshi FINAL including revisions; other FIRST excluding revisions'}
        with self.assertRaisesRegex(ValueError, 'thresholds_revisions'):
            self.approve(pair_id, data)
        rejected = r.decide(self.db, pair_id, 'REJECTED', 'HYPOTHETICAL reviewer',
                            'First vs final report and different cutoff: not equivalent', now=NOW)
        self.assertEqual(rejected['status'], 'REJECTED')
        self.assertFalse(rejected['trading_authorized'])
        r.candidates(self.db)
        with self.assertRaisesRegex(ValueError, 'UNVERIFIED'):
            self.approve(pair_id, data)
        self.assertEqual(r.review(self.db, pair_id, now=NOW)['status'], 'REJECTED')

    def test_human_attestation_exact_hash_and_complete_review_required(self):
        data = hypothetical_review(self.db, self.pair_id)
        with self.assertRaisesRegex(ValueError, 'human review'):
            r.approve(self.db, self.pair_id, data, now=NOW)
        for key, value in (('human_reviewed', False), ('evidence_sha256', 'incorrect'),
                           ('hypothetical', False), ('reviewer', ''), ('pair_id', True)):
            bad = deepcopy(data)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.approve(data=bad)
        bad = deepcopy(data)
        del bad['comparisons']['resolution_sources']
        with self.assertRaises(ValueError):
            self.approve(data=bad)
        approved = self.approve()
        self.assertEqual(approved['status'], 'APPROVED')
        self.assertTrue(approved['hypothetical'])
        self.assertFalse(approved['trading_authorized'])
        events = r.audit(self.db, self.pair_id)
        self.assertEqual([event['action'] for event in events], ['PROPOSED', 'APPROVED'])
        self.assertIn('resolution_text', dumps(events[-1]['detail']))

    def test_contract_changes_invalidate_and_restoration_never_resurrects(self):
        original = json.loads(r._instrument(self.db, 'kalshi', K)['evidence_json'])['contract']
        self.approve()
        self.change()
        self.assertEqual(self.db.execute('SELECT status FROM pairs').fetchone()[0], 'INVALIDATED')
        r._record_instrument(self.db, 'kalshi', K, original, observed_at=NOW.isoformat(),
                             available=True, hypothetical=True, now=NOW)
        self.assertEqual(r.review(self.db, self.pair_id, now=NOW)['status'], 'INVALIDATED')
        self.assertEqual([event['action'] for event in r.audit(self.db, self.pair_id)], ['PROPOSED', 'APPROVED', 'INVALIDATED'])
        new_id = r.propose(self.db, K, P, 'HYPOTHETICAL new proposal', now=NOW)
        self.assertNotEqual(new_id, self.pair_id)
        self.assertEqual(r.review(self.db, new_id, now=NOW)['status'], 'UNVERIFIED')

    def test_rule_document_bytes_and_text_have_separate_hashes(self):
        self.approve()
        original = r._instrument(self.db, 'kalshi', K)
        text = r.review(self.db, self.pair_id, now=NOW)['instruments'][0]['documents'][0]['resolution_text'].encode()
        doc_id = r.import_document(self.db, 'kalshi', K, 'https://example.invalid/' + K,
                                   b'HYPOTHETICAL changed PDF bytes', text, NOW.isoformat(), 'HYPOTHETICAL importer', now=NOW)
        self.assertEqual(r.review(self.db, self.pair_id, now=NOW)['status'], 'INVALIDATED')
        row = self.db.execute('SELECT raw_bytes,text_bytes,raw_sha256,text_sha256 FROM rule_documents WHERE id=?', (doc_id,)).fetchone()
        self.assertEqual(row[0], b'HYPOTHETICAL changed PDF bytes')
        self.assertEqual(row[1], text)
        self.assertNotEqual(row[2], row[3])

    def test_unchanged_document_refresh_preserves_decision_and_expiry(self):
        approved = self.approve()
        text = approved['instruments'][0]['documents'][0]['resolution_text'].encode()
        r.import_document(self.db, 'kalshi', K, 'https://example.invalid/' + K, text, text,
                          (NOW + timedelta(minutes=1)).isoformat(), 'HYPOTHETICAL importer', now=NOW + timedelta(minutes=1))
        refreshed = r.review(self.db, self.pair_id, now=NOW + timedelta(minutes=1))
        self.assertEqual(refreshed['status'], 'APPROVED')
        self.assertEqual(refreshed['expires_at'], approved['expires_at'])
        self.assertEqual(refreshed['evidence_sha256'], approved['evidence_sha256'])

    def test_expiry_invalidates_on_read_and_is_audited_once(self):
        self.approve()
        later = NOW + timedelta(hours=1)
        self.assertEqual(r.review(self.db, self.pair_id, now=later)['status'], 'EXPIRED')
        r.list_pairs(self.db, now=later)
        self.assertEqual([event['action'] for event in r.audit(self.db, self.pair_id)].count('EXPIRED'), 1)

    def test_unknown_stale_missing_or_future_evidence_blocks_approval(self):
        self.db.execute('DELETE FROM document_heads WHERE venue=?', ('kalshi',))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'documents required'):
            self.approve()
        # New evidence changes the hash, so review forms must always be regenerated.
        self.db.execute('UPDATE registry_instruments SET observed_at=? WHERE venue=?',
                        ((NOW - timedelta(days=2)).isoformat(), 'kalshi'))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.approve()
        self.db.execute('UPDATE registry_instruments SET observed_at=? WHERE venue=?',
                        ((NOW + timedelta(minutes=1)).isoformat(), 'kalshi'))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'future'):
            self.approve()

    def test_expiry_cannot_outlive_evidence_or_be_past(self):
        for expires in (NOW, NOW - timedelta(seconds=1), NOW + timedelta(days=2)):
            data = hypothetical_review(self.db, self.pair_id)
            data['expires_at'] = expires.isoformat()
            with self.subTest(expires=expires), self.assertRaisesRegex(ValueError, 'expiry'):
                self.approve(data=data)

    def test_outcome_mapping_including_inverse_propositions(self):
        for mapping, legs in (({'YES': 'YES', 'NO': 'YES'}, {'kalshi': 'YES', 'polymarket_us': 'NO'}),
                              ({'YES': [], 'NO': 'NO'}, {'kalshi': 'YES', 'polymarket_us': 'NO'}),
                              ({'YES': 'YES', 'NO': 'NO'}, {'kalshi': 'YES', 'polymarket_us': 'YES'})):
            data = hypothetical_review(self.db, self.pair_id)
            data.update(outcome_mapping=mapping, legs=legs)
            with self.subTest(mapping=mapping, legs=legs), self.assertRaises(ValueError):
                self.approve(data=data)
        approved = self.approve(data=hypothetical_review(self.db, self.pair_id, inverse=True))
        self.assertEqual(approved['status'], 'APPROVED')
        self.assertEqual(approved['review']['outcome_mapping']['YES'], 'NO')

    def test_unknown_payouts_bad_totals_missing_exceptions_and_timing_rejected(self):
        for change in ('unknown', 'total', 'float', 'precision', 'missing', 'binary', 'timing', 'rationale'):
            data = hypothetical_review(self.db, self.pair_id)
            if change == 'unknown': data['settlement_scenarios'][2]['kalshi_payout'] = 'UNKNOWN'
            if change == 'total': data['settlement_scenarios'][2]['kalshi_payout'] = '0.40'
            if change == 'precision': data['settlement_scenarios'][0]['kalshi_payout'] = '0.' + '9' * 50
            if change == 'float': data['settlement_scenarios'][2]['kalshi_payout'] = 0.5
            if change == 'missing': data['settlement_scenarios'].pop()
            if change == 'binary':
                data['settlement_scenarios'][0].update(kalshi_payout='0', polymarket_us_payout='1')
            if change == 'timing': data['settlement_scenarios'][0]['kalshi_settlement_at'] = NOW.isoformat()
            if change == 'rationale': data['comparisons']['payout_semantics']['rationale'] = ''
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.approve(data=data)
        self.assertEqual(r.review(self.db, self.pair_id, now=NOW)['status'], 'UNVERIFIED')

    def test_revocation_terminal_and_proposals_do_not_auto_reapprove(self):
        self.approve()
        revoked = r.decide(self.db, self.pair_id, 'REVOKED', 'HYPOTHETICAL reviewer', 'withdrawn for re-review', now=NOW)
        self.assertEqual(revoked['status'], 'REVOKED')
        with self.assertRaises(ValueError): self.approve()
        for decision, actor, reason in (('APPROVED', 'test', 'test'), ('REVOKED', '', 'test'), ('REVOKED', 'test', '')):
            with self.assertRaises(ValueError):
                r.decide(self.db, self.pair_id, decision, actor, reason, now=NOW)

    def test_immutable_rules_documents_and_append_only_audit(self):
        for table in ('rule_versions', 'rule_documents', 'pair_audit'):
            for sql in (f'DELETE FROM {table}', f'UPDATE {table} SET id=id'):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    self.db.execute(sql)
                self.db.rollback()

    def test_document_host_credentials_size_text_and_time_validation(self):
        for url in ('http://example.invalid/rules', 'https://polymarket.com/rules',
                    'https://user:secret@example.invalid/rules', 'https://example.invalid:444/rules',
                    'https://example.invalid/rules#part'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                r.import_document(self.db, 'kalshi', K, url, b'x', b'x', NOW.isoformat(), 'HYPOTHETICAL importer', now=NOW)
        for raw, text, retrieved in ((b'', b'text', NOW), (b'raw', b' ', NOW),
                                     (b'raw', b'\xff', NOW), (b'x' * 2000001, b'x', NOW),
                                     (b'raw', b'text', NOW + timedelta(seconds=10))):
            with self.assertRaises(ValueError):
                r.import_document(self.db, 'kalshi', K, 'https://example.invalid/rules', raw, text,
                                  retrieved.isoformat(), 'HYPOTHETICAL importer', now=NOW)

    def test_hypothetical_fixtures_cannot_contaminate_live_database_or_ids(self):
        with self.assertRaisesRegex(ValueError, 'empty isolated'):
            r.load_hypothetical(self.db, example_data(), now=NOW)
        for hypothetical, source_id in ((True, 'REAL-TICKER'), (False, K)):
            with self.assertRaises(ValueError):
                r._record_instrument(self.db, 'kalshi', source_id, {}, observed_at=NOW.isoformat(),
                                     available=True, hypothetical=hypothetical, now=NOW)
        r._record_instrument(self.db, 'polymarket_us', 'real-us-market', {'description': 'test'},
                             observed_at=NOW.isoformat(), available=True, now=NOW)
        with self.assertRaisesRegex(ValueError, 'mix'):
            r.propose(self.db, K, 'real-us-market', 'HYPOTHETICAL proposer', now=NOW)

    def test_failed_venue_refresh_invalidates_even_without_new_valid_metadata(self):
        from predarb.store import start_run, update_run
        self.approve()
        run_id = start_run(self.db, 'kalshi', 'HYPOTHETICAL failed refresh', {})
        update_run(self.db, run_id, status='FAILED', pages=0, records=0, unique=0,
                   next_page=None, error='HYPOTHETICAL schema drift before first valid page')
        self.assertEqual(r.review(self.db, self.pair_id, now=NOW)['status'], 'INVALIDATED')
        self.assertIn('refresh and human re-review', r.audit(self.db, self.pair_id)[-1]['detail']['reason'])

    def test_collected_event_and_series_amendments_invalidate_decisions(self):
        from predarb import kalshi
        from predarb.provider import HttpClient
        from helpers import Replay, Response
        for kind in ('event', 'series'):
            with self.subTest(kind=kind):
                # HYPOTHETICAL provider responses, not actual contract equivalence claims.
                if kind == 'event':
                    evidence = {'event_ticker': 'HYPOTHETICAL-E', 'series_ticker': 'HYPOTHETICAL-S',
                                'title': 'HYPOTHETICAL event', 'settlement_sources': [{'name': 'HYPOTHETICAL report', 'url': 'https://example.invalid/report'}]}
                    validator = kalshi.validate_event
                else:
                    evidence = {'ticker': 'HYPOTHETICAL-S', 'title': 'HYPOTHETICAL series',
                                'contract_url': 'https://example.invalid/contract',
                                'contract_terms_url': 'https://example.invalid/terms', 'additional_prohibitions': []}
                    validator = kalshi.validate_series
                endpoint = kalshi.BASE + '/' + ('events/HYPOTHETICAL-E' if kind == 'event' else 'series/HYPOTHETICAL-S')
                def observe():
                    client = HttpClient(self.db, 'kalshi', opener=Replay(Response(dumps({kind: evidence}).encode())),
                                        sleep=lambda delay: None, utc_now=lambda: NOW.isoformat())
                    client.get(endpoint, kalshi.SCHEMA_VERSION, validator)
                    r._observe_supplement(self.db, K, kind, evidence, endpoint)
                observe()
                pair_id = self.pair_id if kind == 'event' else r.propose(self.db, K, P, 'HYPOTHETICAL proposer', now=NOW)
                self.approve(pair_id)
                observe()
                self.assertEqual(r.review(self.db, pair_id, now=NOW)['status'], 'APPROVED')
                if kind == 'event':
                    evidence['settlement_sources'][0]['url'] = 'https://example.invalid/revised-report'
                else:
                    evidence['contract_terms_url'] = 'https://example.invalid/revised-terms'
                observe()
                self.assertEqual(r.review(self.db, pair_id, now=NOW)['status'], 'INVALIDATED')
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('DELETE FROM supplement_versions')
        self.db.rollback()
