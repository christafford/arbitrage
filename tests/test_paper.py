"""M5 synthetic later-quote comparison, provenance, policy and downside tests."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D, localcontext
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from predarb import cli, registry
from predarb.paper import policy
from predarb.paper_store import archive_ticks, compare, create_intent, report
from predarb.store import connect
from predarb.validation import dumps, load_json
from helpers import FIXTURES
from m5_helpers import seed, ticks


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=str(self.root/'paper.sqlite3')
        self.con=connect(self.path);self.addCleanup(self.con.close)
        self.case,self.now,self.pair,self.session,self.evaluation=seed(self.con,self.root)
        self.scenarios=load_json((FIXTURES/'m5-hypothetical.json').read_bytes())
        self.policy=self.scenarios['policy']
        self.intent=create_intent(self.con,self.evaluation,self.policy,now=self.now)

    def sample(self,index=0,*,change=None,at=None,intent=None):
        value=ticks(self.case,self.scenarios['cases'][index])
        if change:change(value)
        raw=dumps(value).encode()
        observed=archive_ticks(self.con,raw,now=self.now)
        result=compare(self.con,intent or self.intent,tick_input_id=observed,now=at or self.now+timedelta(seconds=2))
        return result,observed,raw

    def test_full_fills_and_explicit_hypothetical_assumptions(self):
        result,_,_=self.sample()
        self.assertEqual(result['status'],'STRESS_MODELED')
        self.assertEqual([leg['filled'] for leg in result['legs']],[D('200'),D('200')])
        self.assertEqual(result['worst_net_bound'],D('16.54'))
        self.assertEqual(result['unhedged_contracts'],0)
        self.assertIn('HYPOTHETICAL_FILLS_FROM_LATER_QUOTES',result['assumptions'])
        self.assertFalse(result['trading_authorized'])

    def test_outage_partial_and_adverse_selection_expose_one_leg_downside(self):
        for index,quantity,loss in ((1,'200','85'),(2,'160','64.69'),(3,'200','85'),(4,'200','85')):
            result,_,_=self.sample(index)
            with self.subTest(index=index):
                self.assertEqual(result['unhedged_contracts'],D(quantity))
                self.assertEqual(result['downside_bound'],D(loss))
                self.assertEqual(result['severity'],'HIGH')
                self.assertIn('UNHEDGED_PAPER_EXPOSURE',result['flags'])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ops_events WHERE action='PAPER_DOWNSIDE_SCENARIO'").fetchone()[0],4)

    def test_cancel_race_hedge_latency_and_cancel_ack_before_samples(self):
        result,_,_=self.sample(5)
        self.assertIn('POSSIBLE_FILL_DURING_CANCEL_ACK_WINDOW',result['flags'])
        self.assertIn('MAX_HEDGE_LATENCY_EXCEEDED',result['flags'])
        self.assertEqual(result['hedge_latency_ms'],1100)
        cancelled,_,_=self.sample(6)
        self.assertTrue(all(row['filled']==0 for row in cancelled['legs']))
        self.assertEqual(cancelled['capital_bound'],0)
        self.assertEqual(cancelled['legs'][0]['reason'],'CANCEL_ACK_ASSUMED_BEFORE_SAMPLE')

    def test_fractional_participation_is_floored_to_lots_and_never_overfills(self):
        config=dict(self.policy,participation='.25')
        intent=create_intent(self.con,self.evaluation,config,now=self.now)
        result,_,_=self.sample(intent=intent)
        self.assertEqual([leg['filled'] for leg in result['legs']],[D('50'),D('50')])
        self.assertEqual(result['worst_net_bound'],D('4.13'))

    def test_later_quotes_required_and_stale_future_partial_off_grid_are_unknown(self):
        mutations=[lambda d:d.update(kalshi_received_at=self.case['clock']),
                   lambda d:d['polymarket_us_rest']['marketData'].update(offers=[]),
                   lambda d:d['polymarket_us_rest']['marketData']['offers'][0]['px'].update(value='.4701'),
                   lambda d:d['polymarket_us_rest']['marketData'].update(transactTime=(self.now+timedelta(seconds=3)).isoformat())]
        for mutate in mutations:
            result,observed,raw=self.sample(change=mutate)
            self.assertEqual(result['status'],'UNOBSERVABLE')
            self.assertTrue(result['fills_unknown'])
            self.assertEqual(self.con.execute('SELECT raw_bytes FROM paper_tick_inputs WHERE id=?',(observed,)).fetchone()[0],raw)
        self.assertEqual(self.sample(at=self.now+timedelta(seconds=61))[0]['status'],'UNOBSERVABLE')

    def test_revocation_and_expiry_block_comparison_without_simulated_fills(self):
        registry.decide(self.con,self.pair,'REVOKED','HYPOTHETICAL reviewer','withdrawn',now=self.now)
        with patch('predarb.paper_store.simulate',side_effect=AssertionError('must not simulate')):
            self.assertEqual(self.sample()[0]['status'],'UNOBSERVABLE')
        with self.assertRaises(ValueError):create_intent(self.con,self.evaluation,self.policy,now=self.now)

    def test_retained_intent_survives_m4_detail_pruning_and_is_not_a_live_position(self):
        self.con.execute('DELETE FROM research_details');self.con.commit()
        self.assertEqual(self.sample()[0]['status'],'STRESS_MODELED')
        summary=report(self.con)
        self.assertFalse(summary['multiweek_acceptance'])
        self.assertTrue(summary['independent_scenarios_not_realized_pnl'])
        self.assertEqual(summary['total_intents'],1)

    def test_idempotent_same_inputs_immutability_and_mode_guards(self):
        self.assertEqual(create_intent(self.con,self.evaluation,self.policy,now=self.now),self.intent)
        first,observed,_=self.sample()
        again=compare(self.con,self.intent,tick_input_id=observed,now=self.now+timedelta(seconds=2))
        self.assertEqual(first['comparison_id'],again['comparison_id'])
        self.con.execute("INSERT INTO ops_events(ts_utc,severity,action,detail_json) VALUES(?,'INFO','HYPOTHETICAL_TEST','{}')",(self.now.isoformat(),));self.con.commit()
        for table in ('paper_tick_inputs','paper_intents','paper_comparisons','ops_events'):
            with self.subTest(table=table),self.assertRaises(sqlite3.IntegrityError):self.con.execute('DELETE FROM '+table)
            self.con.rollback()
        with self.assertRaises(ValueError):compare(self.con,self.intent,now=self.now)
        with self.assertRaises(ValueError):create_intent(self.con,999,self.policy,now=self.now)
        with self.assertRaises(ValueError):create_intent(self.con,self.evaluation,self.policy,now=self.now-timedelta(seconds=1))

    def test_invalid_policy_inputs_and_low_decimal_context(self):
        for key,value in (('participation','0'),('participation',.5),('max_hedge_latency_ms',True),('cancel_ack_delay_ms',60001),('max_price_drift','NaN')):
            with self.subTest(key=key),self.assertRaises(ValueError):policy(dict(self.policy,**{key:value}))
        with localcontext() as context:
            context.prec=3
            self.assertEqual(self.sample()[0]['worst_net_bound'],D('16.54'))

    def test_tampered_m4_details_do_not_create_another_intent(self):
        self.con.execute('UPDATE research_details SET detail_json=? WHERE evaluation_id=?',('{}',self.evaluation));self.con.commit()
        with self.assertRaisesRegex(ValueError,'hash'):create_intent(self.con,self.evaluation,self.policy,now=self.now)

    def test_expired_pair_and_live_contamination_leave_fills_unknown(self):
        result,_,_=self.sample(at=self.now+timedelta(hours=2))
        self.assertEqual(result['status'],'UNOBSERVABLE')
        self.assertFalse(result['current_loss_bound_known'])
        self.assertEqual(result['potential_unhedged_contracts'],'200')
        from predarb.store import save_raw
        save_raw(self.con,'kalshi','https://example.invalid/HYPOTHETICAL-contamination',{'hypothetical':True})
        with self.assertRaises(ValueError):archive_ticks(self.con,b'{}',now=self.now)

    def test_malformed_tick_envelopes_fail_as_unknown_and_preserve_bytes(self):
        broken=ticks(self.case,self.scenarios['cases'][0]);broken['kalshi_metadata']=None
        for raw in (b'null',b'[]',dumps(broken).encode()):
            observed=archive_ticks(self.con,raw,now=self.now)
            self.assertEqual(compare(self.con,self.intent,tick_input_id=observed,now=self.now+timedelta(seconds=2))['status'],'UNOBSERVABLE')
        with self.assertRaises(ValueError):policy(None)

    def test_cli_report_and_missing_later_ticks_exit_code(self):
        def invoke(*args):
            out,err=StringIO(),StringIO()
            with patch('sys.argv',['predarb','paper',*args,'--db',self.path]),redirect_stdout(out),redirect_stderr(err):code=cli.main()
            return code,out.getvalue(),err.getvalue()
        self.assertEqual(invoke('report')[0],0)
        self.assertEqual(invoke('report','--limit','0')[0],1)
        self.assertEqual(invoke('compare',str(self.intent),'--tick-input','999','--at',self.now.isoformat())[0],2)
        self.assertNotIn('Traceback',invoke('compare','999')[2])
