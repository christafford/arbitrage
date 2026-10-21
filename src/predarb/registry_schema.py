"""Atomic schema-2 migration: rule evidence and human decisions, no execution data."""
M2_SCHEMA = """
CREATE TABLE rule_versions (
 id INTEGER PRIMARY KEY, venue TEXT NOT NULL, source_id TEXT NOT NULL,
 contract_sha256 TEXT NOT NULL, evidence_json TEXT NOT NULL,
 hypothetical INTEGER NOT NULL CHECK(hypothetical IN (0,1)), created_at TEXT NOT NULL,
 UNIQUE(venue,source_id,contract_sha256,hypothetical)
);
CREATE TABLE registry_instruments (
 venue TEXT NOT NULL, source_id TEXT NOT NULL, version_id INTEGER NOT NULL REFERENCES rule_versions(id),
 observed_at TEXT NOT NULL, observation_id INTEGER REFERENCES raw_observations(id),
 run_id INTEGER REFERENCES collection_runs(id), available INTEGER NOT NULL,
 PRIMARY KEY(venue,source_id)
);
CREATE TABLE supplement_versions (
 id INTEGER PRIMARY KEY, venue TEXT NOT NULL, source_id TEXT NOT NULL, kind TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, evidence_json TEXT NOT NULL, source_url TEXT NOT NULL,
 UNIQUE(venue,source_id,kind,content_sha256)
);
CREATE TABLE registry_supplements (
 venue TEXT NOT NULL, source_id TEXT NOT NULL, kind TEXT NOT NULL,
 version_id INTEGER NOT NULL REFERENCES supplement_versions(id),
 observation_id INTEGER NOT NULL REFERENCES raw_observations(id), observed_at TEXT NOT NULL,
 PRIMARY KEY(venue,source_id,kind)
);
CREATE TABLE rule_documents (
 id INTEGER PRIMARY KEY, venue TEXT NOT NULL, source_id TEXT NOT NULL, source_url TEXT NOT NULL,
 retrieved_at TEXT NOT NULL, imported_at TEXT NOT NULL, operator TEXT NOT NULL,
 raw_bytes BLOB NOT NULL, raw_sha256 TEXT NOT NULL, text_bytes BLOB NOT NULL,
 text_sha256 TEXT NOT NULL, hypothetical INTEGER NOT NULL CHECK(hypothetical IN (0,1))
);
CREATE TABLE document_heads (
 venue TEXT NOT NULL, source_id TEXT NOT NULL, source_url TEXT NOT NULL,
 document_id INTEGER NOT NULL REFERENCES rule_documents(id),
 PRIMARY KEY(venue,source_id,source_url)
);
CREATE TABLE pairs (
 id INTEGER PRIMARY KEY, kalshi_id TEXT NOT NULL, polymarket_us_id TEXT NOT NULL,
 hypothetical INTEGER NOT NULL CHECK(hypothetical IN (0,1)), created_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('UNVERIFIED','APPROVED','REJECTED','REVOKED','INVALIDATED','EXPIRED')),
 evidence_sha256 TEXT NOT NULL, review_json TEXT, reviewer TEXT, approved_at TEXT, expires_at TEXT, reason TEXT NOT NULL
);
CREATE UNIQUE INDEX pair_pending_unique ON pairs(kalshi_id,polymarket_us_id)
 WHERE status IN ('UNVERIFIED','APPROVED');
CREATE TABLE pair_audit (
 id INTEGER PRIMARY KEY, pair_id INTEGER REFERENCES pairs(id), ts_utc TEXT NOT NULL,
 actor TEXT NOT NULL, action TEXT NOT NULL, detail_json TEXT NOT NULL
);
CREATE TRIGGER pair_audit_no_update BEFORE UPDATE ON pair_audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER pair_audit_no_delete BEFORE DELETE ON pair_audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER rule_versions_no_update BEFORE UPDATE ON rule_versions BEGIN SELECT RAISE(ABORT,'rule versions are immutable'); END;
CREATE TRIGGER rule_versions_no_delete BEFORE DELETE ON rule_versions BEGIN SELECT RAISE(ABORT,'rule versions are immutable'); END;
CREATE TRIGGER supplement_versions_no_update BEFORE UPDATE ON supplement_versions BEGIN SELECT RAISE(ABORT,'supplement versions are immutable'); END;
CREATE TRIGGER supplement_versions_no_delete BEFORE DELETE ON supplement_versions BEGIN SELECT RAISE(ABORT,'supplement versions are immutable'); END;
CREATE TRIGGER rule_documents_no_update BEFORE UPDATE ON rule_documents BEGIN SELECT RAISE(ABORT,'rule documents are immutable'); END;
CREATE TRIGGER rule_documents_no_delete BEFORE DELETE ON rule_documents BEGIN SELECT RAISE(ABORT,'rule documents are immutable'); END;
"""
