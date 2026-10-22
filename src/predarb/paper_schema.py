"""M5 immutable paper and local operational evidence; no exchange order records."""
M5_SCHEMA = """
CREATE TABLE paper_tick_inputs (
 id INTEGER PRIMARY KEY, imported_at TEXT NOT NULL, raw_bytes BLOB NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE paper_intents (
 id INTEGER PRIMARY KEY, evaluation_id INTEGER NOT NULL REFERENCES research_evaluations(id),
 created_at TEXT NOT NULL, mode TEXT NOT NULL, policy_json TEXT NOT NULL, policy_sha256 TEXT NOT NULL,
 input_json TEXT NOT NULL, input_sha256 TEXT NOT NULL, UNIQUE(evaluation_id,policy_sha256)
);
CREATE TABLE paper_comparisons (
 id INTEGER PRIMARY KEY, intent_id INTEGER NOT NULL REFERENCES paper_intents(id), evaluated_at TEXT NOT NULL,
 input_key TEXT NOT NULL, input_json TEXT NOT NULL, result_json TEXT NOT NULL, sha256 TEXT NOT NULL,
 UNIQUE(intent_id,input_key)
);
CREATE TABLE ops_events (
 id INTEGER PRIMARY KEY, ts_utc TEXT NOT NULL, severity TEXT NOT NULL, action TEXT NOT NULL, detail_json TEXT NOT NULL
);
CREATE TABLE ops_checks (
 id INTEGER PRIMARY KEY, ts_utc TEXT NOT NULL, session_id INTEGER NOT NULL REFERENCES research_sessions(id),
 report_json TEXT NOT NULL
);
"""
for table in ('paper_tick_inputs', 'paper_intents', 'paper_comparisons', 'ops_events', 'ops_checks'):
    for operation in ('UPDATE', 'DELETE'):
        M5_SCHEMA += f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'paper/ops evidence is immutable'); END;\n"
