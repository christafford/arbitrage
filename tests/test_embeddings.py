"""HYPOTHETICAL protocol, outage, cache and retrieval integration evidence."""
from contextlib import closing, redirect_stdout
from copy import deepcopy
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, build_opener, ProxyHandler

from predarb import embeddings as e, discovery, discovery_cli, registry, cli
from predarb.store import connect
from predarb.validation import dumps, utc_time

spec = importlib.util.spec_from_file_location('embedding_benchmark', Path(__file__).resolve().parents[1] / 'scripts/embedding_benchmark.py')
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)
DATA = json.loads(bm.FIXTURE.read_text())
NOW = utc_time(DATA['clock'])


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'test.sqlite3')
        self.con = connect(self.path)
        self.addCleanup(self.con.close)
        self.service = bm.HypotheticalService(deepcopy(DATA))
        self.clock = NOW.timestamp()
        self.sleeps = []

    def client(self, opener=None, **kwargs):
        return e.Client(self.con, e.Config('https://gaming.example.ts.net', **kwargs),
                        opener=opener or self.service, clock=lambda: self.clock, sleep=self.sleeps.append)

    def test_environment_url_and_rejected_url_shapes(self):
        with patch.dict('os.environ', {'PREDARB_EMBEDDING_URL': 'https://gaming.example.ts.net/v1/embeddings'}):
            self.assertEqual(e.from_environment(self.con).base, 'https://gaming.example.ts.net/v1')
        for url in ('http://localhost', 'https://name:secret@example.com', 'https://x/?key=secret',
                    'https://x/#secret', 'https://x:1234', 'https://x/completion'):
            with self.subTest(url=url), self.assertRaises(e.EmbeddingError):
                e.Config(url)
        for options in ({'timeout': 0}, {'retries': 4}, {'batch_size': 0}, {'max_items': 513}):
            with self.assertRaises(e.EmbeddingError):
                self.client(**options)

    def test_actual_dimensions_batches_indices_cache_content_and_model(self):
        client = self.client(batch_size=2)
        texts = [e.public_text({'title': c['left']}) for c in DATA['cases']]
        values = client.embed(texts)
        self.assertEqual(client.dimensions, 6)
        self.assertEqual(len(self.service.requests), 5)  # models + probe + three batches
        self.assertEqual(values[1], (0, 1, 0, 0, 0, 0))  # response order reversed
        client.embed(texts)
        self.assertEqual(client.hits, 6)
        self.assertEqual(len(self.service.requests), 5)
        client.embed([e.public_text({'title': 'changed'})])
        self.assertEqual(len(self.service.requests), 6)
        replacement = self.client()
        replacement.embed(texts)
        self.assertEqual(replacement.hits, 6)
        self.service.fixture['models']['data'][0]['id'] = 'HYPOTHETICAL-new-model'
        new = self.client()
        new.embed(texts)
        self.assertNotEqual(new.identity, client.identity)
        self.assertEqual(new.hits, 0)
        self.assertTrue(all(r[0] == 'VALID' for r in self.con.execute("SELECT validation_status FROM raw_observations")))

    def test_missing_fields_invalid_vectors_and_drift_are_archived_rejected(self):
        mutations = [lambda x: x.pop('data'), lambda x: x.pop('model'),
                     lambda x: x['data'][0].pop('index'),
                     lambda x: x['data'].append(x['data'][0]),
                     lambda x: x['data'][0].update(embedding=[]),
                     lambda x: x['data'][0].update(embedding=[0,0]),
                     lambda x: x['data'][0].update(embedding=[True,1]),
                     lambda x: x['data'][0].update(embedding=['0.5',1]),
                     lambda x: x['data'][0].update(embedding=[[1],1]),
                     lambda x: x['data'][0].update(embedding=[1e309,1])]
        for mutate in mutations:
            self.con.execute('DELETE FROM embedding_breakers'); self.con.commit()
            client = self.client()
            client.probe()
            response = deepcopy(DATA['embedding_response'])
            mutate(response)
            raw = json.dumps(response).encode()
            client.open = lambda *a, **kw: bm.HypotheticalResponse(raw)
            with self.assertRaises(e.EmbeddingError):
                client.embed([e.public_text({'title': 'new'})])
            status, body = self.con.execute('SELECT validation_status,raw_body FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone()
            self.assertEqual((status,body), ('REJECTED',raw))
        for values in ([1,2], [1]*7):
            with self.assertRaises(e.EmbeddingError):
                e.vector(values, 6)

    def test_timeout_retries_persistent_breaker_and_recovery(self):
        calls=[]
        def failed(request, timeout):
            calls.append(timeout)
            raise TimeoutError('HYPOTHETICAL transport failure secret must not be logged')
        client=self.client(opener=failed)
        with self.assertRaisesRegex(e.EmbeddingError, 'SERVICE_UNREACHABLE'):
            client.probe()
        self.assertEqual(calls, [5,5,5])
        self.assertEqual(self.sleeps,[1,2])
        with self.assertRaisesRegex(e.EmbeddingError,'CIRCUIT_OPEN'):
            self.client(opener=failed).probe()
        self.assertEqual(len(calls),3)
        self.clock += 61
        self.assertEqual(self.client().probe()['dimensions'],6)

    def test_http_errors_retry_after_redirect_size_and_budget(self):
        for status, expected in [(429,3),(503,3),(401,1),(302,1)]:
            self.con.execute('DELETE FROM embedding_breakers'); self.con.commit()
            calls=[]
            def fail(*a,**kw):
                calls.append(1)
                response=bm.HypotheticalResponse(b'{}');response.status=status
                return response
            with self.assertRaises(e.EmbeddingError): self.client(opener=fail).probe()
            self.assertEqual(len(calls),expected)
        self.con.execute('DELETE FROM embedding_breakers');self.con.commit()
        response=bm.HypotheticalResponse(b'{}');response.status=429;response.headers={'Retry-After':'3600'}
        with self.assertRaises(e.EmbeddingError): self.client(opener=lambda *a,**k:response).probe()
        self.con.execute('DELETE FROM embedding_breakers');self.con.commit()
        with self.assertRaisesRegex(e.EmbeddingError,'BUDGET'):
            self.client(max_requests=1).probe()
        response=bm.HypotheticalResponse(b'x'*(4*1024*1024+1))
        with self.assertRaises(e.EmbeddingError): self.client(opener=lambda *a,**k:response).probe()
        self.assertEqual(self.con.execute('SELECT truncated FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone()[0],1)

    def test_stale_corrupt_cache_retention_and_future_time(self):
        text=e.public_text({'title':'Unemployment declines'})
        first=self.client();first.embed([text])
        self.con.execute("UPDATE embedding_cache SET vector_json='[true]'");self.con.commit()
        first.embed([text]);self.assertEqual(first.hits,0)
        self.clock += 31*86400
        first.embed([text]);self.assertEqual(first.hits,0)
        self.clock -= 86400
        first.embed([text]);self.assertEqual(first.hits,0)
        self.client(cache_rows=1).embed([text,e.public_text({'title':'other'})])
        self.assertEqual(self.con.execute('SELECT count(*) FROM embedding_cache').fetchone()[0],1)

    def test_privacy_allowlist_and_no_environment_auth(self):
        contract={'title':'Public event', 'account_secret':'HYPOTHETICAL_SECRET','uninterpreted_metadata':{'private':'HYPOTHETICAL_SECRET'}, 'review':'HYPOTHETICAL_SECRET'}
        with patch.dict('os.environ', {'OPENAI_API_KEY':'HYPOTHETICAL_SECRET','KALSHI_API_KEY':'HYPOTHETICAL_SECRET','HTTPS_PROXY':'https://secret.invalid'}):
            self.client().embed([e.public_text(contract)])
        for request in self.service.requests:
            self.assertNotIn('HYPOTHETICAL_SECRET',repr(request.headers))
            self.assertNotIn(b'HYPOTHETICAL_SECRET',request.data or b'')
            self.assertFalse(request.has_header('Authorization'))
        with self.assertRaisesRegex(e.EmbeddingError,'TOO_LARGE'):
            e.public_text({'title':'x'*16001})

    def test_pipeline_benchmark_queue_freshness_and_no_approval(self):
        report=bm.benchmark(self.con,DATA,self.client())
        self.assertGreater(report['results']['embedding_assisted']['recall_at_k'],report['results']['deterministic']['recall_at_k'])
        ranked=discovery.refresh_queue(self.con,now=NOW,limit=100,embedding_client=self.client())
        queued=discovery.queue(self.con,now=NOW,limit=100)
        self.assertEqual(ranked['candidates'],queued['candidates'])
        self.assertEqual(self.con.execute('SELECT count(*) FROM pairs').fetchone()[0],0)
        self.assertEqual(discovery.queue(self.con,now=NOW+timedelta(days=2))['candidates'],[])
        # Changed content cannot reuse a saved embedding match.
        registry._record_instrument(self.con,'polymarket_us','HYPOTHETICAL-jobs',{'title':'Unrelated penguin'},observed_at=NOW.isoformat(),available=True,hypothetical=True,now=NOW)
        rows=discovery.queue(self.con,now=NOW,limit=100)['candidates']
        self.assertFalse(any(r['kalshi_id']=='HYPOTHETICAL-jobs' for r in rows))

    def test_outage_identical_deterministic_results_and_empty_stale_skips_network(self):
        bm.seed(self.con,DATA)
        baseline=discovery.discover(self.con,now=NOW,limit=100)
        def fail(*a,**kw): raise OSError('HYPOTHETICAL outage')
        report=discovery.discover(self.con,now=NOW,limit=100,embedding_client=self.client(opener=fail))
        self.assertEqual(report['candidates'],baseline['candidates'])
        self.assertEqual(report['embedding']['status'],'FALLBACK')
        stale=discovery.discover(self.con,now=NOW+timedelta(days=2),embedding_client=self.client())
        self.assertEqual(stale['embedding']['status'],'EMPTY')
        self.assertEqual(self.service.requests,[])

    def test_migration_and_readonly_queue_no_network_offline_cli(self):
        self.con.execute('DROP TABLE embedding_cache');self.con.execute('DROP TABLE embedding_breakers')
        self.con.execute('PRAGMA user_version=7');self.con.commit()
        with connect(self.path) as migrated:
            self.assertEqual(migrated.execute('PRAGMA user_version').fetchone()[0],8)
        with patch.dict('os.environ',{'PREDARB_EMBEDDING_URL':'https://gaming.example.ts.net'}), patch('predarb.embeddings.from_environment',side_effect=AssertionError('network forbidden')), redirect_stdout(StringIO()):
            with patch('sys.argv', ['predarb','discovery','refresh','--offline','--db',self.path]):
                self.assertEqual(cli.main(),0)
            with patch('sys.argv', ['predarb','discovery','queue','--db',self.path]):
                self.assertEqual(cli.main(),0)

    def test_probe_schema_duplicate_json_and_dimension_changes(self):
        for payload in ({}, {'object':'list','data':[]}, {'object':'list','data':[{},{}]}):
            self.con.execute('DELETE FROM embedding_breakers');self.con.commit()
            with self.assertRaisesRegex(e.EmbeddingError, 'MODEL_SCHEMA'):
                self.client(opener=lambda *a, **kw: bm.HypotheticalResponse(dumps(payload).encode())).probe()
        self.con.execute('DELETE FROM embedding_breakers');self.con.commit()
        with self.assertRaisesRegex(e.EmbeddingError,'INVALID_JSON'):
            self.client(opener=lambda *a, **kw: bm.HypotheticalResponse(b'{"object":"list","object":"list"}')).probe()
        self.con.execute('DELETE FROM embedding_breakers');self.con.commit()
        client=self.client();client.probe()
        response=deepcopy(DATA['embedding_response']);response['data'][0]['embedding']=[1,2]
        client.open=lambda *a,**kw: bm.HypotheticalResponse(dumps(response).encode())
        with self.assertRaisesRegex(e.EmbeddingError,'SCHEMA'):
            client.embed([e.public_text({'title':'new'})])
        self.assertEqual(self.con.execute('SELECT count(*) FROM embedding_cache').fetchone()[0],0)

    def test_same_named_model_probe_change_invalidates_cache(self):
        text=e.public_text({'title':'Unemployment declines'})
        old=self.client();old.embed([text])
        def changed(request,timeout):
            response=self.service(request,timeout)
            if request.data and json.loads(request.data)['input']==[e.PROBE]:
                payload=json.loads(response.getvalue());payload['data'][0]['embedding']=[0,1,0,0,0,0]
                return bm.HypotheticalResponse(dumps(payload).encode())
            return response
        new=self.client(opener=changed);new.embed([text])
        self.assertNotEqual(old.identity,new.identity)
        self.assertEqual(new.hits,0)

    def test_partial_batch_failure_discards_semantic_results(self):
        bm.seed(self.con,DATA)
        def partial(request,timeout):
            if len(self.service.requests)>=3: raise OSError('HYPOTHETICAL batch outage')
            return self.service(request,timeout)
        baseline=discovery.discover(self.con,now=NOW,limit=100)
        result=discovery.discover(self.con,now=NOW,limit=100,embedding_client=self.client(opener=partial,batch_size=1,retries=0))
        self.assertEqual(result['candidates'],baseline['candidates'])
        self.assertEqual(result['embedding']['status'],'FALLBACK')
        self.assertEqual(self.con.execute('SELECT count(*) FROM embedding_cache').fetchone()[0],1)

    def test_bounds_sports_scope_and_human_rejection_remain(self):
        bm.seed(self.con,DATA)
        result=discovery.discover(self.con,now=NOW,embedding_client=self.client(max_items=1))
        self.assertTrue(result['embedding']['truncated'])
        self.assertEqual(result['embedding']['embedded'],[1,1])
        client=self.client()
        discovery.discover(self.con,now=NOW,sports_only=True,embedding_client=client)
        self.assertEqual(client.requests,0)
        pair=registry.propose(self.con,'HYPOTHETICAL-jobs','HYPOTHETICAL-jobs','HYPOTHETICAL reviewer',now=NOW)
        registry.decide(self.con,pair,'REJECTED','HYPOTHETICAL reviewer','rules differ',now=NOW)
        result=discovery.discover(self.con,now=NOW,limit=100,embedding_client=self.client())
        row=next(r for r in result['candidates'] if r['kalshi_id']=='HYPOTHETICAL-jobs')
        self.assertEqual(row['prior_reviews'][0]['status'],'REJECTED')
        self.assertFalse(row['equivalence_verified'])
        self.assertFalse(row['trading_authorized'])

    def test_refresh_orchestration_and_probe_cli(self):
        from types import SimpleNamespace
        bm.seed(self.con,DATA)
        with patch('predarb.discovery_cli.collect',return_value=SimpleNamespace(as_dict=lambda:{'status':'COMPLETE'})):
            result,code=discovery_cli.refresh(self.con,now=NOW,books=0,embedding_client=self.client())
        self.assertEqual(code,0)
        self.assertEqual(result['embedding']['status'],'READY')
        self.assertEqual(discovery.queue(self.con,now=NOW)['embedding_at_refresh']['status'],'READY')
        with patch('predarb.embeddings.from_environment',return_value=self.client()), redirect_stdout(StringIO()) as out:
            with patch('sys.argv',['predarb','discovery','embeddings-check','--db',self.path]):
                self.assertEqual(cli.main(),0)
        self.assertEqual(json.loads(out.getvalue())['dimensions'],6)
        with patch('predarb.embeddings.from_environment',return_value=self.client()), patch('predarb.registry.now_utc',return_value=NOW), redirect_stdout(StringIO()) as out:
            with patch('sys.argv',['predarb','discovery','refresh','--cached-catalogues','--db',self.path]):
                self.assertEqual(cli.main(),0)
        self.assertEqual(json.loads(out.getvalue())['embedding']['status'],'READY')

    def test_real_private_service_invalid_vector_replay_fails_closed(self):
        fixture=json.loads((bm.FIXTURE.parent/'embedding-invalid-live.json').read_text())
        responses=iter(fixture['responses'])
        def replay(*args,**kwargs):
            return bm.HypotheticalResponse(next(responses)['body'].encode())
        bm.seed(self.con,DATA)
        baseline=discovery.discover(self.con,now=NOW,limit=100)
        result=discovery.discover(self.con,now=NOW,limit=100,embedding_client=self.client(opener=replay))
        self.assertEqual(result['embedding']['status'],'FALLBACK')
        self.assertEqual(result['candidates'],baseline['candidates'])
        self.assertEqual(self.con.execute('SELECT count(*) FROM embedding_cache').fetchone()[0],0)
        values=json.loads(fixture['responses'][1]['body'])['data'][0]['embedding']
        self.assertEqual(len(values),1024)
        self.assertEqual(sum(x is None for x in values),14)

    def test_real_8b_probe_batch_and_cache_replay(self):
        import hashlib
        fixture=json.loads((bm.FIXTURE.parent/'embedding-8b-live.json').read_text())
        responses=iter(fixture['responses'])
        calls=[]
        def replay(request,timeout):
            item=next(responses)
            self.assertEqual(hashlib.sha256(item['body'].encode()).hexdigest(),item['sha256'])
            self.assertEqual(request.full_url.rsplit('/',1)[1],item['endpoint'].rsplit('/',1)[1])
            calls.append(request)
            return bm.HypotheticalResponse(item['body'].encode())
        client=self.client(opener=replay)
        values=client.embed(fixture['inputs'])
        self.assertEqual(client.model,'qwen3-embedding-8b')
        self.assertEqual(client.dimensions,4096)
        self.assertEqual([len(v) for v in values],[4096,4096])
        self.assertEqual(len(calls),3)
        cached=client.embed(fixture['inputs'])
        self.assertEqual(client.hits,2)
        self.assertEqual(len(calls),3)
        for actual,expected in zip(cached,values):
            self.assertLess(max(abs(a-b) for a,b in zip(actual,expected)),1e-12)
        self.assertEqual(self.con.execute('SELECT count(*) FROM embedding_cache').fetchone()[0],2)
        self.assertEqual(self.con.execute('SELECT count(*) FROM pairs').fetchone()[0],0)

    def test_non_sports_futures_reach_embedding_retrieval_and_unknowns_do_not(self):
        # HYPOTHETICAL markets using the real provider's generic type/category combination.
        bm.seed(self.con,DATA)
        for case in DATA['cases']:
            registry._record_instrument(self.con,'polymarket_us','HYPOTHETICAL-'+case['id'],
                {'title':case['right'],'description':'','category':'finance',
                 'sportsMarketType':'futures','sportsMarketTypeV2':'SPORTS_MARKET_TYPE_FUTURE',
                 'close_time':'2030-02-01T00:00:00Z'},observed_at=NOW.isoformat(),
                 available=True,hypothetical=True,now=NOW)
        result=discovery.discover(self.con,now=NOW,limit=100,embedding_client=self.client())
        self.assertEqual(result['embedding']['status'],'READY')
        self.assertEqual(result['embedding']['non_sports_eligible'],[6,9])
        self.assertEqual(result['embedding']['excluded_sports'],[0,0])
        self.assertEqual(len(result['candidates']),6)
        self.assertTrue(all(r['status']=='UNVERIFIED' and not r['trading_authorized'] for r in result['candidates']))

    def test_empty_embedding_report_separates_selection_from_completed_inference(self):
        # HYPOTHETICAL disjoint pools reproduce the reported one-sided selection.
        client=self.client(max_items=1)
        pools=[[{'features':{'sports':None}}, {'features':{'sports':None}}],
               [{'features':{'sports':{'supported':False}}}]]
        pairs,report=e.retrieve(self.con,pools,client)
        self.assertEqual(pairs,{})
        self.assertEqual(report['status'],'EMPTY')
        self.assertEqual(report['selected'],[1,0])
        self.assertEqual(report['embedded'],[0,0])
        self.assertEqual(report['excluded_sports'],[0,1])
        self.assertEqual(report['reason'],'NO_NON_SPORTS_MARKETS_ON_BOTH_VENUES')
        self.assertTrue(report['truncated'])
        self.assertEqual(client.requests,0)

    def test_local_http_protocol_integration(self):
        service=self.service
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): self.reply()
            def do_POST(self): self.reply()
            def reply(self):
                body=self.rfile.read(int(self.headers.get('Content-Length',0))) or None
                request=Request('https://hypothetical.invalid'+self.path,data=body)
                response=service(request,timeout=1)
                self.send_response(200);self.end_headers();self.wfile.write(response.read())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        transport=build_opener(ProxyHandler({}),e.NoRedirect())
        def local(request,timeout):
            # Injection is test-only: production Config always requires verified HTTPS.
            path=request.full_url.split('/v1',1)[1]
            return transport.open(Request(f'http://127.0.0.1:{server.server_port}/v1'+path,data=request.data,headers=request.headers),timeout=timeout)
        result=bm.benchmark(self.con,DATA,self.client(opener=local,batch_size=2))
        self.assertEqual(result['results']['embedding_assisted']['embedding']['status'],'READY')
        self.assertEqual(result['results']['embedding_assisted']['recall_at_k'],1)


if __name__=='__main__': unittest.main()
