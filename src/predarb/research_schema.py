"""M4 schema: immutable fee evidence and summaries, expirable derived detail only."""
M4_SCHEMA = """
CREATE TABLE fee_imports (
 id INTEGER PRIMARY KEY, imported_at TEXT NOT NULL, raw_bytes BLOB NOT NULL,
 sha256 TEXT NOT NULL, status TEXT NOT NULL, error TEXT, venue TEXT, source_id TEXT, side TEXT
);
CREATE TABLE fee_documents (
 id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES fee_imports(id),
 source_url TEXT NOT NULL, retrieved_at TEXT NOT NULL, raw_bytes BLOB NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE fee_profiles (
 id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES fee_imports(id),
 venue TEXT NOT NULL, source_id TEXT NOT NULL, side TEXT NOT NULL,
 reviewed_at TEXT NOT NULL, expires_at TEXT NOT NULL, hypothetical INTEGER NOT NULL,
 operator TEXT NOT NULL, profile_json TEXT NOT NULL, sha256 TEXT NOT NULL
);
CREATE INDEX fee_profile_lookup ON fee_profiles(venue,source_id,side,id);
CREATE TABLE research_sessions (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, target_end TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('LIVE_READ_ONLY','HYPOTHETICAL_REPLAY')),
 config_json TEXT NOT NULL, interval_seconds INTEGER NOT NULL
);
CREATE TABLE research_cycles (
 id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES research_sessions(id),
 evaluated_at TEXT NOT NULL, recorded_at TEXT NOT NULL, status TEXT NOT NULL,
 summary_json TEXT NOT NULL, UNIQUE(session_id,evaluated_at)
);
CREATE TABLE research_evaluations (
 id INTEGER PRIMARY KEY, cycle_id INTEGER NOT NULL REFERENCES research_cycles(id),
 pair_id INTEGER NOT NULL REFERENCES pairs(id), evaluated_at TEXT NOT NULL,
 status TEXT NOT NULL, reasons_json TEXT NOT NULL, summary_json TEXT NOT NULL,
 detail_sha256 TEXT NOT NULL
);
CREATE INDEX research_eval_pair ON research_evaluations(pair_id,id);
CREATE TABLE research_details (
 evaluation_id INTEGER PRIMARY KEY REFERENCES research_evaluations(id), detail_json TEXT NOT NULL
);
CREATE TABLE research_audit (
 id INTEGER PRIMARY KEY, ts_utc TEXT NOT NULL, action TEXT NOT NULL, detail_json TEXT NOT NULL
);
CREATE TABLE research_replays (
 id INTEGER PRIMARY KEY, imported_at TEXT NOT NULL, raw_bytes BLOB NOT NULL, sha256 TEXT NOT NULL
);
"""
for table in ('fee_documents', 'fee_profiles', 'research_sessions', 'research_cycles', 'research_evaluations', 'research_audit', 'research_replays'):
    for operation in ('UPDATE', 'DELETE'):
        M4_SCHEMA += f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'research evidence is immutable'); END;\n"
M4_SCHEMA += "CREATE TRIGGER fee_import_bytes_immutable BEFORE UPDATE OF raw_bytes,sha256 ON fee_imports BEGIN SELECT RAISE(ABORT,'fee bytes are immutable'); END;"
