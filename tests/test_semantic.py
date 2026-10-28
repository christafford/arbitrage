"""HYPOTHETICAL sidecar, restart, approximation and immutable-source regressions."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from predarb import semantic as s, embeddings as e, registry, cli, kalshi, polymarket_us
from predarb.store import connect
from predarb.runtime import writer_lock
from predarb.validation import dumps
from predarb.catalogue_walk import walk
from test_embeddings import bm, DATA, NOW
from helpers import Replay, fixture
from predarb.provider import HttpClient


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=str(Path(self.temp.name)/'source.sqlite3');self.ipath=self.path+'.semantic.sqlite3'
        self.source=connect(self.path);self.index=connect(self.ipath)
        self.addCleanup(self.source.close);self.addCleanup(self.index.close)
        bm.seed(self.source,DATA)
        s.initialize(self.index,self.source)
        self.service=bm.HypotheticalService(deepcopy(DATA))
    def client(self,**kw):
        return e.Client(self.index,e.Config('https://HYPOTHETICAL.ts.net',**kw),opener=self.service,
                        clock=lambda:NOW.timestamp(),sleep=lambda _:None)
    def sync(self,**kw):return s.sync(self.source,self.index,now=NOW,**kw)
    def work(self,**kw):return s.index_batch(self.index,self.client(),now=NOW,**kw)
    def retrieve(self,**kw):return s.retrieve(self.source,self.index,now=NOW,**kw)

    def test_full_incremental_backfill_and_reopen_preserves_content_vectors(self):
        reports=[]
        for _ in range(20):
            r=self.sync(budget=2);reports.append(r)
            if r['scan_complete']:break
        self.assertEqual(r['documents'],15)
        self.assertGreater(len(reports),1)
        first=self.work(budgets={'kalshi':2,'polymarket_us':2})
        self.assertEqual(first['completed'],{'kalshi':2,'polymarket_us':2})
        with connect(self.ipath) as reopened:
            self.assertEqual(reopened.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0],4)
        self.work();coverage=s.coverage(self.source,self.index,now=NOW)
        self.assertEqual(sum(v.get('backlog',0) for v in coverage['venues'].values()),0)
        self.assertEqual(self.work()['completed'],{'kalshi':0,'polymarket_us':0})
        before=self.index.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0]
        self.sync();self.work()
        self.assertEqual(self.index.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0],before)

    def test_priority_new_changed_versions_and_unchanged_text_binding(self):
        self.sync();self.work()
        old=self.index.execute("SELECT content_hash FROM semantic_documents WHERE source_id='HYPOTHETICAL-jobs' AND venue='kalshi'").fetchone()[0]
        contract=json.loads(registry._instrument(self.source,'kalshi','HYPOTHETICAL-jobs')['evidence_json'])['contract']
        registry._record_instrument(self.source,'kalshi','HYPOTHETICAL-jobs',dict(contract,uninterpreted_metadata={'new':'HYPOTHETICAL'}),
            observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        self.sync(budget=2)
        new=self.index.execute("SELECT content_hash,priority FROM semantic_documents WHERE source_id='HYPOTHETICAL-jobs' AND venue='kalshi'").fetchone()
        self.assertEqual(new,(old,1));self.assertEqual(sum(self.work()['completed'].values()),0)
        registry._record_instrument(self.source,'kalshi','HYPOTHETICAL-jobs',dict(contract,title='Changed public description'),
            observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        self.sync(budget=2);self.assertEqual(self.work()['completed']['kalshi'],1)

    def test_partial_batch_outage_keeps_committed_vectors_and_resumes(self):
        self.sync();client=self.client(batch_size=1,retries=0)
        service=client.open
        def fail(request,timeout):
            if client.requests>4:raise OSError('HYPOTHETICAL outage')
            return service(request,timeout)
        client.open=fail
        r=s.index_batch(self.index,client,now=NOW)
        self.assertEqual(r['status'],'FALLBACK');self.assertEqual(sum(r['completed'].values()),2)
        self.assertEqual(self.index.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0],2)
        self.index.execute('DELETE FROM embedding_breakers');self.index.commit()
        self.assertEqual(sum(self.work()['completed'].values()),13)
        self.assertGreater(len(self.retrieve()['candidates']),0)

    def test_interrupted_sync_rolls_back_checkpoint_and_resumes(self):
        with patch('predarb.semantic.e.public_text',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):self.sync()
        self.assertEqual(self.index.execute('SELECT count(*) FROM semantic_documents').fetchone()[0],0)
        self.assertEqual(s.state(self.index,'scan_cursor',0),0)
        self.assertTrue(self.sync()['scan_complete'])

    def test_model_upgrade_isolated_and_partial_index_stays_deterministic(self):
        self.sync();self.work()
        before=s.state(self.index,'active_identity')
        self.service.fixture['models']['data'][0]['id']='HYPOTHETICAL-upgrade'
        self.work(budgets={'kalshi':1,'polymarket_us':1})
        self.assertNotEqual(before,s.state(self.index,'active_identity'))
        coverage=s.coverage(self.source,self.index,now=NOW)
        self.assertEqual(sum(v.get('indexed',0) for v in coverage['venues'].values()),2)
        self.assertTrue(self.retrieve(semantic=False)['retrieval']['deterministic_enabled'])

    def test_stale_catalogue_and_changed_descriptions_never_use_old_results(self):
        self.sync();self.work();self.retrieve()
        r=s.retrieve(self.source,self.index,now=NOW+timedelta(days=2))
        self.assertEqual(r['candidates'],[])
        contract={'title':'Changed unrelated penguin'}
        registry._record_instrument(self.source,'kalshi','HYPOTHETICAL-jobs',contract,
            observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        results=self.retrieve()['candidates']
        self.assertFalse(any(x['kalshi_id']=='HYPOTHETICAL-jobs' for x in results))
        self.assertEqual(self.source.execute('SELECT count(*) FROM pairs').fetchone()[0],0)

    def test_diverse_events_and_contradictions_cannot_be_overridden(self):
        self.sync();self.work()
        r=self.retrieve(limit=20)
        self.assertEqual(len({x['event_key'] for x in r['candidates']}),len(r['candidates']))
        for row in r['candidates']:
            self.assertFalse(row['equivalence_verified']);self.assertFalse(row['trading_authorized'])
        doc=next(s.rows(self.index,"SELECT * FROM semantic_documents WHERE venue='kalshi'"))
        other=next(s.rows(self.index,"SELECT * FROM semantic_documents WHERE venue='polymarket_us'"))
        # Pure comparison remains authoritative even at perfect vector similarity.
        f=s.decode_features(other['features_json']);f['thresholds']={('>','999999','USD')};other['features_json']=s.encode_features(f)
        f=s.decode_features(doc['features_json']);f['thresholds']={('>','1','USD')};doc['features_json']=s.encode_features(f)
        ranked=s.rank_pair(self.source,self.index,doc,other,{'PERSISTENT_VECTOR_COSINE'},{'cosine':1,'identity':s.state(self.index,'active_identity')},NOW,s.venue_context(self.source))
        self.assertIn('THRESHOLDS_CONFLICT',ranked[1]['known_contradictions'])
        self.assertTrue(ranked[0][0])

    def test_corrupt_vector_falls_back_to_keyword_and_unknown_schema_refused(self):
        self.sync();self.work()
        self.index.execute("UPDATE semantic_vectors SET vector=x'00'");self.index.commit()
        r=self.retrieve();self.assertGreater(r['retrieval']['vector_failures'],0)
        self.assertGreater(len(r['candidates']),0)
        s.set_state(self.index,'schema','UNKNOWN');self.index.commit()
        with self.assertRaisesRegex(ValueError,'schema'):s.initialize(self.index,self.source)

    def test_coverage_stale_missing_fields_and_inference_budget_validation(self):
        self.sync()
        c=s.coverage(self.source,self.index,now=NOW)
        self.assertEqual(sum(v.get('backlog',0) for v in c['venues'].values()),15)
        self.assertTrue(any(x['settlement_deadline_horizon']=='UNKNOWN' for x in c['groups']))
        for budgets in ({'kalshi':1},{'kalshi':-1,'polymarket_us':1}):
            with self.assertRaises(ValueError):self.work(budgets=budgets)
        with self.assertRaises(ValueError):self.sync(budget=0)
        with self.assertRaises(ValueError):self.retrieve(candidate_cap=2000)

    def test_source_writer_lock_does_not_block_worker_and_offline_no_network(self):
        with writer_lock(self.path),patch('predarb.embeddings.from_environment',side_effect=AssertionError('inference forbidden')):
            with patch('sys.argv',['predarb','discovery','index-sync','--db',self.path]),redirect_stdout(StringIO()):
                self.assertEqual(cli.main(),0)
        with self.assertRaisesRegex(ValueError,'different source'):
            with connect(str(Path(self.temp.name)/'other.sqlite3')) as other:s.initialize(self.index,other)

    def test_exact_vector_signatures_are_deterministic_and_integrity_checked(self):
        values=e.vector([1,2,3])
        self.assertEqual(list(s.signatures(values)),list(s.signatures(values)))
        blob=s.pack(values)
        self.assertEqual(s.unpack({'vector':blob,'dimensions':3,'sha256':__import__('hashlib').sha256(blob).hexdigest()}),values)
        with self.assertRaises(e.EmbeddingError):s.unpack({'vector':blob,'dimensions':3,'sha256':'bad'})


class WalkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.con=connect(str(Path(self.temp.name)/'walk.sqlite3'));self.addCleanup(self.con.close)
    def test_interrupted_partial_resume_same_run_and_schema_rejection(self):
        from helpers import payload, Response
        first={'markets':[payload('kalshi-market-live')['market']]}
        # All mutations below are hypothetical, retaining valid venue shapes.
        market=deepcopy(first['markets'][0]);market['ticker']='HYPOTHETICAL-K'
        first={'markets':[market],'cursor':'HYPOTHETICAL-next'}
        bodies=iter([first,{'markets':[],'cursor':''}])
        class Client:
            def __init__(inner):inner.urls=[]
            def get(inner,url,schema,validator):
                from predarb.store import archive_response, validate_observation
                from predarb.provider import Observation
                inner.urls.append(url);data=next(bodies);validator(data)
                # Registry deliberately refuses hypothetical IDs as live: use the
                # unchanged public identity for this transport-only replay.
                data['markets']=[dict(x,ticker={'markets':[payload('kalshi-market-live')['market']]}['markets'][0]['ticker']) for x in data['markets']]
                raw=archive_response(self.con,'kalshi',url,dumps(data).encode(),200,{},NOW.isoformat(),schema)
                validate_observation(self.con,raw,'VALID',None)
                return Observation(raw,url,NOW.isoformat(),data)
        client=Client()
        a=walk(self.con,kalshi,page_size=1,max_pages=1,client=client)
        self.assertEqual(a.status,'PARTIAL')
        b=walk(self.con,kalshi,page_size=1,max_pages=1,client=client)
        self.assertEqual(a.run_id,b.run_id);self.assertEqual(b.status,'COMPLETE');self.assertIn('cursor=HYPOTHETICAL-next',client.urls[1])
        self.assertEqual(b.unique_records,1)

class ScaleAndEvidenceTests(unittest.TestCase):
    setUp=SemanticTests.setUp
    client=SemanticTests.client
    sync=SemanticTests.sync
    work=SemanticTests.work
    retrieve=SemanticTests.retrieve

    def test_backfill_exceeds_512_and_advancing_inference_clock_never_repeats_batch(self):
        for venue in registry.VENUES:
            for n in range(520):
                registry._record_instrument(self.source,venue,f'HYPOTHETICAL-scale-{n}',{'title':f'HYPOTHETICAL event {venue} {n}'},
                    observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        self.sync()
        tick=[NOW.timestamp()]
        service=self.service
        def advance(request,timeout):
            tick[0]+=1
            return service(request,timeout)
        client=e.Client(self.index,e.Config('https://HYPOTHETICAL.ts.net',batch_size=16,max_requests=100),
                        opener=advance,clock=lambda:tick[0],sleep=lambda _:None)
        report=s.index_batch(self.index,client,now=NOW,budgets={'kalshi':600,'polymarket_us':600},seconds=120)
        self.assertEqual(sum(report['completed'].values()),1055)
        self.assertEqual(self.index.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0],1055)
        self.assertGreater(report['completed']['kalshi'],512)
        self.assertGreater(report['completed']['polymarket_us'],512)
        self.assertEqual(client.hits,0)

    def test_genuine_corpus_hashes_and_real_rule_contradictions(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('m5i_eval',Path(__file__).resolve().parents[1]/'scripts/m5i_evaluate.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        corpus=json.loads(mod.FIXTURE.read_text())
        self.assertFalse(corpus['hypothetical']);self.assertFalse(corpus['operator_approved'])
        self.assertEqual({x['category'] for x in corpus['hard_negatives']},
             {'inverse_outcome','different_threshold','different_measure_or_settlement_rule','obvious_false_positive'})
        with connect(str(Path(self.temp.name)/'genuine.sqlite3')) as source,connect(str(Path(self.temp.name)/'genuine-index.sqlite3')) as index:
            report=mod.evaluate(source,index,corpus)
            self.assertEqual(report['baseline']['20']['relevant_found'],18)
            self.assertEqual(report['improved']['20']['relevant_found'],18)
            self.assertFalse(report['settlement_equivalence_approved'])
            self.assertEqual(source.execute('SELECT count(*) FROM pairs').fetchone()[0],0)
        corrupt=deepcopy(corpus);corrupt['instruments'][0]['body']='{}'
        with self.assertRaisesRegex(ValueError,'hash'):mod.seed(self.source,corrupt)

    def test_cached_refresh_has_no_network_and_expiry_is_not_renewed_by_receipt(self):
        from predarb import semantic_cli
        self.sync();self.work()
        candidates=self.retrieve()['candidates']
        self.assertTrue(semantic_cli.revalidate_candidates(self.source,candidates,now=NOW))
        self.source.execute('UPDATE registry_instruments SET observed_at=?',((NOW+timedelta(days=2)).isoformat(),));self.source.commit()
        self.assertEqual(semantic_cli.revalidate_candidates(self.source,candidates,now=NOW+timedelta(days=2)),[])
        with patch('predarb.provider.HttpClient.get',side_effect=AssertionError('network forbidden')),patch('predarb.embeddings.from_environment',side_effect=AssertionError('inference forbidden')):
            with patch('sys.argv',['predarb','discovery','refresh','--cached-catalogues','--db',self.path]),redirect_stdout(StringIO()):
                self.assertEqual(cli.main(),0)

    def test_busy_inference_writer_allows_deterministic_read_snapshot(self):
        self.sync()
        from predarb.semantic_cli import sidecar
        with patch('predarb.semantic_cli.writer_lock',side_effect=ValueError('another predarb writer holds this database lock')):
            with sidecar(self.ipath,self.source,read_fallback=True) as (index,writable):
                self.assertFalse(writable)
                result=s.retrieve(self.source,index,now=NOW,semantic=False,persist=False)
                self.assertTrue(result['candidates'])
                self.assertTrue(result['retrieval']['deterministic_enabled'])

    def test_sidecar_backup_verifies_vectors_fts_and_without_rowid_buckets(self):
        from predarb.backups import backup,verify
        self.sync();self.work()
        destination=str(Path(self.temp.name)/'backup.sqlite3')
        manifest=backup(self.ipath,destination)
        self.assertEqual(manifest['logical_sha256'],verify(destination)['logical_sha256'])
        self.assertGreater(manifest['row_counts']['semantic_buckets'],0)

    def test_persistent_ranking_rejects_invalid_stale_and_partial_liquidity(self):
        from test_discovery import DiscoveryTests
        self.db=self.source
        self.sync();self.work()
        self.assertTrue(all(x['quality']=='MISSING' for x in self.retrieve()['candidates'][0]['liquidity'].values()))
        DiscoveryTests.book(self,'polymarket_us','HYPOTHETICAL-jobs',invalid=True)
        r=self.retrieve()['candidates'];jobs=next(x for x in r if x['polymarket_us_id']=='HYPOTHETICAL-jobs')
        self.assertEqual(jobs['liquidity']['polymarket_us']['quality'],'INVALID')
        self.assertIsNone(jobs['liquidity']['polymarket_us']['depth_proxy'])
        DiscoveryTests.book(self,'polymarket_us','HYPOTHETICAL-jobs',source_at=NOW-timedelta(minutes=5))
        jobs=next(x for x in self.retrieve()['candidates'] if x['polymarket_us_id']=='HYPOTHETICAL-jobs')
        self.assertEqual(jobs['liquidity']['polymarket_us']['quality'],'STALE_SOURCE')
        DiscoveryTests.book(self,'polymarket_us','HYPOTHETICAL-jobs',quantity='0.01')
        jobs=next(x for x in self.retrieve()['candidates'] if x['polymarket_us_id']=='HYPOTHETICAL-jobs')
        self.assertEqual(jobs['liquidity']['polymarket_us']['depth_proxy'],'0.01')
        self.assertFalse(jobs['liquidity']['polymarket_us']['executable'])

    def test_walk_interrupt_mid_page_replays_without_skipping_or_double_counting(self):
        from predarb import catalogue_walk
        from predarb.provider import Observation
        from predarb.store import archive_response,validate_observation
        from helpers import payload
        market=payload('kalshi-market-live')['market']
        class ReplayClient:
            def get(inner,url,schema,validator):
                data={'markets':[market],'cursor':'HYPOTHETICAL-next'} if 'cursor=' not in url else {'markets':[],'cursor':''}
                validator(data)
                raw=archive_response(self.source,'kalshi',url,dumps(data).encode(),200,{},NOW.isoformat(),schema)
                validate_observation(self.source,raw,'VALID',None)
                return Observation(raw,url,NOW.isoformat(),data)
        save=catalogue_walk.save_entry
        def interrupted(*args,**kwargs):
            save(*args,**kwargs)
            raise KeyboardInterrupt()
        with patch('predarb.catalogue_walk.save_entry',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):
            walk(self.source,kalshi,page_size=1,max_pages=1,client=ReplayClient())
        run=self.source.execute('SELECT id,pages,records,next_page,status FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(run[1:],(0,0,None,'INTERRUPTED'))
        result=walk(self.source,kalshi,page_size=1,max_pages=2,client=ReplayClient())
        self.assertEqual(result.run_id,run[0]);self.assertEqual(result.status,'COMPLETE')
        self.assertEqual((result.records,result.unique_records,result.duplicates),(1,1,0))

    def test_walk_unknown_schema_and_no_progress_fail_closed(self):
        from predarb.provider import Observation
        class Bad:
            def get(inner,url,schema,validator):
                data={'markets':[{'ticker':'HYPOTHETICAL-missing-fields'}],'cursor':''}
                validator(data)
        with self.assertRaises(ValueError):walk(self.source,kalshi,page_size=1,max_pages=1,client=Bad())
        self.assertEqual(self.source.execute('SELECT status FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()[0],'FAILED')
        with self.assertRaisesRegex(ValueError,'page size'):
            walk(self.source,kalshi,page_size=2,max_pages=1,client=Bad())

    def test_sparse_vector_lookup_does_not_scan_unindexed_venue(self):
        self.sync();self.work()
        template=next(s.rows(self.index,"SELECT * FROM semantic_documents WHERE venue='kalshi'"))
        columns=[key for key in template if key!='id']
        for n in range(5000):
            item=dict(template,source_id=f'HYPOTHETICAL-unindexed-{n}',content_hash=f'HYPOTHETICAL-unused-{n}')
            self.index.execute('INSERT INTO semantic_documents('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',
                               tuple(item[key] for key in columns))
        self.index.commit()
        query=next(s.rows(self.index,"SELECT * FROM semantic_documents WHERE venue='polymarket_us'"))
        steps=[0]
        def bounded_steps():
            steps[0]+=1
            return int(steps[0]>100)
        self.index.set_progress_handler(bounded_steps,1000)
        try:
            matches,_=s.vector_candidates(self.index,query,s.state(self.index,'active_identity'),NOW)
            self.assertTrue(matches)
        finally:self.index.set_progress_handler(None,0)

    def test_generic_provider_question_preserves_selection_title_and_event_diversity(self):
        for n in range(3):
            for venue in registry.VENUES:
                contract={'title':f'HYPOTHETICAL singer {n} top song','description':f'HYPOTHETICAL singer {n} is top song'}
                if venue=='polymarket_us':contract['question']='HYPOTHETICAL Top Song 2030?'
                else:contract['event_ticker']=f'HYPOTHETICAL-song-event-{n}'
                registry._record_instrument(self.source,venue,f'HYPOTHETICAL-song-{n}',contract,
                    observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        self.sync()
        doc=next(s.rows(self.index,"select * from semantic_documents where venue='polymarket_us' and source_id='HYPOTHETICAL-song-0'"))
        self.assertIn('singer',s.decode_features(doc['features_json'])['subject'])
        result=self.retrieve(semantic=False,limit=100)['candidates']
        self.assertLessEqual(sum(row['polymarket_us_id'].startswith('HYPOTHETICAL-song') for row in result),1)

    def test_initial_partial_sidecar_retains_established_deterministic_queue(self):
        from predarb import discovery
        prior=discovery.refresh_queue(self.source,now=NOW,limit=20)
        self.assertTrue(prior['candidates'])
        original=s.sync
        with patch('predarb.registry.now_utc',return_value=NOW),patch('predarb.semantic.sync',side_effect=lambda a,b,**kw:original(a,b,budget=1,now=NOW)):
            with patch('sys.argv',['predarb','discovery','refresh','--cached-catalogues','--db',self.path]),redirect_stdout(StringIO()) as output:
                self.assertEqual(cli.main(),0)
        result=json.loads(output.getvalue())
        self.assertGreater(result['retained_deterministic_candidates'],0)
        before={(r['kalshi_id'],r['polymarket_us_id']) for r in prior['candidates']}
        after={(r['kalshi_id'],r['polymarket_us_id']) for r in result['candidates']}
        self.assertTrue(before<=after)
        self.assertTrue(all(not x['equivalence_verified'] for x in result['candidates']))

    def test_fresh_genuine_review_fixture_replays_without_approval(self):
        import hashlib
        fixture=json.loads((Path(__file__).parent/'fixtures/m5i-live-review.json').read_text())
        self.assertFalse(fixture['hypothetical'])
        identities=[]
        for response in fixture['responses']:
            self.assertEqual(hashlib.sha256(response['body'].encode()).hexdigest(),response['body_sha256'])
            adapter=kalshi if response['venue']=='kalshi' else polymarket_us
            data=json.loads(response['body']);adapter.validate_detail(data)
            self.assertEqual(response['schema_version'],adapter.SCHEMA_VERSION)
            identities.append(s.sports.key(s.sports.features(data['market'])))
        self.assertIsNotNone(identities[0]);self.assertEqual(identities[0],identities[1])
        self.assertEqual(self.source.execute('SELECT count(*) FROM pairs').fetchone()[0],0)

    def test_changed_definition_priority_streams_before_reading_next_record(self):
        self.sync()
        for n in range(3):
            registry._record_instrument(self.source,'kalshi',f'HYPOTHETICAL-new-{n}',{'title':f'HYPOTHETICAL newly changed {n}'},
                observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        original=s.rows
        def checked(con,sql,args=()):
            previous=None
            for row in original(con,sql,args):
                if con is self.source and 'WHERE h.version_id>?' in sql:
                    if previous is not None:
                        self.assertIsNotNone(self.index.execute('SELECT 1 FROM semantic_documents WHERE source_id=?',(previous,)).fetchone())
                    previous=row['source_id']
                yield row
        with patch('predarb.semantic.rows',side_effect=checked):self.sync(budget=10)
        self.assertEqual(self.index.execute("SELECT count(*) FROM semantic_documents WHERE source_id LIKE 'HYPOTHETICAL-new-%'").fetchone()[0],3)
