"""M5O hypothetical economics, lifecycle failures and genuine source schema tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
import tempfile
import threading
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from predarb import conditional_research as econ, continuous_research as run
from predarb.book_stream import KalshiBookStream
from predarb.models import AskLevel
from predarb.orderbooks import normalize_rest
from predarb.store import connect, archive_response
from predarb.validation import load_json, utc_time

FIX=Path(__file__).parent/'fixtures'


def hypothetical():
    data=load_json((FIX/'m4-hypothetical.json').read_bytes()); at=utc_time(data['clock'])
    k=KalshiBookStream('HYPOTHETICAL-K',data['kalshi_metadata'],metadata_received_at=data['clock'])
    kb=k.apply(data['kalshi_ws_snapshot'],received_at=data['clock'],now=at,generation=k.generation)
    ub=normalize_rest('polymarket_us','HYPOTHETICAL-P',data['polymarket_us_rest'],data['polymarket_us_metadata'],
        received_at=data['clock'],metadata_received_at=data['clock'],now=at)
    # Hypothetical same-proposition cash-long quotes, not the fixture's inverse registry.
    kb=replace(kb,no_asks=(AskLevel(D('.40'),D('20')),AskLevel(D('.55'),D('30'))))
    pair={'id':'hypothetical','kalshi_id':kb.source_id,'polymarket_us_id':ub.source_id,
          'classification':'CONDITIONAL','ordinary_basis':'HYPOTHETICAL same ordinary outcome',
          'residual_risks':['HYPOTHETICAL independent exceptional payouts'],'origin':'DETERMINISTIC',
          'ai_only':False,'contract_fingerprints':{'kalshi':'a','polymarket_us':'b'}}
    return data,at,[kb,ub],pair


class ConditionalTests(unittest.TestCase):
    def setUp(self): self.data,self.at,self.books,self.pair=hypothetical()

    def evaluate(self,books=None,pair=None,at=None):
        books=books or self.books; at=at or self.at
        return econ.quote_cases(books,pair or self.pair,now=at,inspected=[b.as_dict(now=at) for b in books])

    def test_depth_budget_optimum_and_unknown_fees_cash_collateral(self):
        r=self.evaluate(); self.assertEqual(r['status'],'CONDITIONAL_GROSS_ONLY')
        small,medium,*_=r['capital_cases']
        self.assertEqual(small['evaluated_quantity'],D(5))
        self.assertEqual(small['gross_edge_usd'],D('.65'))
        self.assertEqual(medium['evaluated_quantity'],D(20))
        self.assertGreater(medium['maximum_quantity_within_quote_budget'],D(20))
        self.assertEqual(medium['gross_edge_usd'],D('2.60'))
        self.assertIsNone(medium['fee_adjusted_edge_usd'])
        self.assertIsNone(medium['all_in_capital_usd'])
        self.assertIsNone(medium['settlement_delay_seconds'])
        self.assertEqual(medium['loss_if_selected_legs_both_pay_zero_before_fees_usd'],D('17.40'))
        self.assertFalse(r['strict_arbitrage_eligible']); self.assertFalse(r['trading_authorized'])

    def test_negative_edge_and_partial_liquidity_do_not_invent_depth(self):
        k=replace(self.books[0],no_asks=(AskLevel(D('.60'),D(2)),))
        r=self.evaluate([k,self.books[1]])
        for c in r['capital_cases']:
            self.assertEqual(c['maximum_matched_displayed_quantity'],D(2))
            self.assertEqual(c['gross_edge_usd'],D('-.14'))
            self.assertFalse(c['positive_conditional_discrepancy'])
            self.assertTrue(c['depth_limited_before_budget'])

    def test_missing_stale_future_invalid_partial_and_continuity_reject_economics(self):
        bad=[replace(self.books[1],source_ts=None),replace(self.books[1],source_ts=(self.at-timedelta(seconds=3)).isoformat()),
            replace(self.books[1],received_at=(self.at+timedelta(seconds=1)).isoformat()),
            replace(self.books[1],rejections=('PARTIAL_BOOK',)),
            replace(self.books[1],rejections=('INVALID_BOOK: off-grid price',)),
            replace(self.books[1],rejections=('UNVERIFIED_CONTINUITY',)),
            replace(self.books[1],metadata_received_at=(self.at-timedelta(seconds=61)).isoformat()),
            replace(self.books[1],market_close_at=self.at.isoformat())]
        for book in bad:
            with self.subTest(book=book.rejections):
                r=self.evaluate([self.books[0],book]); self.assertEqual(r['capital_cases'],[])

    def test_invalid_us_grid_price_missing_quantity_normalizer_fails_closed(self):
        for field,value in [('qty',None),('qty','1.2'),('px',{'value':'1.1','currency':'USD'}),
                            ('px',{'value':'.4705','currency':'USD'})]:
            raw=deepcopy(self.data['polymarket_us_rest']); raw['marketData']['offers'][0][field]=value
            b=normalize_rest('polymarket_us','HYPOTHETICAL-P',raw,self.data['polymarket_us_metadata'],
                received_at=self.at.isoformat(),metadata_received_at=self.at.isoformat(),now=self.at)
            self.assertEqual(self.evaluate([self.books[0],b])['capital_cases'],[])

    def test_discovery_and_arbitrary_strict_configuration_cannot_authorize(self):
        p={**self.pair,'classification':'DISCOVERY'}
        self.assertEqual(self.evaluate(pair=p)['status'],'DISCOVERY_ONLY')
        self.assertEqual(self.evaluate(pair=p)['capital_cases'],[])
        for key,value in [('classification','STRICT'),('ordinary_basis',''),('residual_risks',[])]:
            with self.assertRaises(ValueError):self.evaluate(pair={**self.pair,key:value})

    def test_wrong_pair_or_synthetic_short_route_rejected(self):
        with self.assertRaises(ValueError):self.evaluate(pair={**self.pair,'kalshi_id':'WRONG'})
        k=replace(self.books[0],mechanism_no='SYNTHETIC_SHORT')
        with self.assertRaises(ValueError):self.evaluate([k,self.books[1]])
        self.assertIn('BLOCKED',self.evaluate()['reverse_direction'])

    def test_no_fee_sensitivity_is_reported_as_reviewed_net(self):
        c=self.evaluate()['capital_cases'][0]
        self.assertEqual(c['hypothetical_combined_fee_per_unit_sensitivity']['0.02'],D('.55'))
        self.assertIsNone(c['fee_adjusted_edge_usd'])

    def test_fingerprint_ignores_quotes_but_not_rules_or_unknown_fields(self):
        m=self.data['polymarket_us_metadata']; original=econ.contract_fingerprint('polymarket_us',m)
        n=deepcopy(m); n['updatedAt']='2031-01-01T00:00:00Z'; n['marketSides'][0]['price']='.99'
        self.assertEqual(econ.contract_fingerprint('polymarket_us',n),original)
        n['description']+=' changed'; self.assertNotEqual(econ.contract_fingerprint('polymarket_us',n),original)
        n=deepcopy(m); n['unknown_schema_field']=True
        self.assertNotEqual(econ.contract_fingerprint('polymarket_us',n),original)

    def test_quality_never_ignores_inspection_disconnect_or_new_invalid_frame(self):
        inspected=[b.as_dict(now=self.at) for b in self.books]
        for reason in ['STREAM_DISCONNECTED','NEWER_INVALID_FRAME','NEWER_METADATA_REQUIRES_FRESH_BOOK','LOCAL_CLOCK_UNVERIFIED']:
            inspected[0]['rejections']=[reason]
            r=econ.quote_cases(self.books,self.pair,now=self.at,inspected=inspected)
            self.assertEqual(r['capital_cases'],[])


class ObservationTests(unittest.TestCase):
    def setUp(self): self.data,self.at,self.books,self.pair=hypothetical()

    def config(self):
        pairs=[dict(self.pair,id='hypothetical-'+str(i),kalshi_id='HYPOTHETICAL-K'+str(i)) for i in range(10)]
        return dict(schema=run.VERSION,started_at=self.at.isoformat(),deadline_at=(self.at+timedelta(hours=24)).isoformat(),
                    pairs=pairs,poll_seconds=5,segment_seconds=900,max_storage_bytes=20*1024**3,min_free_bytes=2*1024**3)

    def test_run_bounds_no_duplicate_pairs_or_unknown_class(self):
        c=self.config();run.validate_config(c)
        for change in [{'pairs':c['pairs'][:9]},{'poll_seconds':1},{'schema':'unknown'},
                       {'deadline_at':(self.at+timedelta(hours=25)).isoformat()},
                       {'pairs':[c['pairs'][0]]*10}]:
            with self.assertRaises(ValueError):run.validate_config({**c,**change})

    def test_expired_run_and_monotonic_budget_never_renew(self):
        c=self.config()
        self.assertEqual(run.remaining(c,100,at=self.at+timedelta(hours=25),mono=101),0)
        self.assertEqual(run.remaining(c,100,at=self.at+timedelta(seconds=1),mono=86500),0)
        self.assertEqual(run.remaining(c,100,at=self.at+timedelta(hours=23),mono=101),3600)

    def test_source_changes_downgrade_and_clock_failure_blocks(self):
        refs={'book':{'observation_id':1,'sha256':'x'},'metadata':{'observation_id':2,'sha256':'y'}}
        metas=[self.data['kalshi_metadata'],self.data['polymarket_us_metadata']]
        p={**self.pair,'contract_fingerprints':dict(zip(('kalshi','polymarket_us'),[
            econ.contract_fingerprint(v,m) for v,m in zip(('kalshi','polymarket_us'),metas)]))}
        def select(_con,v,sid,at):
            i=0 if v=='kalshi' else 1; b=self.books[i]
            return b,b.as_dict(now=at),refs,metas[i]
        with patch.object(run,'select_book',select):
            self.assertEqual(run.observation(None,None,p,self.at,synchronized=True)['status'],'CONDITIONAL_GROSS_ONLY')
            self.assertEqual(run.observation(None,None,p,self.at,synchronized=False)['capital_cases'],[])
            metas[1]['description']+=' revised'
            result=run.observation(None,None,p,self.at,synchronized=True)
            self.assertEqual(result['classification'],'DISCOVERY');self.assertEqual(result['capital_cases'],[])

    def test_positive_sample_spans_break_on_gap_or_rejection_never_continuous(self):
        s=run.empty_summary()
        base=econ.quote_cases(self.books,self.pair,now=self.at,inspected=[b.as_dict(now=self.at) for b in self.books])
        for sec in [0,5,20]:run.accumulate(s,{**base,'at':(self.at+timedelta(seconds=sec)).isoformat()})
        v=s['capital']['5'];self.assertEqual(v['sample_clusters'],2)
        self.assertEqual(v['positive_sample_cluster_span_seconds'],5)
        run.accumulate(s,{'at':(self.at+timedelta(seconds=25)).isoformat(),'rejections':['STALE']})
        run.accumulate(s,{**base,'at':(self.at+timedelta(seconds=30)).isoformat()})
        self.assertEqual(v['sample_clusters'],3);self.assertIsNone(v['continuous_opportunity_duration_seconds'])

    def test_missing_capture_cannot_pass_offline_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaises(FileNotFoundError):run.replay_segment(root,self.pair)
            run.atomic_json(root/'status.json',{'schema':run.VERSION,'pair_id':self.pair['id']})
            with self.assertRaisesRegex(ValueError,'unfinished'):run.replay_segment(root,self.pair)

    def test_archived_visibility_preserves_pending_status_and_excludes_late_commits(self):
        with tempfile.TemporaryDirectory() as tmp, connect(str(Path(tmp)/'hypothetical.sqlite3')) as con:
            first=archive_response(con,'kalshi','https://external-api.kalshi.com/hypothetical',
                b'{"hypothetical":true}',200,{},self.at.isoformat(),'HYPOTHETICAL')
            known=run.visible_archive(con)
            original=con.execute('SELECT validation_status FROM raw_observations WHERE id=?',(first,)).fetchone()[0]
            con.execute("UPDATE raw_observations SET validation_status='VALID' WHERE id=?",(first,));con.commit()
            archive_response(con,'kalshi','https://external-api.kalshi.com/hypothetical',
                b'{"hypothetical":"received earlier, committed later"}',200,{},self.at.isoformat(),'HYPOTHETICAL')
            with run.archived_visibility(con,known):
                self.assertEqual(con.execute('SELECT count(*) FROM raw_observations').fetchone()[0],1)
                self.assertEqual(con.execute('SELECT validation_status FROM raw_observations').fetchone()[0],original)
            self.assertEqual(con.execute('SELECT count(*) FROM raw_observations').fetchone()[0],2)
            self.assertEqual(con.execute('SELECT validation_status FROM raw_observations WHERE id=?',(first,)).fetchone()[0],'VALID')
            bad={**known,'raw_head':-1}
            with self.assertRaises(ValueError),run.archived_visibility(con,bad):pass

    def test_supervisor_clock_failure_prevents_children_and_existing_directory_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(run,'clock_evidence',return_value={'synchronized':False}), \
             patch.object(run.subprocess,'Popen') as launch:
            root=Path(tmp)/'new'
            with self.assertRaisesRegex(ValueError,'synchronized'):
                run.supervise(root,{'pairs':self.config()['pairs']},'unused',seconds=10,stop=threading.Event())
            launch.assert_not_called()
            with self.assertRaises(FileExistsError):
                run.supervise(root,{'pairs':self.config()['pairs']},'unused',seconds=10,stop=threading.Event())

    def test_supervisor_deadline_resource_early_exit_and_forced_cleanup(self):
        for scenario,expected in [('deadline','DEADLINE_REACHED'),('disk','LOW_DISK'),
                                  ('size','STORAGE_LIMIT'),('early','ALL_WORKERS_ENDED_EARLY'),
                                  ('kill','FORCED_WORKER_STOP')]:
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as tmp:
                elapsed=[0]; children=[]
                class Stop:
                    def is_set(self):return False
                    def wait(self,seconds):elapsed[0]+=seconds;return False
                class Child:
                    returncode=None
                    def poll(self):return 0 if scenario=='early' else self.returncode
                    def terminate(self):self.returncode=-15
                    def kill(self):self.returncode=-9
                    def wait(self,timeout):
                        if scenario=='kill' and self.returncode!=-9:raise run.subprocess.TimeoutExpired('hypothetical',timeout)
                        return self.returncode
                def launch(*a,**kw):
                    child=Child();children.append(child);return child
                with patch.object(run,'now',lambda:self.at+timedelta(seconds=elapsed[0])), \
                     patch.object(run.time,'monotonic',lambda:elapsed[0]), \
                     patch.object(run,'clock_evidence',return_value={'synchronized':True}), \
                     patch.object(run.subprocess,'Popen',launch), \
                     patch.object(run.shutil,'disk_usage',return_value=SimpleNamespace(free=0 if scenario=='disk' else 100*1024**3)), \
                     patch.object(run,'storage_bytes',return_value=30*1024**3 if scenario=='size' else 0):
                    r=run.supervise(Path(tmp)/'new',{'pairs':self.config()['pairs']},'unused',seconds=10,stop=Stop())
                self.assertEqual(r['status'],expected);self.assertEqual(len(children),10)
                self.assertTrue(all(c.poll() is not None for c in children))

    def test_deadline_transport_rejects_before_opening_network(self):
        with tempfile.TemporaryDirectory() as tmp, connect(str(Path(tmp)/'hypothetical.sqlite3')) as con:
            client=run.DeadlineClient(con,'polymarket_us',guard=lambda:True,emit=lambda row:None,attempts=1)
            with self.assertRaisesRegex(OSError,'FIXED_DEADLINE'):
                client.get('https://gateway.polymarket.us/v1/market/slug/hypothetical','HYPOTHETICAL',lambda x:None)
            self.assertEqual(con.execute('SELECT count(*) FROM raw_observations').fetchone()[0],0)


class GenuineReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        fixture=load_json((FIX/'m5o-live-replay.json').read_bytes()); self.pair=fixture['pair']
        self.assertIs(fixture['hypothetical'],False)
        for name,item in fixture['files'].items():
            raw=item['body'].encode();self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
            (self.root/name).write_bytes(raw)
        for name,tables in fixture['databases'].items():
            with connect(str(self.root/name)) as con:
                for table in ('collection_runs','raw_observations','catalogue_entries','book_captures',
                              'ws_connections','ws_frames','normalized_books'):
                    rows=tables[table]
                    for row in rows:
                        if 'raw_body' in row:row['raw_body']=row['raw_body'].encode()
                        columns=list(row)
                        con.execute('INSERT INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',list(row.values()))
                con.commit()

    def test_real_pair_raw_bytes_and_visibility_replay_offline(self):
        r=run.replay_segment(self.root,self.pair)
        self.assertEqual(r['replay'],'PASS');self.assertEqual(r['raw_hashes_verified'],41)
        self.assertEqual(r['samples'],9)

    def test_hypothetical_tampering_and_false_count_fail_replay(self):
        with connect(str(self.root/'us.sqlite3')) as con:
            con.execute("UPDATE raw_observations SET raw_body=? WHERE id=(SELECT max(id) FROM raw_observations)",(b'{}',));con.commit()
        with self.assertRaisesRegex(ValueError,'hash'):run.replay_segment(self.root,self.pair)

    def test_hypothetical_lost_clock_or_unfinished_stream_cannot_pass(self):
        run.atomic_json(self.root/'clock-after.json',{'synchronized':False})
        with self.assertRaisesRegex(ValueError,'clock'):run.replay_segment(self.root,self.pair)
        run.atomic_json(self.root/'clock-after.json',{'synchronized':True})
        with connect(str(self.root/'kalshi.sqlite3')) as con:
            con.execute('UPDATE ws_connections SET ended_at=NULL');con.commit()
        with self.assertRaisesRegex(ValueError,'unfinished'):run.replay_segment(self.root,self.pair)

    def test_current_public_definition_fixtures_keep_hashes_and_tick_lot_fields(self):
        from predarb import kalshi,polymarket_us
        from predarb.orderbooks import market_rules
        data=load_json((FIX/'m5o-definitions-live.json').read_bytes())
        self.assertIs(data['hypothetical'],False);self.assertEqual(len(data['responses']),22)
        for row in data['responses']:
            raw=row['body'].encode();self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
            adapter=kalshi if row['venue']=='kalshi' else polymarket_us
            payload=load_json(raw);adapter.validate_detail(payload)
            market_rules(row['venue'],row['source_id'],payload['market'],now=utc_time(row['received_at']))


if __name__=='__main__':unittest.main()
