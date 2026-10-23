"""M5A C offline replay; every altered source/approval here is HYPOTHETICAL."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from predarb import cli, registry
from predarb.fee_capture import SCHEMA, capture, export_review, review
from predarb.fee_store import current_profile, import_profile
from predarb.provider import FEE_DOCUMENT_URLS, HttpClient
from predarb.store import connect
from predarb.validation import dumps, load_json, utc_time
from helpers import fixture, Replay, Response


class FeeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = str(self.root / 'HYPOTHETICAL.sqlite3')
        self.con = connect(self.path)
        self.addCleanup(self.con.close)
        self.fixtures = {venue: fixture('m5c-' + venue + '-live') for venue in FEE_DOCUMENT_URLS}
        self.venue = 'kalshi'

    def times(self, venue):
        captured = utc_time(self.fixtures[venue]['request']['captured_at'])
        return captured, captured + timedelta(minutes=1)

    def run_capture(self, venue='kalshi', sources=None, *, offset=0):
        evidence = self.fixtures[venue]
        sources = deepcopy(sources if sources is not None else evidence['sources'])
        replay = Replay(*(Response(s['body'].encode(), s['status'], s['headers']) for s in sources))
        times = iter((utc_time(s['retrieved_at']) + timedelta(seconds=offset)).isoformat() for s in sources)
        client = HttpClient(self.con, venue, opener=replay, sleep=lambda _: None, utc_now=lambda: next(times), attempts=1)
        captured, _ = self.times(venue)
        result = capture(self.con, venue, evidence['request']['source_id'], 'YES',
                         now=captured + timedelta(seconds=offset), client=client)
        self.assertFalse(replay.responses)
        self.assertTrue(all(request.method == 'GET' for request, _ in replay.requests))
        return result

    def mutate(self, index, mutate, venue='kalshi'):
        sources = deepcopy(self.fixtures[venue]['sources'])
        value = json.loads(sources[index]['body'])
        mutate(value)
        sources[index]['body'] = json.dumps(value)
        return sources

    def reviewed_profile(self, venue='kalshi', sources=None):
        capture_id = self.run_capture(venue, sources)
        _, now = self.times(venue)
        profile = review(self.con, capture_id, now=now)['draft']
        # A simulated human decision in an isolated offline test DB only.
        profile.update(version='HYPOTHETICAL review', operator='HYPOTHETICAL reviewer', applicability_reviewed=True,
                       effective_from=now.isoformat(), settlement_fee_per_contract='0',
                       instrument_scope='HYPOTHETICAL exact single contract review',
                       scheduled_changes_checked='HYPOTHETICAL reviewed all sources',
                       account_fee_extras_checked='NONE_CONFIRMED', schedule_reviewed='HYPOTHETICAL schedule review',
                       category_reviewed='HYPOTHETICAL category and exceptions review')
        if venue == 'kalshi':
            (self.root / 'HYPOTHETICAL.pdf').write_bytes(b'%PDF-1.7\nHYPOTHETICAL fixture, not venue terms\n')
            profile['balance_precision'] = '.01'
            profile['documents'][0].update(path='HYPOTHETICAL.pdf', retrieved_at=now.isoformat())
        # Registry identity exists but no real pair is approved, and nothing trades.
        registry._record_instrument(self.con, venue, profile['source_id'],
                                    {'test': 'HYPOTHETICAL isolated operator simulation'},
                                    observed_at=now.isoformat(), available=True, now=now)
        return profile, now

    def cli(self, args):
        with patch('sys.argv', ['predarb', *args]):
            return cli.main()

    def import_fee(self, profile, now, *, attested=True):
        return import_profile(self.con, dumps(profile).encode(), base=self.root, now=now, attested=attested)

    def test_real_fixture_hashes_and_deterministic_replay_both_venues(self):
        for venue in self.fixtures:
            with self.subTest(venue=venue):
                for source in self.fixtures[venue]['sources']:
                    self.assertEqual(source['schema_version'], SCHEMA)
                    self.assertEqual(source['body_sha256'], sha256(source['body'].encode()).hexdigest())
                    self.assertNotIn('set-cookie', source['headers'])
                cid = self.run_capture(venue)
                _, now = self.times(venue)
                packet = review(self.con, cid, now=now)
                self.assertEqual(packet, review(self.con, cid, now=now))
                self.assertEqual(packet['status'], 'NEEDS_OPERATOR_REVIEW')
                self.assertFalse(packet['draft']['applicability_reviewed'])
                self.assertEqual(packet['draft']['settlement_fee_per_contract'], '')
                self.assertFalse(packet['trading_authorized'])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM fee_profiles').fetchone()[0], 0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], 9)

    def test_missing_invalid_fee_parameters_archive_before_rejecting(self):
        changes = [('missing', lambda s: s.pop('fee_multiplier')),
                   ('string', lambda s: s.update(fee_multiplier='1')),
                   ('boolean', lambda s: s.update(fee_multiplier=True)),
                   ('negative', lambda s: s.update(fee_multiplier=-1)),
                   ('excessive', lambda s: s.update(fee_multiplier=101)),
                   ('unknown', lambda s: s.update(fee_type='flat'))]
        for name, change in changes:
            with self.subTest(name=name):
                sources = self.mutate(2, lambda d: change(d['series']))
                with self.assertRaises(ValueError):
                    self.run_capture(sources=sources)
                row = self.con.execute('SELECT raw_body FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone()
                self.assertEqual(row[0], sources[2]['body'].encode())
                self.assertEqual(self.con.execute('SELECT status FROM fee_imports ORDER BY id DESC LIMIT 1').fetchone()[0], 'CAPTURE_FAILED')

    def test_us_unknown_missing_zero_negative_coefficient_and_invalid_price(self):
        for value in (None, 0, -1, True, '0.0695', 0.03):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_capture('polymarket_us', self.mutate(0, lambda d: d['market'].update(feeCoefficient=value), 'polymarket_us'))
        sources = self.mutate(0, lambda d: d['market']['bestAskQuote'].update(value='1.1'), 'polymarket_us')
        with self.assertRaisesRegex(ValueError, 'price outside'):
            self.run_capture('polymarket_us', sources)

    def test_explicit_table_tennis_and_zero_kalshi_multiplier(self):
        sources = self.mutate(0, lambda d: d['market'].update(feeCoefficient=0.10), 'polymarket_us')
        cid = self.run_capture('polymarket_us', sources)
        self.assertEqual(review(self.con, cid, now=self.times('polymarket_us')[1])['draft']['kind'], 'table_tennis')
        sources = self.mutate(2, lambda d: d['series'].update(fee_multiplier=0))
        cid = self.run_capture(sources=sources)
        self.assertEqual(review(self.con, cid, now=self.times('kalshi')[1])['draft']['multiplier'], '0')

    def test_event_override_and_incomplete_override(self):
        sources = self.mutate(1, lambda d: d['event'].update(fee_type_override='quadratic', fee_multiplier_override=2))
        cid = self.run_capture(sources=sources)
        packet = review(self.con, cid, now=self.times('kalshi')[1])
        self.assertEqual(packet['draft']['multiplier'], '2')
        self.assertTrue(packet['analysis']['scope']['event_override'])
        sources = self.mutate(1, lambda d: d['event'].update(fee_type_override='quadratic'))
        with self.assertRaises(ValueError): self.run_capture(sources=sources)

    def test_identity_mismatch_and_waiver_fail_closed(self):
        cases = [(0, lambda d: d['market'].update(ticker='HYPOTHETICAL-WRONG')),
                 (1, lambda d: d['event'].update(event_ticker='HYPOTHETICAL-WRONG')),
                 (2, lambda d: d['series'].update(ticker='HYPOTHETICAL-WRONG')),
                 (0, lambda d: d['market'].update(fee_waiver_expiration_time='2030-01-01T00:00:00Z'))]
        for index, mutate in cases:
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.run_capture(sources=self.mutate(index, mutate))

    def series_change(self, *, hours=2):
        captured, _ = self.times('kalshi')
        series_id = load_json(self.fixtures['kalshi']['sources'][2]['body'])['series']['ticker']
        return {'id': 'HYPOTHETICAL-change', 'series_ticker': series_id, 'fee_type': 'quadratic',
                'fee_multiplier': 2, 'scheduled_ts': (captured + timedelta(hours=hours)).isoformat()}

    def test_scheduled_series_change_caps_window_and_rejects_at_boundary(self):
        change = self.series_change()
        sources = self.mutate(3, lambda d: d.update(series_fee_change_arr=[change]))
        profile, now = self.reviewed_profile(sources=sources)
        self.assertEqual(profile['effective_until'], change['scheduled_ts'])
        self.import_fee(profile, now)
        current_profile(self.con, 'kalshi', profile['source_id'], 'YES', now=now, hypothetical=False)
        with self.assertRaises(ValueError):
            review(self.con, profile['capture_id'], now=utc_time(change['scheduled_ts']))
        profile['effective_until'] = (now + timedelta(hours=3)).isoformat()
        with self.assertRaisesRegex(ValueError, 'window'): self.import_fee(profile, now)

    def test_event_change_clear_caps_expiry_and_history_is_bounded(self):
        change = self.series_change(hours=1)
        change.pop('fee_type'); change.pop('fee_multiplier')
        change.update(event_ticker=load_json(self.fixtures['kalshi']['sources'][1]['body'])['event']['event_ticker'],
                      fee_type_override=None, fee_multiplier_override=None)
        cid = self.run_capture(sources=self.mutate(4, lambda d: d.update(event_fee_changes=[change])))
        self.assertEqual(review(self.con, cid, now=self.times('kalshi')[1])['expires_no_later_than'], change['scheduled_ts'])
        with self.assertRaisesRegex(ValueError, 'partial'):
            self.run_capture(sources=self.mutate(4, lambda d: d.update(cursor='HYPOTHETICAL-more')))
        change.pop('fee_multiplier_override')
        with self.assertRaisesRegex(ValueError, 'missing event'):
            self.run_capture(sources=self.mutate(4, lambda d: d.update(event_fee_changes=[change])))

    def test_bad_change_identity_duplicate_and_past_pending_change(self):
        for mode in ('duplicate', 'wrong-series', 'past', 'missing-time'):
            change = self.series_change(hours=-1 if mode == 'past' else 2)
            if mode == 'wrong-series': change['series_ticker'] = 'HYPOTHETICAL-wrong'
            if mode == 'missing-time': change.pop('scheduled_ts')
            changes = [change, change] if mode == 'duplicate' else [change]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.run_capture(sources=self.mutate(3, lambda d: d.update(series_fee_change_arr=changes)))

    def test_expiry_future_clock_and_document_hash_corruption(self):
        cid = self.run_capture()
        captured, now = self.times('kalshi')
        with self.assertRaisesRegex(ValueError, 'STALE'):
            review(self.con, cid, now=captured + timedelta(hours=24))
        with self.assertRaisesRegex(ValueError, 'future'):
            review(self.con, cid, now=captured - timedelta(minutes=1))
        # Simulated disk corruption bypasses immutability only in this test.
        self.con.execute('DROP TRIGGER fee_documents_no_update')
        self.con.execute("UPDATE fee_documents SET raw_bytes=x'00' WHERE import_id=?", (cid,))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            review(self.con, cid, now=now)

    def test_hypothetical_operator_import_both_venues_and_scanner_lookup(self):
        for venue in self.fixtures:
            with self.subTest(venue=venue):
                profile, now = self.reviewed_profile(venue)
                imported = self.import_fee(profile, now)
                model, provenance = current_profile(self.con, venue, profile['source_id'], 'YES', now=now, hypothetical=False)
                self.assertEqual(provenance['id'], imported)
                self.assertGreater(model.coefficient, Decimal(0))
                self.assertEqual(len(provenance['source_hashes']), 8 if venue == 'kalshi' else 2)
                with self.assertRaises(ValueError):
                    current_profile(self.con, venue, profile['source_id'], 'NO', now=now, hypothetical=False)

    def test_missing_attestation_and_review_fields_and_old_live_format_rejected(self):
        profile, now = self.reviewed_profile('polymarket_us')
        with self.assertRaisesRegex(ValueError, 'attestation'):
            self.import_fee(profile, now, attested=False)
        for key in ('capture_id', 'schedule_reviewed', 'category_reviewed', 'settlement_fee_per_contract', 'instrument_scope'):
            changed = deepcopy(profile); changed.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError): self.import_fee(changed, now)

    def test_mismatch_and_stale_capture_never_import(self):
        profile, now = self.reviewed_profile()
        for key, value in [('capture_sha256', 'bad'), ('kind', 'quadratic_with_maker_fees'), ('multiplier', '2'),
                           ('side', 'NO'), ('account_fee_extras_checked', 'UNKNOWN')]:
            changed = deepcopy(profile); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.import_fee(changed, now)
        with self.assertRaises(ValueError): self.import_fee(profile, now + timedelta(days=1))

    def test_new_capture_and_failed_refresh_block_old_approval_and_old_capture_reuse(self):
        profile, now = self.reviewed_profile('polymarket_us')
        self.import_fee(profile, now)
        bad = self.mutate(0, lambda d: d['market'].pop('feeCoefficient'), 'polymarket_us')
        with self.assertRaises(ValueError): self.run_capture('polymarket_us', bad, offset=70)
        with self.assertRaisesRegex(ValueError, 'SUPERSEDED'):
            current_profile(self.con, 'polymarket_us', profile['source_id'], 'YES', now=now, hypothetical=False)
        with self.assertRaisesRegex(ValueError, 'superseded'): self.import_fee(profile, now)
        cid = self.run_capture('polymarket_us', offset=80)
        self.assertEqual(review(self.con, cid, now=now + timedelta(minutes=1))['status'], 'NEEDS_OPERATOR_REVIEW')
        with self.assertRaisesRegex(ValueError, 'superseded'): self.import_fee(profile, now)

    def test_pending_capture_blocks_older_approval_after_interruption(self):
        profile, now = self.reviewed_profile('polymarket_us')
        self.import_fee(profile, now)
        with patch('predarb.fee_capture.HttpClient.get', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                capture(self.con, 'polymarket_us', profile['source_id'], 'YES', now=now)
        self.assertEqual(self.con.execute('SELECT status FROM fee_imports ORDER BY id DESC LIMIT 1').fetchone()[0], 'CAPTURE_PENDING')
        with self.assertRaisesRegex(ValueError, 'SUPERSEDED'):
            current_profile(self.con, 'polymarket_us', profile['source_id'], 'YES', now=now, hypothetical=False)

    def test_kalshi_pdf_required_rejects_error_page_and_expired_file(self):
        profile, now = self.reviewed_profile()
        for mode in ('missing', 'html', 'stale'):
            changed = deepcopy(profile)
            if mode == 'missing': changed['documents'] = []
            if mode == 'html': (self.root / 'HYPOTHETICAL.pdf').write_text('<html>429</html>')
            if mode == 'stale':
                (self.root / 'HYPOTHETICAL.pdf').write_bytes(b'%PDF-1.7 HYPOTHETICAL')
                changed['documents'][0]['retrieved_at'] = (now - timedelta(days=2)).isoformat()
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.import_fee(changed, now)

    def test_document_transport_limits_and_fixed_origin(self):
        for body, content_type, status in [(b'<html>login</html>', 'text/html', 200),
                                            (b'', 'text/plain', 200), (b'\xff', 'text/plain', 200),
                                            (b'x' * 2000001, 'text/plain', 200), (b'error', 'text/plain', 429)]:
            client = HttpClient(self.con, 'kalshi', opener=Replay(Response(body, status, {'Content-Type': content_type})), attempts=1)
            with self.subTest(status=status, size=len(body)), self.assertRaises((ValueError, OSError)):
                client.get_fee_document(FEE_DOCUMENT_URLS['kalshi'][0], SCHEMA)
            self.assertEqual(self.con.execute('SELECT raw_body FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone()[0], body)
        client = HttpClient(self.con, 'kalshi', opener=Replay())
        for url in ('https://polymarket.com/fees', 'https://docs.kalshi.com/other.md', FEE_DOCUMENT_URLS['kalshi'][0] + '?redirect=yes'):
            with self.assertRaises(ValueError): client.get_fee_document(url, SCHEMA)

    def test_export_immutable_sources_no_overwrite_and_offline_cli(self):
        cid = self.run_capture('polymarket_us')
        _, now = self.times('polymarket_us')
        root = self.root / 'review'
        result = export_review(self.con, cid, root, now=now)
        self.assertEqual(result['status'], 'NEEDS_OPERATOR_REVIEW')
        packet = load_json((root / 'review.json').read_bytes())
        for source in packet['sources']:
            self.assertEqual(sha256((root / source['local_path']).read_bytes()).hexdigest(), source['sha256'])
        with self.assertRaises(FileExistsError): export_review(self.con, cid, root, now=now)
        with patch('predarb.research_cli.clock', return_value=now), patch('predarb.runtime.writer_lock', side_effect=AssertionError('reader must not lock')), redirect_stdout(StringIO()):
            self.assertEqual(self.cli(['research', 'fees-review', str(cid), '--db', self.path, '--output', str(self.root / 'cli')]), 0)

    def test_capture_cli_and_unapproved_draft_rejected(self):
        venue = 'polymarket_us'
        source_id = self.fixtures[venue]['request']['source_id']
        captured, now = self.times(venue)
        def replay_capture(con, v, sid, side, *, now):
            return self.run_capture(v)
        with patch('predarb.research_cli.capture', side_effect=replay_capture), patch('predarb.research_cli.clock', return_value=now), redirect_stdout(StringIO()):
            self.assertEqual(self.cli(['research', 'fees-capture', venue, source_id, '--side', 'YES', '--db', self.path, '--output', str(self.root / 'cli')]), 0)
        with redirect_stderr(StringIO()):
            self.assertEqual(self.cli(['research', 'fees-import', str(self.root / 'cli/profile.json'), '--db', self.path]), 1)
        with redirect_stderr(StringIO()):
            self.assertEqual(self.cli(['research', 'fees-capture', venue, source_id, '--side', 'YES', '--db', self.path, '--output', str(self.root / 'cli')]), 1)
