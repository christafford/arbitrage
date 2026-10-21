"""M4 fee examples from official docs; all book/applicability scenarios hypothetical."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D, localcontext
from pathlib import Path
import tempfile
import unittest

from predarb.economics import evaluate, policy
from predarb.fees import fill_fees, model_from_profile, quote_fee_bound
from predarb.models import AskLevel
from predarb.research import archive_replay, replay_books
from predarb.store import connect
from predarb.validation import load_json, utc_time
from helpers import FIXTURES


def case():
    return load_json((FIXTURES / 'm4-hypothetical.json').read_bytes())


class FeeTests(unittest.TestCase):
    def setUp(self):
        self.data = case()
        self.k, self.p = [model_from_profile(row) for row in self.data['fee_profiles']]

    def test_official_kalshi_fractional_cost_rounding_example(self):
        model = replace(self.k, balance_precision=D('.01'))
        result = fill_fees(model, [AskLevel(D('.055'), D('1'))])
        self.assertEqual(result['fills'][0]['raw_fee'], D('.00363825'))
        self.assertEqual(result['fills'][0]['trade_fee'], D('.003639'))
        self.assertEqual(result['fills'][0]['rounding_adjustment'], D('.001361'))
        self.assertEqual(result['total'], D('.005'))
        self.assertEqual(fill_fees(self.k, [AskLevel(D('.055'), D('1'))])['total'], D('.0037'))

    def test_kalshi_per_order_accumulator_rebates_are_capped_nonnegative(self):
        model = replace(self.k, balance_precision=D('.01'))
        result = fill_fees(model, [AskLevel(D('.5'), D('.1'))] * 3)
        self.assertEqual(result['total'], D('.01'))
        self.assertEqual(sum(row['rebate'] for row in result['fills']), D('.02'))
        self.assertTrue(all(row['charge'] >= 0 for row in result['fills']))

    def test_official_us_examples_bankers_ties_and_table_tennis(self):
        for price, expected in (('.10','6.26'),('.65','15.81'),('.30','14.60'),('.90','6.26'),('.50','17.38')):
            with self.subTest(price=price):
                self.assertEqual(fill_fees(self.p,[AskLevel(D(price),D('1000'))])['total'],D(expected))
        data=deepcopy(self.data['fee_profiles'][1]);data['kind']='table_tennis'
        self.assertEqual(fill_fees(model_from_profile(data),[AskLevel(D('.5'),D('1000'))])['total'],D('25'))
        # .0695 * 40 * .5 * .5 = .695, rounded half-even to .70.
        self.assertEqual(fill_fees(self.p,[AskLevel(D('.5'),D('40'))])['total'],D('.70'))

    def test_us_fragmentation_never_exceeds_order_cumulative_cap(self):
        levels=[AskLevel(D('.3'),D('2'))]
        actual=fill_fees(self.p,[AskLevel(D('.3'),D('1'))] * 2)['total']
        self.assertEqual(actual,D('.02'))
        self.assertEqual(quote_fee_bound(self.p,levels,D('1')),D('.03'))
        for model in (self.k,self.p,replace(self.k,balance_precision=D('.01'))):
            for price in ('.011','.3','.555','.99'):
                fills=[AskLevel(D(price),D(q)) for q in ('.01','.02','.17','.8')]
                bound=quote_fee_bound(model,[AskLevel(D(price),D('1'))],D('.01'))
                self.assertGreaterEqual(bound,fill_fees(model,fills)['total'])

    def test_missing_unknown_float_window_and_identity_rejected(self):
        for key,value in (('kind','flat'),('multiplier',1.0),('balance_precision','.001'),('schema','v99')):
            data=deepcopy(self.data['fee_profiles'][0]);data[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):model_from_profile(data)
        now=utc_time(self.data['clock'])
        with self.assertRaises(ValueError):self.k.check(venue='kalshi',source_id='WRONG',side='YES',now=now)
        with self.assertRaises(ValueError):self.k.check(venue='kalshi',source_id=self.k.source_id,side='YES',now=now+timedelta(days=2))
        data=deepcopy(self.data['fee_profiles'][1]);data['effective_from']='2026-10-18T00:00:00Z'
        with self.assertRaises(ValueError):model_from_profile(data)

    def test_settlement_fee_is_explicit_and_included_in_conservative_bound(self):
        data=deepcopy(self.data['fee_profiles'][1])
        del data['settlement_fee_per_contract']
        with self.assertRaises(ValueError):model_from_profile(data)
        data['settlement_fee_per_contract']='.02'
        levels=[AskLevel(D('.5'),D('100'))]
        self.assertEqual(quote_fee_bound(model_from_profile(data),levels,D('1')),D('3.74'))


class EconomicsTests(unittest.TestCase):
    def setUp(self):
        self.data=case();self.now=utc_time(self.data['clock'])
        self.models=[model_from_profile(row) for row in self.data['fee_profiles']]
        with tempfile.TemporaryDirectory() as temp:
            with connect(str(Path(temp)/'isolated.sqlite3')) as con:
                replay_id=archive_replay(con,(FIXTURES/'m4-hypothetical.json').read_bytes(),now=self.now)
                self.books,_=replay_books(con,replay_id,now=self.now)
        self.settlement=['2030-07-04T12:00:00Z']*2

    def evaluate(self,**kwargs):
        return evaluate(kwargs.pop('books',self.books),kwargs.pop('sides',['YES','YES']),self.models,
                        kwargs.pop('settlement',self.settlement),kwargs.pop('config',self.data['policy']),
                        now=kwargs.pop('now',self.now),**kwargs)

    def test_multilevel_fee_reserve_and_high_price_tail_reduce_size(self):
        result=self.evaluate()
        self.assertEqual(result['status'],'MODELED_EDGE')
        best=result['best']
        self.assertEqual(best['contracts'],D('200'))
        self.assertEqual(best['quote_costs'],[D('80'),D('94')])
        self.assertEqual(best['fee_bounds'],[D('4'),D('3.46')])
        self.assertEqual(best['capital_per_venue'],[D('85'),D('98.46')])
        self.assertEqual(best['net_profit_bound'],D('16.54'))
        self.assertIn('SIMULTANEOUS_FULL_FILLS_HYPOTHETICAL',result['assumptions'])
        self.assertFalse(result['trading_authorized'])

    def test_independent_budgets_zero_funding_and_depth_exhaustion(self):
        config=deepcopy(self.data['policy']);config['kalshi_budget']='4.25'
        self.assertEqual(self.evaluate(config=config)['best']['contracts'],D('10'))
        config['kalshi_budget']='0'
        self.assertIsNone(self.evaluate(config=config)['best'])
        config=deepcopy(self.data['policy']);config['max_contracts']='501'
        self.assertTrue(self.evaluate(config=config)['depth_exhausted'])

    def test_lattice_search_is_complete_and_bounded(self):
        config=deepcopy(self.data['policy']);config['max_contracts']='10001'
        with self.assertRaisesRegex(ValueError,'SEARCH_LIMIT'):self.evaluate(config=config)
        config['max_contracts']='.5'
        with self.assertRaises(ValueError):self.evaluate(config=config)
        books=[replace(book,quantity_step=D('.01'),minimum_quantity=D('.01')) for book in self.books]
        result=self.evaluate(books=books,config=config)
        self.assertEqual(result['quantities_tested'],50)

    def test_stale_partial_closed_synthetic_no_unknown_and_bad_policy_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'STALE'):self.evaluate(now=self.now+timedelta(seconds=61))
        with self.assertRaisesRegex(ValueError,'SYNTHETIC'):self.evaluate(sides=['YES','NO'])
        with self.assertRaises(ValueError):self.evaluate(books=[replace(self.books[0],source_ts=None),self.books[1]])
        with self.assertRaises(ValueError):self.evaluate(books=[replace(self.books[0],rejections=('PARTIAL_BOOK',)),self.books[1]])
        with self.assertRaises(ValueError):self.evaluate(settlement=[self.now.isoformat()]*2)
        for key,value in (('max_contracts',1.0),('reserve_per_leg','0'),('kalshi_budget','10001')):
            data=deepcopy(self.data['policy']);data[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):policy(data)

    def test_low_decimal_context_does_not_round_money_and_settlement_days(self):
        expected=self.evaluate()
        with localcontext() as context:
            context.prec=3
            self.assertEqual(self.evaluate(),expected)
        earlier=['2030-01-02T12:00:00Z']*2
        self.assertGreater(self.evaluate(settlement=earlier)['best']['profit_per_capital_day'],
                           expected['best']['profit_per_capital_day'])
