"""Page-bounded, resumable public catalogue walks. No inference or book requests."""
import hashlib
import json
from .collector import CollectionResult
from .provider import HttpClient
from .store import start_run, save_entry, update_run
from .validation import SchemaError, dumps

SCHEMA = '''
CREATE TABLE IF NOT EXISTS catalogue_walk_pages (
 run_id INTEGER NOT NULL REFERENCES collection_runs(id), page INTEGER NOT NULL,
 fingerprint TEXT NOT NULL, next_page TEXT,
 PRIMARY KEY(run_id,page), UNIQUE(run_id,fingerprint)
);
CREATE INDEX IF NOT EXISTS catalogue_observation_source ON catalogue_entries(observation_id,source_id);
CREATE INDEX IF NOT EXISTS registry_version_lookup ON registry_instruments(version_id);
'''


def walk(con, adapter, *, page_size=200, max_pages=20, client=None, restart=False):
    if not 1<=page_size<=1000 or not 1<=max_pages<=1000:raise ValueError('catalogue bounds: page size/pages 1..1000')
    latest=con.execute('''SELECT id,status,scope_json,pages,records,next_page FROM collection_runs
        WHERE venue=? AND json_extract(scope_json,'$.walker')='m5i-v1' ORDER BY id DESC LIMIT 1''',(adapter.VENUE,)).fetchone()
    if latest and latest[1]!='COMPLETE' and not restart:
        run,status,scope,pages,records,continuation=latest
        if json.loads(scope)['page_size']!=page_size:raise ValueError('resume requires original page size; use explicit restart')
    else:
        run=start_run(con,adapter.VENUE,adapter.SCHEMA_VERSION,
                      {'filter':None,'page_size':page_size,'walker':'m5i-v1','books':0})
        pages=records=0;continuation=None
    unique=con.execute('SELECT unique_records FROM collection_runs WHERE id=?',(run,)).fetchone()[0]
    client=client or HttpClient(con,adapter.VENUE,interval=1)
    try:
        update_run(con,run,status='RUNNING',pages=pages,records=records,unique=unique,next_page=continuation)
        for _ in range(max_pages):
            def validate(data):
                adapter.validate_page(data)
                if len(data['markets'])>page_size:raise SchemaError('provider exceeded page size')
            observation=client.get(adapter.page_url(page_size,continuation,None),adapter.SCHEMA_VERSION,validate)
            markets=observation.data['markets']
            fingerprint=hashlib.sha256(dumps(markets).encode()).hexdigest()
            following=adapter.next_page(observation.data,continuation,page_size)
            if con.execute('SELECT 1 FROM catalogue_walk_pages WHERE run_id=? AND fingerprint=?',(run,fingerprint)).fetchone():
                raise SchemaError('pagination repeated a page')
            if following is not None and (following==continuation or not markets or con.execute(
                    'SELECT 1 FROM catalogue_walk_pages WHERE run_id=? AND next_page=?',(run,following)).fetchone()):
                raise SchemaError('pagination did not advance')
            for market in markets:
                save_entry(con,run,observation,market[adapter.ID_FIELD],market,adapter.rules(market),market.get(adapter.TIME_FIELD))
            actual_unique=con.execute('SELECT count(*) FROM catalogue_entries WHERE run_id=?',(run,)).fetchone()[0]
            if following is not None and actual_unique==unique:
                raise SchemaError('pagination added no new identities')
            unique=actual_unique
            # Entries/raw evidence may precede this commit. If interrupted there,
            # replaying the old cursor overwrites entries safely before advancing.
            con.execute('INSERT INTO catalogue_walk_pages VALUES(?,?,?,?)',(run,pages,fingerprint,following))
            pages+=1;records+=len(markets);continuation=following
            update_run(con,run,status='RUNNING',pages=pages,records=records,unique=unique,next_page=continuation)
            if following is None:break
        status='COMPLETE' if continuation is None else 'PARTIAL'
        update_run(con,run,status=status,pages=pages,records=records,unique=unique,next_page=continuation)
        return CollectionResult(run,adapter.VENUE,status,pages,records,unique,records-unique,continuation,0)
    except BaseException as exc:
        con.rollback()
        # Reload the durable checkpoint, including an interruption in the commit.
        pages,records,unique,continuation=con.execute('SELECT pages,records,unique_records,next_page FROM collection_runs WHERE id=?',(run,)).fetchone()
        # A partially ingested page must not inflate the accepted page counters.
        update_run(con,run,status='INTERRUPTED' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'FAILED',
                   pages=pages,records=records,unique=min(unique,records),next_page=continuation,error=str(exc) or type(exc).__name__)
        raise
