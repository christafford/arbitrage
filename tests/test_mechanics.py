"""M5A D: all reviews, balances, payouts and delayed cash flows are HYPOTHETICAL."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D, localcontext
from hashlib import sha256
from io import StringIO
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from predarb import cli, mechanics, registry as r
from predarb.economics import evaluate
from predarb.fee_store import import_profile
from predarb.fees import model_from_profile
from predarb.models import AskLevel
from predarb.paper import simulate
from predarb.paper_store import create_intent, compare, archive_ticks
from predarb.research import archive_replay, replay_books, scan_once, start_session
from predarb.store import connect
from predarb.validation import load_json, dumps, utc_time
from helpers import FIXTURES
from m5_helpers import ticks


class MechanicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = str(self.root / 'HYPOTHETICAL.sqlite3')
        self.con = connect(self.path); self.addCleanup(self.con.close)
        raw = (FIXTURES / 'm4-hypothetical.json').read_bytes()
        self.data = load_json(raw); self.now = utc_time(self.data['clock'])
        r.load_hypothetical(self.con, self.data['registry'], now=self.now)
        self.pair = r.propose(self.con, 'HYPOTHETICAL-K', 'HYPOTHETICAL-P', 'HYPOTHETICAL proposer', now=self.now)
        self.bundle = r.review(self.con, self.pair, now=self.now)
        self.form = load_json((FIXTURES / 'm5d-hypothetical.json').read_bytes())['review']
        self.form.update(pair_id=self.pair, evidence_sha256=self.bundle['evidence_sha256'])
        self.replay = archive_replay(self.con, raw, now=self.now)
        self.books, _ = replay_books(self.con, self.replay, now=self.now)
        self.models = [model_from_profile(row) for row in self.data['fee_profiles']]
        self.settlement = [max((row[v + '_settlement_at'] for row in self.form['settlement_scenarios']), key=utc_time) for v in mechanics.VENUES]

    def evaluate(self, *, scenarios=True, books=None, config=None, now=None):
        return evaluate(books or self.books, ['YES', 'YES'], self.models, self.settlement, config or self.data['policy'],
                        now=now or self.now, payout_scenarios=self.form['settlement_scenarios'] if scenarios else None)

    def seed_scan(self):
        r.approve(self.con, self.pair, self.form, human_attested=True, now=self.now)
        (self.root / 'HYPOTHETICAL-fees.txt').write_text('HYPOTHETICAL fee source')
        for profile in self.data['fee_profiles']:
            import_profile(self.con, dumps(profile).encode(), base=self.root, now=self.now, attested=True)
        session = start_session(self.con, self.data['policy'], now=self.now, hypothetical=True)
        result = scan_once(self.con, session, now=self.now, replay_id=self.replay)
        self.assertEqual(result['modeled_edges'], 1)
        return self.con.execute('SELECT id FROM research_evaluations').fetchone()[0]

    def test_official_document_fixture_hashes_provenance_and_us_only(self):
        data = load_json((FIXTURES / 'm5d-us-documents-live.json').read_bytes())
        self.assertIn('REAL_OFFICIAL_US', data['provenance'])
        for source in data['sources']:
            self.assertTrue(source['url'].startswith('https://docs.polymarket.us/'))
            self.assertEqual(source['body_sha256'], sha256(source['body'].encode()).hexdigest())
            self.assertEqual(source['schema_version'], 'official-mechanics-documents/m5a-d-v1')
            self.assertNotIn('set-cookie', source['headers'])
            utc_time(source['retrieved_at'])

    def test_explicit_source_bound_review_approval_and_cash_timing(self):
        result = r.approve(self.con, self.pair, self.form, human_attested=True, now=self.now)
        assessment = result['mechanics_assessment']
        self.assertEqual(assessment['status'], 'REVIEWED_RESEARCH_ONLY')
        self.assertEqual(assessment['latest_cash_available_at'], ['2030-07-05T12:00:00+00:00', '2030-07-07T12:00:00+00:00'])
        self.assertFalse(result['trading_authorized'])
        with self.assertRaisesRegex(ValueError, 'attest'):
            # No human attestation -> no new approval, even with complete mechanics.
            r._validate_review(dict(self.form, human_reviewed=False), self.pair, self.bundle, self.now)

    def test_missing_schema_attestation_unknown_currency_notional_collateral_and_funding(self):
        mutations = [lambda f: f.pop('mechanics'),
                     lambda f: f['mechanics'].update(schema='unknown'),
                     lambda f: f['mechanics'].update(reviewed=False),
                     lambda f: f['mechanics'].update(netting='PORTFOLIO_OFFSETS'),
                     lambda f: f['mechanics'].update(funding='REUSE_PROCEEDS'),
                     lambda f: f['mechanics'].update(timing_basis='VENUE_GUARANTEED'),
                     lambda f: f['mechanics']['venues']['kalshi'].update(currency='EUR'),
                     lambda f: f['mechanics']['venues']['kalshi'].update(notional='10'),
                     lambda f: f['mechanics']['venues']['kalshi'].update(additional_collateral_per_contract='1'),
                     lambda f: f['mechanics']['venues']['kalshi'].update(notional=1.0)]
        for mutation in mutations:
            form = deepcopy(self.form); mutation(form)
            with self.subTest(form=form.get('mechanics')), self.assertRaises(ValueError):
                mechanics.validate_review(form, self.bundle, now=self.now)

    def test_source_roles_missing_foreign_hash_duplicates_stale_and_future(self):
        for mode in ('missing', 'foreign', 'duplicate', 'stale', 'future'):
            form, bundle = deepcopy(self.form), deepcopy(self.bundle)
            docs = form['mechanics']['venues']['kalshi']['documents']
            if mode == 'missing': docs['collateral'] = []
            if mode == 'foreign': docs['payout_rules'] = ['0' * 64]
            if mode == 'duplicate': docs['settlement_timing'] *= 2
            if mode in {'stale', 'future'}:
                bundle['instruments'][0]['documents'][0]['retrieved_at'] = (self.now + timedelta(hours=-25 if mode == 'stale' else 1)).isoformat()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                mechanics.validate_review(form, bundle, now=self.now)

    def test_cash_time_missing_naive_before_settlement_past_and_unbounded(self):
        for value in (None, '2030-07-04T13:00:00', '2030-07-04T11:00:00Z', '2029-01-01T00:00:00Z', '9999-01-01T00:00:00Z'):
            form = deepcopy(self.form)
            form['settlement_scenarios'][0]['kalshi_cash_available_at'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                mechanics.validate_review(form, self.bundle, now=self.now)
        scenarios = deepcopy(self.form['settlement_scenarios']); scenarios.pop()
        with self.assertRaises(ValueError): mechanics.scenario_terms(scenarios, now=self.now)

    def test_unknown_payout_and_noncomplementary_exception_never_assume_one_dollar(self):
        for value in ('UNKNOWN', '-.1', '1.1', 0.5, '.4'):
            form = deepcopy(self.form); form['settlement_scenarios'][2]['kalshi_payout'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                mechanics.scenario_terms(form['settlement_scenarios'], now=self.now)
        form = deepcopy(self.form); form['settlement_scenarios'][0]['case'] = 'UNKNOWN'
        with self.assertRaises(ValueError): mechanics.scenario_terms(form['settlement_scenarios'], now=self.now)

    def test_normal_payout_must_match_selected_legs_even_when_total_is_one(self):
        form = deepcopy(self.form)
        form['settlement_scenarios'][0].update(kalshi_payout='0', polymarket_us_payout='1')
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            mechanics.validate_review(form, self.bundle, now=self.now)
        form = deepcopy(self.form); form['outcome_mapping']['YES'] = 'YES'
        with self.assertRaisesRegex(ValueError, 'bijective'):
            mechanics.validate_review(form, self.bundle, now=self.now)

    def test_economics_cashflows_no_double_collateral_and_delayed_capital_days(self):
        result = self.evaluate(); legacy = self.evaluate(scenarios=False)
        best = result['best']; old = legacy['best']
        self.assertEqual(best['net_profit_bound'], D('16.54'))
        self.assertEqual(best['total_capital'], D('183.46'))
        self.assertEqual(best['locked_capital_days'] - old['locked_capital_days'], D('85') + D('98.46') * 3)
        self.assertEqual(best['payout_bound'], D('200'))
        self.assertTrue(all(row['total_payout'] == D('200') for row in best['settlement_cashflows']))
        self.assertEqual([row['research_cash_required'] for row in best['funding']], [D('85'), D('98.46')])
        self.assertTrue(all(row['additional_collateral'] == 0 and row['sale_proceeds'] == 0 for row in best['funding']))
        self.assertEqual(result['cash_timing_basis'], 'OPERATOR_CONSERVATIVE_ASSUMPTION')
        self.assertFalse(result['trading_authorized'])
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(self.evaluate(), result)

    def test_unknown_book_mechanism_and_us_short_rejected_in_all_routes(self):
        for venue, side in (('polymarket_us', 'NO'), ('other', 'YES'), ('kalshi', 'OTHER')):
            with self.subTest(venue=venue), self.assertRaises(ValueError): mechanics.route(venue, side)
        self.assertEqual(mechanics.route('kalshi', 'NO'), 'BUY_NO_FROM_COMPLEMENTARY_YES_BID')
        with self.assertRaisesRegex(ValueError, 'MECHANISM_MISMATCH'):
            self.evaluate(books=[replace(self.books[0], mechanism_yes='UNKNOWN'), self.books[1]])
        form = deepcopy(self.form); form['legs']['polymarket_us'] = 'NO'
        with self.assertRaisesRegex(ValueError, 'SYNTHETIC_US_NO'):
            mechanics.validate_review(form, self.bundle, now=self.now)

    def test_fractional_payouts_skip_unknown_rounding_but_search_valid_larger_quantity(self):
        books = [replace(b, quantity_step=D('.01'), minimum_quantity=D('.01')) for b in self.books]
        config = dict(self.data['policy'], max_contracts='.03', reserve_per_leg='.001', min_profit='0')
        result = self.evaluate(books=books, config=config)
        self.assertEqual(result['quantities_tested'], 3)
        self.assertEqual(result['payout_grid_rejections'], 2)
        self.assertEqual(result['best']['contracts'], D('.02'))
        # .01 * .50 would need unknown half-cent rounding; .02 * .50 is exact.
        flows = mechanics.payout_cashflows(self.form['settlement_scenarios'], [D('.02'), D('.02')])
        self.assertEqual(flows[2]['total_payout'], D('.02'))
        with self.assertRaisesRegex(ValueError, 'PRECISION'):
            mechanics.payout_cashflows(self.form['settlement_scenarios'], [D('.01'), D('.02')])
        result = self.evaluate(books=books, config=dict(config, max_contracts='.01'))
        self.assertIsNone(result['best']); self.assertIn('PAYOUT_PRECISION_UNVERIFIED', result['rejections'])

    def test_stale_books_partial_depth_zero_budget_and_invalid_price_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.evaluate(now=self.now + timedelta(seconds=61))
        self.assertTrue(self.evaluate(config=dict(self.data['policy'], max_contracts='501'))['depth_exhausted'])
        self.assertIsNone(self.evaluate(config=dict(self.data['policy'], kalshi_budget='0'))['best'])
        with self.assertRaises(ValueError): mechanics.capital(self.books[0], 'YES', D('-1'), D('0'), D('0'))
        bad = deepcopy(self.data); bad['polymarket_us_rest']['marketData']['offers'][0]['px']['value'] = '1.1'
        rid = archive_replay(self.con, dumps(bad).encode(), now=self.now)
        invalid, _ = replay_books(self.con, rid, now=self.now)
        self.assertTrue(invalid[1].issues(now=self.now))
        with self.assertRaisesRegex(ValueError, 'BOOK_REJECTED'): self.evaluate(books=invalid)

    def test_real_identity_requires_cashflow_input_and_matching_settlement_window(self):
        books = [replace(b, source_id='REAL-' + b.source_id) for b in self.books]
        with self.assertRaisesRegex(ValueError, 'MECHANICS_REVIEW_REQUIRED'): self.evaluate(books=books, scenarios=False)
        with self.assertRaisesRegex(ValueError, 'MISMATCH'):
            evaluate(self.books, ['YES', 'YES'], self.models, ['2030-07-05T12:00:00Z'] * 2, self.data['policy'],
                     now=self.now, payout_scenarios=self.form['settlement_scenarios'])

    def test_scanner_records_reviewed_cashflows_and_delayed_capital(self):
        evaluation = self.seed_scan()
        detail = load_json(self.con.execute('SELECT detail_json FROM research_details WHERE evaluation_id=?', (evaluation,)).fetchone()[0])
        self.assertEqual(detail['mechanics']['status'], 'REVIEWED_RESEARCH_ONLY')
        self.assertEqual(detail['economics']['best']['cash_available_at'][1], '2030-07-07T12:00:00+00:00')
        self.assertEqual(len(detail['economics']['best']['settlement_cashflows']), 6)

    def test_paper_unequal_fill_cashflows_do_not_invent_full_pair_payout(self):
        evaluation = self.seed_scan()
        paper = load_json((FIXTURES / 'm5-hypothetical.json').read_bytes())
        intent = create_intent(self.con, evaluation, paper['policy'], now=self.now)
        value = ticks(self.data, paper['cases'][2])
        observed = archive_ticks(self.con, dumps(value).encode(), now=self.now)
        result = compare(self.con, intent, tick_input_id=observed, now=self.now + timedelta(seconds=2))
        self.assertEqual(result['status'], 'STRESS_MODELED')
        self.assertEqual(result['unhedged_contracts'], D('160'))
        self.assertEqual(result['worst_reviewed_payout'], D('40'))
        self.assertEqual(result['downside_bound'], D('64.69'))
        self.assertEqual(min(row['total_payout'] for row in result['settlement_cashflows']), D('40'))
        self.assertEqual(sum(row['research_cash_required'] for row in result['funding']), result['capital_bound'])

    def test_paper_unknown_mechanism_and_fractional_partial_payout_are_unobservable(self):
        initial = [replace(b, quantity_step=D('.01'), minimum_quantity=D('.01'),
                           yes_asks=(AskLevel(b.yes_asks[0].price, D('.02')),)) for b in self.books]
        later = [replace(b, received_at=(self.now + timedelta(milliseconds=100)).isoformat(),
                         source_ts=(self.now + timedelta(milliseconds=100)).isoformat()) for b in initial]
        config = load_json((FIXTURES / 'm5-hypothetical.json').read_bytes())['policy']
        kwargs = dict(created_at=self.now.isoformat(), now=self.now + timedelta(seconds=1), reserve_per_leg=D('.001'))
        bad = [replace(later[0], mechanism_yes='UNKNOWN'), later[1]]
        with self.assertRaisesRegex(ValueError, 'MECHANISM_MISMATCH'):
            simulate(initial, bad, self.models, ['YES', 'YES'], D('.02'), self.form, config, **kwargs)
        partial = [replace(later[0], yes_asks=(AskLevel(later[0].yes_asks[0].price, D('.01')),)), later[1]]
        with self.assertRaisesRegex(ValueError, 'PAYOUT_PRECISION_UNVERIFIED'):
            simulate(initial, partial, self.models, ['YES', 'YES'], D('.02'), self.form, config, **kwargs)

    def test_corrupt_document_bytes_and_changed_sources_invalidate_review(self):
        r.approve(self.con, self.pair, self.form, human_attested=True, now=self.now)
        head = self.bundle['instruments'][0]; doc = head['documents'][0]
        r.import_document(self.con, 'kalshi', 'HYPOTHETICAL-K', doc['source_url'], b'HYPOTHETICAL changed mechanics',
                          b'HYPOTHETICAL changed mechanics', self.now.isoformat(), 'HYPOTHETICAL reviewer', now=self.now)
        self.assertEqual(r.review(self.con, self.pair, now=self.now)['status'], 'INVALIDATED')
        self.con.execute('DROP TRIGGER rule_documents_no_update')
        self.con.execute("UPDATE rule_documents SET raw_bytes=x'00'")
        with self.assertRaisesRegex(ValueError, 'provenance'): r.review(self.con, self.pair, now=self.now)

    def test_live_legacy_review_invalidates_without_automatic_reapproval(self):
        legacy = deepcopy(self.form); legacy.pop('mechanics')
        r.approve(self.con, self.pair, legacy, human_attested=True, now=self.now)
        # Isolated simulation of pre-D live registry state, no real approval created.
        bundle = {key: deepcopy(self.bundle[key]) for key in ('instruments', 'evidence_sha256')}
        bundle['hypothetical'] = False
        with patch('predarb.registry._bundle', return_value=bundle), patch('predarb.registry._live_reason', return_value=None):
            result = r.review(self.con, self.pair, now=self.now)
        self.assertEqual(result['status'], 'INVALIDATED')
        self.assertEqual(result['mechanics_assessment']['status'], 'UNVERIFIED')
        self.assertIn('mechanics', result['reason'])

    def test_live_template_is_unapproved_and_sources_require_human_role_assignment(self):
        bundle = {key: deepcopy(self.bundle[key]) for key in ('instruments', 'evidence_sha256')}
        bundle['hypothetical'] = False
        with patch('predarb.registry._bundle', return_value=bundle):
            form = r.review_template(self.con, self.pair, now=self.now)
        self.assertFalse(form['mechanics']['reviewed'])
        self.assertEqual(form['mechanics']['venues']['kalshi']['documents']['collateral'], [])
        self.assertFalse(form['human_reviewed'])
        live = deepcopy(self.form); live['hypothetical'] = False; live.pop('mechanics')
        with self.assertRaisesRegex(ValueError, 'mechanics'):
            r._validate_review(live, self.pair, bundle, self.now)

    def test_cli_review_exposes_mechanics_without_approving_pair(self):
        out = StringIO()
        with patch('sys.argv', ['predarb', 'pairs', 'review', str(self.pair), '--db', self.path]), patch('predarb.registry.now_utc', return_value=self.now), redirect_stdout(out):
            self.assertEqual(cli.main(), 0)
        result = load_json(out.getvalue())
        self.assertEqual(result['mechanics_assessment']['status'], 'UNVERIFIED')
        self.assertEqual(result['status'], 'UNVERIFIED')

    def test_isolated_demo_cli_includes_cash_timing_and_preserves_fixture_bytes(self):
        root = self.root / 'demo'
        command = [sys.executable, 'scripts/m4_demo.py', '--output', str(root),
                   '--mechanics-fixture', str(FIXTURES / 'm5d-hypothetical.json')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = load_json(result.stdout)
        self.assertTrue(data['hypothetical'])
        self.assertEqual(data['favorable_sample']['cash_available_at'][1], '2030-07-07T12:00:00+00:00')
        self.assertEqual(data['cycles'][-1]['rejected'], 1)
        self.assertEqual((root / 'mechanics-input.json').read_bytes(), (FIXTURES / 'm5d-hypothetical.json').read_bytes())
        failed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(failed.returncode, 0)
