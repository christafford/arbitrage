"""M5R genuine historical quote and visibly hypothetical cash/fee diagnostics."""
from dataclasses import fields, replace
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
import unittest

from predarb.models import AskLevel
from predarb.orderbooks import Book, PriceBand
from predarb.validation import load_json, utc_time
from predarb.viability import Attribution, cause, sensitivity, fee_history
from test_continuous_research import hypothetical
import test_quality_recovery


def genuine():
    fixture=load_json((Path(__file__).parent/'fixtures/m5r-senate-genuine.json').read_bytes())
    row=fixture['row'];books=[]
    for b in row['displayed_books']:
        data={f.name:b[f.name] for f in fields(Book)}
        for key in ('yes_asks','no_asks'):
            data[key]=tuple(AskLevel(D(x['price']),D(x['quantity'])) for x in data[key])
        data['price_bands']=tuple(PriceBand(**{k:D(v) for k,v in x.items()}) for x in data['price_bands'])
        for k in ('quantity_step','minimum_quantity'):data[k]=D(data[k])
        books.append(Book(**data))
    pair=dict(kalshi_id=books[0].source_id,polymarket_us_id=books[1].source_id,
        classification=row['classification'],ordinary_basis=row['ordinary_basis'],residual_risks=row['residual_risks'])
    return utc_time(row['at']),books,pair


class ViabilityTests(unittest.TestCase):
    def setUp(self):self.at,self.books,self.pair=genuine()

    def result(self,**kw):
        return sensitivity(kw.pop('books',self.books),kw.pop('pair',self.pair),
                           at=kw.pop('at',self.at),budget=kw.pop('budget',D(3000)),**kw)

    def test_genuine_senate_fee_break_even_and_unknown_actual(self):
        r=self.result(budget=D(500))
        self.assertEqual(r['gross_optimal_quantity'],D(505))
        self.assertEqual(r['gross_usd'],D('5.05'))
        self.assertEqual(r['combined_fee_break_even_per_unit_usd'],D('.01'))
        self.assertLess(r['cases'][0]['per_level_net_usd'],0)
        self.assertIsNone(r['actual_net_profit_usd'])
        self.assertFalse(r['trading_authorized']);self.assertFalse(r['strict_arbitrage_eligible'])

    def test_all_requested_budgets_cash_caps_and_rounding_bounds(self):
        for budget in map(D,('5','25','100','500','3000')):
            for fraction in (None,D('.5'),D('.75')):
                r=self.result(budget=budget,kalshi_fraction=fraction)
                self.assertLessEqual(sum(r['purchase_per_venue_usd']),budget)
                for case in r['cases']:
                    cash=[x+y for x,y in zip(case['bound_funded_purchase_usd'],case['bound_funded_fees_usd'])]
                    self.assertLessEqual(sum(cash),budget)
                    if fraction is not None:
                        self.assertLessEqual(cash[0],budget*fraction)
                        self.assertLessEqual(cash[1],budget*(1-fraction))
                    self.assertLessEqual(sum(case['per_level_fees_usd']),sum(case['minimum_lot_no_rebate_fee_bound_usd']))
                    self.assertLessEqual(sum(case['one_contract_partition_fees_usd']),sum(case['minimum_lot_no_rebate_fee_bound_usd']))

    def test_split_capital_and_reserve_reduce_deployment(self):
        flexible=self.result();equal=self.result(kalshi_fraction=D('.5'));reserved=self.result(reserve=D(150))
        self.assertLess(equal['gross_optimal_quantity'],flexible['gross_optimal_quantity'])
        self.assertLess(reserved['gross_optimal_quantity'],flexible['gross_optimal_quantity'])
        self.assertLessEqual(sum(reserved['purchase_per_venue_usd']),D(2850))

    def test_november_six_tiers_are_separate_hypothetical_cases(self):
        cases=[self.result(us_coefficient=c)['cases'][0] for c in map(D,('.0695','.075','.085','.095'))]
        self.assertEqual([c['us_coefficient'] for c in cases],list(map(D,('.0695','.075','.085','.095'))))
        self.assertEqual(sorted(c['per_level_net_usd'] for c in cases),[c['per_level_net_usd'] for c in reversed(cases)])
        with self.assertRaises(ValueError):self.result(us_coefficient=D('.05'))

    def test_missing_stale_partial_and_metadata_reject(self):
        for b in [replace(self.books[1],source_ts=None),
                  replace(self.books[1],source_ts=(self.at-timedelta(seconds=3)).isoformat()),
                  replace(self.books[1],metadata_received_at=(self.at-timedelta(seconds=61)).isoformat()),
                  replace(self.books[1],rejections=('PARTIAL_BOOK',))]:
            self.assertEqual(self.result(books=[self.books[0],b])['cases'],[])

    def test_invalid_prices_order_and_quantity_are_rejected(self):
        for p,q in [('1','2'),('NaN','2'),('.74','-1')]:
            with self.assertRaises(ValueError):AskLevel(D(p),D(q))
        for ladder in [(AskLevel(D('.75'),D(2)),AskLevel(D('.74'),D(2))),
                       (AskLevel(D('.74123'),D(2)),)]:
            with self.assertRaises(ValueError):
                self.result(books=[replace(self.books[0],no_asks=ladder),self.books[1]])

    def test_partial_depth_no_spread_and_fractional_lots(self):
        k=replace(self.books[0],no_asks=(AskLevel(D('.74'),D(2)),))
        r=self.result(books=[k,self.books[1]])
        self.assertEqual(r['gross_optimal_quantity'],D(2));self.assertTrue(r['depth_limited'])
        r=self.result(books=[replace(k,no_asks=(AskLevel(D('.9'),D(2)),)),self.books[1]])
        self.assertEqual(r['gross_optimal_quantity'],0)
        self.assertEqual(r['cases'][0]['per_level_net_usd'],0)
        u=replace(self.books[1],quantity_step=D('.01'),minimum_quantity=D('.01'))
        r=self.result(books=[k,u],budget=D('.5'))
        self.assertEqual(r['gross_optimal_quantity'],D('.50'))

    def test_bad_identity_approval_and_cash_inputs_fail(self):
        for kw in [dict(pair=dict(self.pair,classification='STRICT')),
                   dict(pair=dict(self.pair,kalshi_id='wrong')),
                   dict(budget=3000.0),dict(reserve=D(3000)),dict(kalshi_fraction=D(1))]:
            with self.assertRaises(ValueError):self.result(**kw)


class AttributionTests(unittest.TestCase):
    def setUp(self):
        _,self.at,self.books,self.pair=hypothetical()
        self.engine=Attribution(self.pair,self.at.isoformat(),(self.at+timedelta(seconds=10)).isoformat())

    def event(self,channel,kind,offset,book=None,**kw):
        stamp=(self.at+timedelta(seconds=offset)).isoformat()
        self.engine.event(dict(at=stamp,received_at=stamp,channel=channel,kind=kind,**kw),book)

    def test_quiet_books_expire_heartbeats_do_not_refresh(self):
        self.event('kalshi','book',0,self.books[0]);self.event('us_ws','book',0,self.books[1])
        self.event('us_ws','heartbeat',5)
        r=self.engine.report()
        self.assertEqual(r['exclusive_combinations_seconds']['VALID'],D(2))
        self.assertEqual(sum(r['exclusive_combinations_seconds'].values()),D(10))
        self.assertEqual(r['overlapping_category_seconds']['us_source_age'],D(8))
        self.assertEqual(r['sole_category_seconds'].get('us_source_age',0),0)
        self.assertFalse(r['trading_authorized'])

    def test_pending_loss_and_unknown_category_are_not_discarded(self):
        self.event('kalshi','book',0,self.books[0]);self.event('us_ws','book',0,self.books[1])
        self.event('kalshi','pending',1)
        r=self.engine.report()
        self.assertEqual(r['exclusive_combinations_seconds']['VALID'],D(1))
        self.assertEqual(r['sole_category_seconds']['continuity_or_local_barrier'],D(1))
        self.assertEqual(cause('kalshi:UNRECOGNIZED'),'other_fail_closed')
        self.assertEqual(cause('kalshi:UNRECOGNIZED_SOURCE_SCHEMA'),'other_fail_closed')

    def test_late_arrival_and_local_processing_are_separate(self):
        b=replace(self.books[1],received_at=(self.at+timedelta(seconds=3)).isoformat())
        self.event('us_ws','book',4,b)
        r=self.engine.report()['latency_seconds']['us_ws']
        self.assertEqual(r['source_to_receipt']['median'],D(3))
        self.assertEqual(r['receipt_to_available']['median'],D(1))
        self.assertEqual(r['arrival_source_stale'],1)

    def test_regressing_clock_fails(self):
        self.event('us_ws','heartbeat',2)
        with self.assertRaises(ValueError):self.event('us_ws','heartbeat',1)

    def test_genuine_raw_replay_and_attribution_preserve_intervals(self):
        from predarb.quality_capture import replay
        from hashlib import sha256
        source=test_quality_recovery.GenuineEventReplay();source.setUp()
        try:
            before={str(p):sha256(p.read_bytes()).hexdigest() for p in source.root.rglob('*') if p.is_file()}
            f=source.fixture
            engine=Attribution(f['pair'],f['config']['started_at'],f['config']['deadline_at'])
            audit=replay(source.root,f['pair'],f['config'],event_observer=engine.event)
            r=engine.report()
            old=load_json(f['files']['result.json']['body'])
            self.assertEqual(r['strict']['valid_local_market_state_seconds']['us_ws'],D(old['valid_local_market_state_seconds']['us_ws']))
            self.assertEqual(audit['replay'],'PASS')
            # SQLite read-only connections can create WAL/SHM companions; original
            # fixture contents, including each archived raw response, stay intact.
            self.assertEqual(before,{p:sha256(Path(p).read_bytes()).hexdigest() for p in before})
        finally:source.doCleanups()


class HistoricalFeeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=load_json((Path(__file__).parent/'fixtures/m5r-fee-history-genuine.json').read_bytes())
        self.rows=[load_json(r['body']) for r in self.fixture['responses'][:4]]

    def test_genuine_historical_raw_hashes_and_current_parameters(self):
        from hashlib import sha256
        from predarb import kalshi,polymarket_us
        self.assertFalse(self.fixture['hypothetical'])
        for row in self.fixture['responses']:
            self.assertEqual(sha256(row['body'].encode()).hexdigest(),row['sha256'])
            utc_time(row['retrieved_at'])
            if row['kind']=='historical_market':
                adapter=kalshi if row['venue']=='kalshi' else polymarket_us
                adapter.validate_detail(load_json(row['body']))
        for i in range(0,16,4):
            rows=[load_json(r['body']) for r in self.fixture['responses'][i:i+4]]
            result=fee_history(rows[0]['series']['ticker'],rows[1]['event']['event_ticker'],rows)
            self.assertEqual(result['current_parameters']['multiplier'],'1')
            self.assertEqual(result['historical_account_applicability'],'UNKNOWN')
            self.assertFalse(result['empty_history_is_historical_proof'])

    def test_missing_unknown_partial_and_wrong_identity_history_fail(self):
        mutations=[(0,'series','fee_multiplier',None),(0,'series','fee_type','unrecognized'),
                   (1,'event','series_ticker','wrong')]
        for index,container,key,value in mutations:
            rows=deepcopy(self.rows);rows[index][container][key]=value
            with self.assertRaises(ValueError):fee_history('CONTROLS','CONTROLS-2026',rows)
        rows=deepcopy(self.rows);rows[3]['cursor']='remaining'
        with self.assertRaises(ValueError):fee_history('CONTROLS','CONTROLS-2026',rows)
        rows=deepcopy(self.rows);del rows[2]['series_fee_change_arr']
        with self.assertRaises(ValueError):fee_history('CONTROLS','CONTROLS-2026',rows)

    def test_hypothetical_nonempty_changes_duplicates_and_override_pairs(self):
        rows=deepcopy(self.rows)
        change=dict(id='HYPOTHETICAL',series_ticker='CONTROLS',fee_type='quadratic',fee_multiplier=2,
                    scheduled_ts='2026-11-01T00:00:00Z')
        rows[2]['series_fee_change_arr']=[change]
        event=dict(id='HYPOTHETICAL',series_ticker='CONTROLS',event_ticker='CONTROLS-2026',
                   fee_type_override=None,fee_multiplier_override=None,scheduled_ts='2026-11-02T00:00:00Z')
        rows[3]['event_fee_changes']=[event]
        self.assertEqual(len(fee_history('CONTROLS','CONTROLS-2026',rows)['series_changes']),1)
        rows[2]['series_fee_change_arr'].append(change)
        with self.assertRaises(ValueError):fee_history('CONTROLS','CONTROLS-2026',rows)
        rows[2]['series_fee_change_arr'].pop();del event['fee_type_override']
        with self.assertRaises(ValueError):fee_history('CONTROLS','CONTROLS-2026',rows)


if __name__ == '__main__':unittest.main()
