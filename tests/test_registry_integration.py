"""M2 collection/migration and CLI tests; all decision scenarios are HYPOTHETICAL."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from predarb import cli, kalshi, registry as r
from predarb.collector import collect
from predarb.provider import HttpClient
from predarb.store import connect
from predarb.validation import dumps
from helpers import Replay, Response, payload
from test_registry import EXAMPLE, NOW, K, P, hypothetical_review


class RegistryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'x.sqlite3')

    def collect_page(self, db, page):
        client = HttpClient(db, 'kalshi', opener=Replay(Response(dumps(page).encode())), sleep=lambda delay: None)
        return collect(db, kalshi, page_size=2, max_pages=1, books=0, client=client)

    def test_collector_separates_rule_changes_from_quote_and_timestamp_changes(self):
        # HYPOTHETICAL alterations to captured records. No real pair is approved.
        page = payload('kalshi-page')
        page['cursor'] = ''
        ticker = page['markets'][0]['ticker']
        with connect(self.path) as db:
            self.collect_page(db, page)
            first = r._instrument(db, 'kalshi', ticker)
            page['markets'][0]['yes_bid_dollars'] = '0.0400'
            page['markets'][0]['updated_time'] = '2026-10-21T20:00:00Z'
            self.collect_page(db, page)
            self.assertEqual(r._instrument(db, 'kalshi', ticker)['version_id'], first['version_id'])
            page['markets'][0]['rules_secondary'] += '\nHYPOTHETICAL amendment: earlier cutoff.'
            self.collect_page(db, page)
            current = r._instrument(db, 'kalshi', ticker)
            self.assertNotEqual(current['version_id'], first['version_id'])
            self.assertNotEqual(current['observation_id'], first['observation_id'])
            page['markets'][0]['new_uninterpreted_terms'] = 'HYPOTHETICAL new settlement restriction'
            self.collect_page(db, page)
            self.assertNotEqual(r._instrument(db, 'kalshi', ticker)['version_id'], current['version_id'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)

    def test_v1_database_migrates_and_backfills_existing_catalogue(self):
        page = payload('kalshi-page')
        page['cursor'] = ''
        with connect(self.path) as db:
            self.collect_page(db, page)
            count = db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0]
            # HYPOTHETICAL reconstruction of the previous schema with genuine captured catalogue content.
            from helpers import drop_m4_tables
            drop_m4_tables(db)
            for table in ('normalized_books', 'pair_audit', 'pairs', 'document_heads', 'rule_documents', 'registry_instruments', 'rule_versions', 'registry_supplements', 'supplement_versions'):
                db.execute(f'DROP TABLE {table}')
            db.execute('PRAGMA user_version=1')
        with connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 8)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], count)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM registry_instruments').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM rule_versions').fetchone()[0], 2)

    def invoke(self, *args):
        out, err = StringIO(), StringIO()
        with patch('sys.argv', ['predarb', 'pairs', *args, '--db', self.path]), patch('predarb.registry.now_utc', return_value=NOW), redirect_stdout(out), redirect_stderr(err):
            code = cli.main()
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_cli_review_approve_revoke_and_audit(self):
        self.assertEqual(self.invoke('load-example', '--fixture', str(EXAMPLE))[0], 0)
        code, suggestions, _ = self.invoke('candidates')
        self.assertEqual((code, len(suggestions)), (0, 2))
        code, pair, _ = self.invoke('propose', '--kalshi', K, '--polymarket-us', P, '--operator', 'HYPOTHETICAL proposer')
        self.assertEqual(code, 0)
        pair_id = pair['pair_id']
        form = Path(self.temp.name) / 'review.json'
        code, view, _ = self.invoke('review', str(pair_id), '--template-output', str(form))
        self.assertEqual((code, view['status']), (0, 'UNVERIFIED'))
        self.assertFalse(json.loads(form.read_text())['human_reviewed'])
        self.assertEqual(self.invoke('review', str(pair_id), '--template-output', str(form))[0], 1)
        with connect(self.path) as db:
            form.write_text(dumps(hypothetical_review(db, pair_id)))
        code, _, err = self.invoke('approve', str(pair_id), '--review-file', str(form))
        self.assertEqual(code, 1)
        self.assertIn('human review', err)
        code, approved, err = self.invoke('approve', str(pair_id), '--review-file', str(form), '--human-review')
        self.assertEqual((code, approved['status'], approved['trading_authorized']), (0, 'APPROVED', False))
        code, revoked, _ = self.invoke('revoke', str(pair_id), '--operator', 'HYPOTHETICAL reviewer', '--reason', 'test revocation')
        self.assertEqual((code, revoked['status']), (0, 'REVOKED'))
        code, audit, _ = self.invoke('audit', '--pair-id', str(pair_id))
        self.assertEqual(code, 0)
        self.assertEqual([event['action'] for event in audit], ['PROPOSED', 'APPROVED', 'REVOKED'])
        self.assertEqual(self.invoke('list')[1][0]['status'], 'REVOKED')

    def test_cli_document_import_invalidates_current_hypothetical_approval(self):
        self.invoke('load-example', '--fixture', str(EXAMPLE))
        with connect(self.path) as db:
            pair_id = r.propose(db, K, P, 'HYPOTHETICAL proposer', now=NOW)
            r.approve(db, pair_id, hypothetical_review(db, pair_id), human_attested=True, now=NOW)
        source = Path(self.temp.name) / 'terms.txt'
        source.write_text('HYPOTHETICAL changed rule: first report now controls.')
        code, imported, _ = self.invoke('document', '--venue', 'kalshi', '--source-id', K,
                                       '--url', 'https://example.invalid/' + K, '--source-file', str(source),
                                       '--text-file', str(source), '--retrieved-at', NOW.isoformat(),
                                       '--operator', 'HYPOTHETICAL importer')
        self.assertEqual(code, 0)
        self.assertIsInstance(imported['document_id'], int)
        self.assertEqual(self.invoke('review', str(pair_id))[1]['status'], 'INVALIDATED')

    def test_cli_malformed_missing_files_and_invalid_ids_fail_clearly(self):
        self.invoke('load-example', '--fixture', str(EXAMPLE))
        code, _, err = self.invoke('review', '9999')
        self.assertEqual(code, 1)
        self.assertNotIn('Traceback', err)
        self.assertEqual(self.invoke('load-example', '--fixture', str(Path(self.temp.name)/'missing.json'))[0], 1)
        form = Path(self.temp.name)/'broken.json'
        form.write_text('{"x":1,"x":2}')
        self.assertEqual(self.invoke('approve', '1', '--review-file', str(form), '--human-review')[0], 1)
