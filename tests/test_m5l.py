"""M5L planner failures, real-source replay and explicitly hypothetical workers."""
from contextlib import closing
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from predarb import backfill as b,semantic as s,embeddings as e,registry,kalshi,polymarket_us
from predarb.store import connect
from predarb.validation import load_json,dumps
from test_embeddings import bm,DATA,NOW

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import m5l_benchmark as bench
import m5l_economics as econ


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.source=connect(str(root/'source.sqlite3'));self.index=connect(str(root/'index.sqlite3'))
        self.plan=sqlite3.connect(root/'schedule.sqlite3')
        for con in (self.source,self.index,self.plan):self.addCleanup(con.close)
        bm.seed(self.source,DATA);s.sync(self.source,self.index,now=NOW)
        self.service=bm.HypotheticalService(deepcopy(DATA))
        self.client=e.Client(self.index,e.Config('https://HYPOTHETICAL.ts.net',batch_size=2,retries=0),opener=self.service,clock=lambda:NOW.timestamp(),sleep=lambda _:None)
        self.client.probe();s.set_state(self.index,'active_identity',self.client.identity);self.index.commit()
        self.report=b.refresh(self.source,self.index,self.plan,now=NOW)
    def test_source_preserved_and_unknowns_reported(self):
        before=list(self.source.iterdump());report=b.refresh(self.source,self.index,self.plan,now=NOW)
        self.assertEqual(before,list(self.source.iterdump()))
        self.assertEqual(report['counts']['current_eligible'],15)
        self.assertTrue(all(g['activity']=='UNKNOWN' for g in report['groups']))
        self.assertEqual(report['capital_release_coverage'],'UNKNOWN')
    def test_priority_requires_activity_and_fresh_depth(self):
        args=dict(event_date=NOW.date().isoformat(),activity_status='POSITIVE_REPORTED_24H_VOLUME',now=NOW)
        self.assertEqual(b.priority(**args,liquidity={'quality':'FRESH','depth_proxy':'4.1'}),0)
        for quality,amount in [('STALE','4.1'),('FRESH','0'),('FRESH',None),('UNKNOWN_SOURCE_TIME','4.1')]:
            self.assertEqual(b.priority(**args,liquidity={'quality':quality,'depth_proxy':amount}),1)
        self.assertGreater(b.priority(**dict(args,event_date=None),liquidity={'quality':'FRESH','depth_proxy':'4.1'}),0)
    def test_activity_missing_invalid_and_exact(self):
        self.assertEqual(b.activity('kalshi',{})['status'],'UNKNOWN')
        self.assertEqual(b.activity('polymarket_us',{'volume24hr':None})['status'],'UNKNOWN')
        self.assertEqual(b.activity('kalshi',{'volume_24h_fp':'0'})['status'],'ZERO_REPORTED_24H_VOLUME')
        self.assertEqual(b.activity('polymarket_us',{'volume24hr':Decimal('1.01')})['value'],'1.01')
        for venue,contract in [('kalshi',{'volume_24h_fp':True}),('kalshi',{'volume_24h_fp':'NaN'}),('kalshi',{'volume_24h_fp':'-1'}),('polymarket_us',{'volume24hr':'1'}),('polymarket_us',{'volume24hr':1.0})]:
            with self.assertRaises(ValueError):b.activity(venue,contract)
    def test_three_priority_one_fair_and_no_ack_on_failure(self):
        ordered=list(self.plan.execute("SELECT source_id FROM backfill_tasks WHERE venue='kalshi' ORDER BY shuffle"))
        low=ordered[0][0]
        self.plan.execute("UPDATE backfill_tasks SET tier=0 WHERE venue='kalshi'")
        self.plan.execute('UPDATE backfill_tasks SET tier=5 WHERE source_id=?',(low,));self.plan.commit()
        selected,token=b.select(self.source,self.index,self.plan,'kalshi',4,now=NOW)
        self.assertNotIn(low,[x['source_id'] for x in selected[:3]])
        self.assertEqual(selected[3]['source_id'],low)
        self.assertEqual(token['fair_slots'],[False,False,False,True])
        self.assertEqual(token,b.select(self.source,self.index,self.plan,'kalshi',4,now=NOW)[1])
        with self.assertRaisesRegex(ValueError,'not committed'):b.acknowledge(self.index,self.plan,token,now=NOW)
        self.assertIsNone(b.state(self.plan,'progress:kalshi'))
    def test_worker_integration_commit_resume_no_duplicates(self):
        scheduler=b.Scheduler(self.source,self.index,self.plan)
        result=s.index_batch(self.index,self.client,now=NOW,expected_identity=self.client.identity,
            scheduler=scheduler,budgets={'kalshi':4,'polymarket_us':4},texts_per_second=100)
        self.assertEqual(result['status'],'READY');self.assertEqual(result['completed'],{'kalshi':4,'polymarket_us':4})
        self.assertEqual(b.state(self.plan,'progress:kalshi')['slot'],4)
        selected,_=scheduler.select('kalshi',64,now=NOW)
        self.assertTrue(all(not self.index.execute('SELECT 1 FROM semantic_vectors WHERE content_hash=?',(d['content_hash'],)).fetchone() for d in selected))
    def test_worker_requires_pin_without_modifying_namespace(self):
        with self.assertRaisesRegex(ValueError,'exact namespace'):
            s.index_batch(self.index,self.client,now=NOW,scheduler=b.Scheduler(self.source,self.index,self.plan))
        self.assertEqual(s.state(self.index,'active_identity'),self.client.identity)
    def test_stale_plan_and_source_changed_are_excluded(self):
        with self.assertRaisesRegex(ValueError,'stale scheduler'):b.select(self.source,self.index,self.plan,'kalshi',1,now=NOW+timedelta(days=2))
        chosen,_=b.select(self.source,self.index,self.plan,'kalshi',1,now=NOW)
        sid=chosen[0]['source_id'];head=registry._instrument(self.source,'kalshi',sid)
        contract=load_json(head['evidence_json'])['contract']
        registry._record_instrument(self.source,'kalshi',sid,dict(contract,title='HYPOTHETICAL changed'),observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        remaining,_=b.select(self.source,self.index,self.plan,'kalshi',64,now=NOW)
        self.assertNotIn(sid,[r['source_id'] for r in remaining])
    def test_wrong_namespace_and_schema_fail(self):
        s.set_state(self.index,'active_identity','f'*64);self.index.commit()
        with self.assertRaisesRegex(ValueError,'binding'):b.select(self.source,self.index,self.plan,'kalshi',1,now=NOW)
        s.set_state(self.index,'schema','HYPOTHETICAL-UNKNOWN');self.index.commit()
        with self.assertRaisesRegex(ValueError,'semantic schema'):b.initialize(self.plan,self.source,self.index)
    def test_depth_bonus_expires_without_renewing_evidence(self):
        ids=[x[0] for x in self.plan.execute("SELECT source_id FROM backfill_tasks WHERE venue='kalshi' ORDER BY shuffle")]
        self.plan.execute("UPDATE backfill_tasks SET tier=5 WHERE venue='kalshi'")
        for sid,age in [(ids[0],120),(ids[1],0)]:
            evidence={'event_date':NOW.date().isoformat(),'activity':{'status':'POSITIVE_REPORTED_24H_VOLUME'},
                'liquidity':{'quality':'FRESH','depth_proxy':'10','source_ts':(NOW-timedelta(seconds=age)).isoformat(),'received_at':(NOW-timedelta(seconds=age)).isoformat()}}
            self.plan.execute('UPDATE backfill_tasks SET tier=0,evidence_json=? WHERE source_id=?',(dumps(evidence),sid))
        self.plan.commit()
        selected,_=b.select(self.source,self.index,self.plan,'kalshi',1,now=NOW)
        self.assertEqual(selected[0]['source_id'],ids[1])
        old=json.loads(self.plan.execute('SELECT evidence_json FROM backfill_tasks WHERE source_id=?',(ids[0],)).fetchone()[0])
        self.assertEqual(old['liquidity']['source_ts'],(NOW-timedelta(seconds=120)).isoformat())
    def test_bounds_and_separate_archive(self):
        for count in (0,65,True):
            with self.assertRaises(ValueError):b.select(self.source,self.index,self.plan,'kalshi',count,now=NOW)
        with self.assertRaisesRegex(ValueError,'separate'):b.initialize(self.index,self.source,self.index)


class M5LReplayTests(unittest.TestCase):
    def test_genuine_metadata_books_and_activity_replay(self):
        fixture=json.loads((ROOT/'tests/fixtures/m5l-public-live.json').read_text())
        self.assertFalse(fixture['hypothetical']);counts={}
        for r in fixture['responses']:
            self.assertEqual(hashlib.sha256(r['body'].encode()).hexdigest(),r['body_sha256'])
            data=load_json(r['body']);adapter=kalshi if r['venue']=='kalshi' else polymarket_us
            if r['schema_version']==adapter.SCHEMA_VERSION:
                if 'market' in data:
                    adapter.validate_detail(data);b.activity(r['venue'],data['market'])
                else:adapter.validate_book(data)
            else:
                self.assertEqual(r['schema_version'],'kalshi-ws/m5a-v1')
                self.assertIn('clock',data['msg']);self.assertIn('seq',data)
            counts[r['capture']]=counts.get(r['capture'],0)+1
        self.assertEqual(len(counts),2);self.assertTrue(all(n>=5 for n in counts.values()))
    def test_invalid_price_missing_fields_and_stale_live_book(self):
        fixture=json.loads((ROOT/'tests/fixtures/m5l-public-live.json').read_text())
        r=next(x for x in fixture['responses'] if '/book' in x['endpoint']);data=load_json(r['body'])
        altered=deepcopy(data);del altered['marketData']['offers']
        with self.assertRaises(ValueError):polymarket_us.validate_book(altered)
        altered=deepcopy(data);altered['marketData']['offers'][0]['px']['value']='1.1'
        with self.assertRaises(ValueError):polymarket_us.validate_book(altered)
        from predarb.collector import book_freshness
        stamp=data['marketData']['transactTime']
        self.assertEqual(book_freshness(stamp,r['ts_utc'],now=utc_time(r['ts_utc'])+timedelta(days=1)), 'STALE_RECEIPT')
    def test_capital_unknown_not_zero_and_no_gate_bypass(self):
        rows=econ.blocked_capital(['SETTLEMENT_UNVERIFIED','STALE_SOURCE'])
        self.assertEqual([x['combined_capital_usd'] for x in rows],['5','25','100','500'])
        self.assertTrue(all(x['net_return_usd'] is None and x['feasible_quantity'] is None for x in rows))
        with self.assertRaises(ValueError):econ.blocked_capital([])
    def test_benchmark_same_definitions_query_only_instruction(self):
        corpus=bench.corpus64();a=bench.texts_for(corpus,'existing');z=bench.texts_for(corpus,'instruction')
        self.assertEqual(len(a),64)
        for r,x,y in zip(corpus['instruments'],a,z):
            if r['venue']=='kalshi':self.assertEqual(x,y)
            else:self.assertTrue(y.startswith('Instruct: '));self.assertTrue(y.endswith(x))
        with self.assertRaises(ValueError):bench.texts_for(corpus,'unknown')
    def test_exact_probe_rejects_all_three_mismatches(self):
        class HypotheticalClient:
            def probe(self):self.identity='0'*64;return {'identity':self.identity}
        with self.assertRaisesRegex(e.EmbeddingError,'PINNED_MODEL'):bench.exact_probe(HypotheticalClient())
    def test_benchmark_requires_new_directory_and_private_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):bench.run(Path(directory),'https://HYPOTHETICAL.ts.net',1)
            with self.assertRaises(ValueError):bench.run(Path(directory)/'new','https://example.invalid',1)
            with self.assertRaises(ValueError):bench.run(Path(directory)/'new','https://HYPOTHETICAL.ts.net',0)
    def test_large_diagnostic_bounds_preserve_production_limit(self):
        class HypotheticalClient:
            response_limit=4*1024*1024
        with self.assertRaisesRegex(ValueError,'16 MiB'):bench.direct_large_batch(HypotheticalClient(),['HYPOTHETICAL']*64)
        self.assertEqual(e.Config('https://HYPOTHETICAL.ts.net').batch_size,16)

from predarb.validation import utc_time
if __name__=='__main__':unittest.main()
