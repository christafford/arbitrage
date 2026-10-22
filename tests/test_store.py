import tempfile
import unittest
from pathlib import Path
from predarb.store import connect, save_raw

class StorageTests(unittest.TestCase):
    def test_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/"x.sqlite")
            with connect(path) as db:
                save_raw(db,"kalshi","https://example.invalid",{"a": 2})
            with connect(path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_observations").fetchone()[0],1)

    def test_migration_preserves_legacy_observations(self):
        import sqlite3
        from predarb.store import SCHEMA
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'legacy.sqlite3')
            old = sqlite3.connect(path)
            old.executescript(SCHEMA)
            old.execute("INSERT INTO raw_observations VALUES(1,'2026-01-01T00:00:00Z','kalshi','https://example.invalid','{}')")
            old.commit()
            old.close()
            with connect(path) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 7)
                self.assertEqual(db.execute('SELECT id,validation_status,raw_body FROM raw_observations').fetchone(),
                                 (1, 'LEGACY_UNVALIDATED', None))
            with connect(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], 1)

    def test_future_migration_rejected_and_connections_close(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'future.sqlite3')
            with connect(path) as db:
                db.execute('PRAGMA user_version=8')
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute('SELECT 1')
            with self.assertRaisesRegex(ValueError, 'unsupported database schema'):
                connect(path)
