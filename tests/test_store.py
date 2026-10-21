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
