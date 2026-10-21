import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def connect(path: str):
    dbpath = Path(path)
    dbpath.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(dbpath), timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=15000")
    con.executescript(SCHEMA)
    return con

def save_raw(con, venue, endpoint, payload):
    con.execute("INSERT INTO raw_observations(ts_utc,venue,endpoint,json_payload) VALUES(?,?,?,?)",
                (timestamp(), venue, endpoint, json.dumps(payload, separators=(",", ":"))))
    con.commit()

def save_example(con, result):
    con.execute("""INSERT INTO opportunities(ts_utc,pair_label,hypothetical,contracts,capital,profit,fee_assumption,reserve_assumption)
                   VALUES(?,?,1,?,?,?,?,?)""",
                (timestamp(), "EXAMPLE ONLY: manually assumed identical contracts", str(result.contracts),
                 str(result.capital), str(result.net_profit), "0.01 USD/pair", "0.005 USD/pair"))
    con.commit()
