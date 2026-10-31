"""Bounded genuine-text HTTP and persistent-index benchmark in NEW archives only."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import resource
import statistics
import time
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError

from predarb import embeddings as e, semantic as s
from predarb.store import connect, archive_response, validate_observation
from predarb.backups import readonly
from predarb.validation import dumps, load_json, utc_time
from m5i_evaluate import seed
from m5i_compatibility_evaluate import validate

ROOT = Path(__file__).resolve().parents[1]
PIN = '8f1b745674ea82993cc5211498d606a86627ecedb6776637daeaf66e42611204'
INSTRUCTION = 'Retrieve prediction market contracts about the same event, participants, outcome, threshold and time period as the query. Exclude merely related topics.'


def corpus64():
    corpus = json.loads((ROOT/'tests/fixtures/m5i-compatibility-genuine.json').read_text())
    validate(corpus)
    ids = {(r['venue'],r['source_id']) for r in corpus['instruments']}
    extra = json.loads((ROOT/'tests/fixtures/m5i-genuine-evaluation.json').read_text())
    # Older texts supplement throughput only, never live eligibility or quality labels.
    for row in extra['instruments']:
        if (row['venue'],row['source_id']) not in ids:
            corpus['instruments'].append(row); ids.add((row['venue'],row['source_id']))
        if len(corpus['instruments']) == 64: break
    if len(corpus['instruments']) != 64: raise ValueError('64 distinct genuine definitions required')
    for row in corpus['instruments']:
        if hashlib.sha256(row['body'].encode()).hexdigest() != row['body_sha256']:
            raise ValueError('source hash mismatch')
    return corpus


class Response(io.BytesIO):
    def __init__(self, body, status, headers):
        super().__init__(body); self.status=status; self.headers=headers


class MeasuredClient(e.Client):
    """HTTP timer ends after body receipt, before SQLite/archive/schema validation.

    HTTP includes TLS, network, server queue and inference. It is NOT GPU time.
    """
    def __init__(self, con, config, *, response_limit=4*1024*1024):
        self.response_limit=response_limit
        self.http=[]; self.calls=[]
        opener=build_opener(ProxyHandler({}),e.NoRedirect()).open
        def measured(request, timeout):
            started=time.perf_counter(); first=None; status=None; size=0
            try:
                try: response=opener(request,timeout=timeout)
                except HTTPError as exc: response=exc
                with response:
                    first=time.perf_counter()-started
                    status=response.status; headers=dict(response.headers)
                    body=response.read(self.response_limit+1); size=len(body)
                return Response(body,status,headers)
            finally:
                self.http.append(dict(route=request.full_url.rsplit('/',1)[-1],status=status,
                    headers_seconds=first,http_seconds=time.perf_counter()-started,bytes=size))
        super().__init__(con,config,opener=measured)

    def _request(self, route, payload=None):
        start=time.perf_counter(); n=len(self.http)
        try: return super()._request(route,payload)
        finally:
            elapsed=time.perf_counter()-start
            self.calls.append(dict(route=route,seconds=elapsed,
                archive_parse_and_client_seconds=max(0,elapsed-sum(x['http_seconds'] for x in self.http[n:]))))


def direct_large_batch(client,texts):
    """Isolated diagnostic only; production's 4 MiB response guard is unchanged."""
    if len(texts)!=64 or client.response_limit!=16*1024*1024:
        raise ValueError('bounded 64-text / 16 MiB diagnostic required')
    request=Request(client.base+'/embeddings',data=dumps({'model':client.model,'input':texts,
        'encoding_format':'float'}).encode(),headers={'Content-Type':'application/json'})
    with client.open(request,timeout=30) as response:
        body=response.read(client.response_limit+1);status=response.status;headers=response.headers
    truncated=len(body)>client.response_limit
    raw=archive_response(client.con,'embedding',request.full_url,body[:client.response_limit],status,headers,
        datetime.now(timezone.utc).isoformat(),e.VERSION,truncated=truncated)
    if status!=200 or truncated:
        validate_observation(client.con,raw,'REJECTED','HTTP_OR_SIZE_ERROR');raise e.EmbeddingError('HTTP_OR_SIZE_ERROR')
    return client._decode(load_json(body),raw,64,client.dimensions),raw


def large_diagnostic(directory,url):
    if not e.endpoint(url).split('/')[2].endswith('.ts.net'):raise ValueError('private Tailscale endpoint required')
    directory.mkdir(parents=True,exist_ok=False);corpus=corpus64();report=[]
    for method in ('existing','instruction'):
        with connect(str(directory/(method+'.sqlite3'))) as con:
            client=MeasuredClient(con,e.Config(url,timeout=30,retries=0),response_limit=16*1024*1024)
            row={'method':method,'batch_size':64,'response_limit_bytes':client.response_limit,
                 'production_compatible':False,'samples':[]};report.append(row)
            try:
                row['probes']=exact_probe(client)
                for repeat in range(3):
                    start=time.perf_counter();values,raw=direct_large_batch(client,texts_for(corpus,method))
                    seconds=time.perf_counter()-start
                    row['samples'].append({'seconds':seconds,'definitions_per_second':64/seconds,'raw':raw,'http':client.http[-1]})
                row['status']='MEASURED';row['median_definitions_per_second']=statistics.median(x['definitions_per_second'] for x in row['samples'])
            except (ValueError,OSError) as exc:row.update(status='FAILED',error=str(exc))
            (directory/'results.json').write_text(json.dumps(report,indent=2)+'\n')
            print(dumps(row),flush=True)
    return report


def exact_probe(client, pin=PIN):
    attempts=[]
    for _ in range(3):
        result=client.probe(); attempts.append(result)
        if result['identity']==pin: return attempts
    raise e.EmbeddingError('PINNED_MODEL_IDENTITY_MISMATCH')


def texts_for(corpus, method):
    if method not in ('existing','instruction'): raise ValueError('unknown benchmark method')
    texts=[e.public_text(load_json(r['body'])['market']) for r in corpus['instruments']]
    if method=='instruction':
        texts=[f'Instruct: {INSTRUCTION}\nQuery: {text}' if r['venue']=='polymarket_us' else text
               for r,text in zip(corpus['instruments'],texts)]
    return texts


def run(directory, url, repeats=3):
    if type(repeats)is not int or not 1<=repeats<=5: raise ValueError('repeats 1..5')
    if not e.endpoint(url).split('/')[2].endswith('.ts.net'): raise ValueError('private Tailscale endpoint required')
    directory.mkdir(parents=True,exist_ok=False)
    corpus=corpus64(); (directory/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
    report={'schema':'m5l-benchmark/v1','started_at':datetime.now(timezone.utc).isoformat(),
        'corpus_sha256':e.digest(dumps(corpus)),'definitions':64,'repeats':repeats,
        'production_index_modified':False,'trading_authorized':False,
        'sampling':'Purposive genuine development definitions, mixed sports/macroeconomics/politics; not catalogue-representative. Four older definitions throughput-only.',
        'gpu_inference_seconds':None,'gpu_offload':None,'gpu_vram':None,'server_cpu':None,
        'host_measurement_blocker':'No verified inference-host SSH/log access. HTTP time includes inference; do not subtract health RTT to invent GPU time.',
        'direct':[],'persistent':[]}
    output=directory/'results.json'
    def save(): output.write_text(json.dumps(report,indent=2)+'\n')
    save()
    for method in ('existing','instruction'):
        texts=texts_for(corpus,method)
        # Same 64 descriptions for each size; no client cache on direct requests.
        for batch in (8,16,32,64):
            with connect(str(directory/f'{method}-b{batch}.sqlite3')) as con:
                client=MeasuredClient(con,e.Config(url,timeout=30,retries=0,batch_size=batch,max_requests=100))
                row={'method':method,'batch_size':batch,'samples':[],
                    'namespace':e.digest(dumps([PIN,method,INSTRUCTION if method=='instruction' else e.TEXT_VERSION]))}
                report['direct'].append(row)
                try:
                    tick=time.perf_counter(); row['probes']=exact_probe(client);row['probe_seconds']=time.perf_counter()-tick
                    all_vectors=None
                    for repeat in range(repeats):
                        start=time.perf_counter(); cpu=time.process_time(); n=len(client.http);values=[];raw_ids=[]
                        for offset in range(0,64,batch):
                            payload,raw=client._request('/embeddings',{'model':client.model,'input':texts[offset:offset+batch],'encoding_format':'float'})
                            raw_ids.append(raw); values.extend(client._decode(payload,raw,batch,client.dimensions))
                        elapsed=time.perf_counter()-start
                        row['samples'].append(dict(repeat=repeat,seconds=elapsed,definitions_per_second=64/elapsed,
                            client_cpu_seconds=time.process_time()-cpu,http=client.http[n:],raw_observations=raw_ids))
                        all_vectors=values; save()
                    row['median_definitions_per_second']=statistics.median(x['definitions_per_second'] for x in row['samples'])
                    row['status']='MEASURED'
                    # Preserve latest per-input vectors/provenance for exact-corpus evaluation.
                    (directory/f'{method}-b{batch}-vectors.json').write_text(dumps({'identity':client.identity,
                        'namespace':row['namespace'],'method':method,'vectors':all_vectors,
                        'source_ids':[[r['venue'],r['source_id']] for r in corpus['instruments']],
                        'text_hashes':[e.digest(t) for t in texts]})+'\n')
                except (ValueError,OSError) as exc:row.update(status='FAILED',error=str(exc))
                row['http']=client.http;row['client_calls']=client.calls
                save(); print(dumps({'direct':method,'batch':batch,'status':row['status'],'rate':row.get('median_definitions_per_second')}),flush=True)
    # Real production persistence path; freshly seeded sources preserve original receipts.
    # Use only current eligible rows; never renew older text receipts for worker throughput.
    quality=json.loads((ROOT/'tests/fixtures/m5i-compatibility-genuine.json').read_text())
    for batch in (8,16,32,64):
        source_path=str(directory/f'worker-b{batch}-source.sqlite3')
        with connect(source_path) as seeded:seed(seeded,quality)
        with closing(readonly(source_path)) as source,connect(str(directory/f'worker-b{batch}-index.sqlite3')) as index:
            s.sync(source,index)
            client=MeasuredClient(index,e.Config(url,timeout=30,retries=0,batch_size=batch,max_requests=100))
            start=time.perf_counter(); cpu=time.process_time()
            measured=s.index_batch(index,client,budgets={'kalshi':64,'polymarket_us':64},seconds=600,texts_per_second=100,expected_identity=PIN)
            measured.update(batch_size=batch,client_cpu_seconds=time.process_time()-cpu,http=client.http,client_calls=client.calls,
                            persistent_vectors=index.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0],
                            source_coverage=s.coverage(source,index))
            measured['http_seconds']=sum(x['http_seconds'] for x in client.http)
            measured['non_http_seconds']=measured['elapsed_seconds']-measured['http_seconds']
            report['persistent'].append(measured);save();print(dumps({'persistent_batch':batch,'rate':measured['texts_per_second'],'status':measured['status']}),flush=True)
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    report['client_peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    save();return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--url',required=True);p.add_argument('--repeats',type=int,default=3);a=p.parse_args()
    run(a.directory,a.url,a.repeats)

if __name__=='__main__':main()
