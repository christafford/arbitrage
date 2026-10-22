"""Single-writer SQLite archive and versioned M1 catalogue evidence."""
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .validation import dumps

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_observations (
 id INTEGER PRIMARY KEY, ts_utc TEXT NOT NULL, venue TEXT NOT NULL,
 endpoint TEXT NOT NULL, json_payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS raw_observations_venue_ts ON raw_observations(venue,ts_utc);
CREATE TABLE IF NOT EXISTS opportunities (
 id INTEGER PRIMARY KEY, ts_utc TEXT NOT NULL, pair_label TEXT NOT NULL,
 hypothetical INTEGER NOT NULL CHECK(hypothetical=1),
 contracts TEXT NOT NULL, capital TEXT NOT NULL, profit TEXT NOT NULL,
 fee_assumption TEXT NOT NULL, reserve_assumption TEXT NOT NULL
);
"""
M1_SCHEMA = """
CREATE TABLE collection_runs (
 id INTEGER PRIMARY KEY, venue TEXT NOT NULL, schema_version TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 scope_json TEXT NOT NULL, pages INTEGER NOT NULL DEFAULT 0,
 records INTEGER NOT NULL DEFAULT 0, unique_records INTEGER NOT NULL DEFAULT 0,
 duplicates INTEGER NOT NULL DEFAULT 0, next_page TEXT, error TEXT
);
CREATE TABLE catalogue_entries (
 run_id INTEGER NOT NULL REFERENCES collection_runs(id), source_id TEXT NOT NULL,
 observation_id INTEGER NOT NULL REFERENCES raw_observations(id), source_ts TEXT,
 metadata_json TEXT NOT NULL, rules_json TEXT NOT NULL, rules_sha256 TEXT NOT NULL,
 verification TEXT NOT NULL CHECK(verification='UNVERIFIED'),
 PRIMARY KEY(run_id,source_id)
);
CREATE TABLE book_captures (
 observation_id INTEGER PRIMARY KEY REFERENCES raw_observations(id),
 run_id INTEGER NOT NULL REFERENCES collection_runs(id), source_id TEXT NOT NULL,
 source_ts TEXT, freshness TEXT NOT NULL, liquidity TEXT NOT NULL,
 verification TEXT NOT NULL CHECK(verification='UNVERIFIED')
);
"""


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def connect(path: str):
    dbpath = Path(path)
    dbpath.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(dbpath), timeout=15, factory=Connection)
    try:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA busy_timeout=15000')
        version = con.execute('PRAGMA user_version').fetchone()[0]
        if version > 6:
            raise ValueError(f'unsupported database schema version {version}')
        con.executescript(SCHEMA)
        if version == 0:
            columns = {
                'raw_body': 'BLOB', 'body_sha256': 'TEXT', 'http_status': 'INTEGER',
                'headers_json': 'TEXT', 'schema_version': 'TEXT', 'source_ts': 'TEXT',
                'validation_status': "TEXT NOT NULL DEFAULT 'LEGACY_UNVALIDATED'",
                'validation_error': 'TEXT', 'truncated': 'INTEGER NOT NULL DEFAULT 0',
            }
            # One atomic migration; existing starter observations remain explicitly unvalidated.
            sql = 'BEGIN IMMEDIATE;\n' + '\n'.join(
                f'ALTER TABLE raw_observations ADD COLUMN {name} {kind};'
                for name, kind in columns.items())
            con.executescript(sql + '\n' + M1_SCHEMA + '\nPRAGMA user_version=1;\nCOMMIT;')
        if version < 2:
            from .registry_schema import M2_SCHEMA
            con.executescript('BEGIN IMMEDIATE;\n' + M2_SCHEMA + '\nPRAGMA user_version=2;\nCOMMIT;')
            from .registry import sync_catalogue
            sync_catalogue(con)
        if version < 3:
            from .book_store import M3_SCHEMA
            con.executescript('BEGIN IMMEDIATE;\n' + M3_SCHEMA + '\nPRAGMA user_version=3;\nCOMMIT;')
        if version < 4:
            from .research_schema import M4_SCHEMA
            con.executescript('BEGIN IMMEDIATE;\n' + M4_SCHEMA + '\nPRAGMA user_version=4;\nCOMMIT;')
        if version < 5:
            from .paper_schema import M5_SCHEMA
            con.executescript('BEGIN IMMEDIATE;\n' + M5_SCHEMA + '\nPRAGMA user_version=5;\nCOMMIT;')
        if version < 6:
            from .discovery import SCHEMA as DISCOVERY_SCHEMA
            con.executescript('BEGIN IMMEDIATE;\n' + DISCOVERY_SCHEMA + '\nPRAGMA user_version=6;\nCOMMIT;')
        return con
    except BaseException:
        con.close()
        raise


def save_raw(con, venue, endpoint, payload):
    con.execute('INSERT INTO raw_observations(ts_utc,venue,endpoint,json_payload) VALUES(?,?,?,?)',
                (timestamp(), venue, endpoint, dumps(payload)))
    con.commit()


def archive_response(con, venue, endpoint, body, status, headers, received_at, schema_version, *, truncated=False):
    # Cookies and infrastructure identifiers are deliberately excluded from the archive.
    safe_headers = {key.lower(): value for key, value in headers.items()
                    if key.lower() in {'date', 'content-type', 'retry-after', 'etag', 'last-modified'}}
    cursor = con.execute('''INSERT INTO raw_observations
        (ts_utc,venue,endpoint,json_payload,raw_body,body_sha256,http_status,headers_json,
         schema_version,validation_status,truncated) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (received_at, venue, endpoint, body.decode('utf-8', errors='replace'), body,
         hashlib.sha256(body).hexdigest(), status, dumps(safe_headers), schema_version,
         'REJECTED' if truncated else 'PENDING', int(truncated)))
    con.commit()
    return cursor.lastrowid


def validate_observation(con, observation_id, status, error, source_ts=None):
    con.execute('''UPDATE raw_observations SET validation_status=?, validation_error=?,
                   source_ts=? WHERE id=?''', (status, error, source_ts, observation_id))
    con.commit()


def start_run(con, venue, schema_version, scope):
    cursor = con.execute('''INSERT INTO collection_runs(venue,schema_version,started_at,status,scope_json)
                            VALUES(?,?,?,'RUNNING',?)''', (venue, schema_version, timestamp(), dumps(scope)))
    con.commit()
    return cursor.lastrowid


def update_run(con, run_id, *, status, pages, records, unique, next_page, error=None):
    con.execute('''UPDATE collection_runs SET status=?,pages=?,records=?,unique_records=?,duplicates=?,
                   next_page=?,error=?,finished_at=? WHERE id=?''',
                (status, pages, records, unique, records - unique, next_page, error,
                 None if status == 'RUNNING' else timestamp(), run_id))
    con.commit()
    if status in {'FAILED', 'INTERRUPTED'}:
        from .registry import invalidate_failed_collection
        invalidate_failed_collection(con, run_id, status)


def save_entry(con, run_id, observation, source_id, metadata, rules, source_ts):
    rules_json = dumps(rules)
    con.execute('''INSERT INTO catalogue_entries VALUES(?,?,?,?,?,?,?,'UNVERIFIED')
                   ON CONFLICT(run_id,source_id) DO UPDATE SET observation_id=excluded.observation_id,
                   source_ts=excluded.source_ts,metadata_json=excluded.metadata_json,
                   rules_json=excluded.rules_json,rules_sha256=excluded.rules_sha256''',
                (run_id, source_id, observation.id, source_ts, dumps(metadata), rules_json,
                 hashlib.sha256(rules_json.encode()).hexdigest()))
    con.commit()
    from .registry import observe_catalogue
    observe_catalogue(con, run_id, observation.id, source_id, metadata, rules)


def save_book(con, run_id, observation, source_id, source_ts, freshness, liquidity):
    con.execute("INSERT INTO book_captures VALUES(?,?,?,?,?,?, 'UNVERIFIED')",
                (observation.id, run_id, source_id, source_ts, freshness, liquidity))
    validate_observation(con, observation.id, 'VALID', None, source_ts)


def save_example(con, result):
    con.execute('''INSERT INTO opportunities(ts_utc,pair_label,hypothetical,contracts,capital,profit,fee_assumption,reserve_assumption)
                   VALUES(?,?,1,?,?,?,?,?)''',
                (timestamp(), 'EXAMPLE ONLY: manually assumed identical contracts', str(result.contracts),
                 str(result.capital), str(result.net_profit), '0.01 USD/pair', '0.005 USD/pair'))
    con.commit()
