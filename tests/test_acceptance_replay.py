"""Deterministic replay of complete REAL public US API acceptance collections."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from predarb import kalshi, polymarket_us as poly
from predarb.collector import collect
from predarb.provider import HttpClient
from predarb.store import connect
from predarb.validation import utc_time
from helpers import fixture, Replay, Response


class AcceptanceReplayTests(unittest.TestCase):
    def replay(self, adapter, prefix):
        capture = fixture(prefix + '-scoped-acceptance')
        source_run, frames = capture['run'], capture['responses']
        scope = json.loads(source_run['scope_json'])
        responses = []
        for frame in frames:
            self.assertEqual(hashlib.sha256(frame['body'].encode()).hexdigest(), frame['body_sha256'])
            self.assertEqual(frame['schema_version'], adapter.SCHEMA_VERSION)
            self.assertEqual(frame['status'], 200)
            utc_time(frame['retrieved_at'])
            responses.append(Response(frame['body'].encode(), frame['status'], frame['headers']))
        replay = Replay(*responses)
        clock = iter(frame['retrieved_at'] for frame in frames)
        with tempfile.TemporaryDirectory() as temp:
            with connect(str(Path(temp) / 'replay.sqlite3')) as db:
                client = HttpClient(db, adapter.VENUE, opener=replay, sleep=lambda delay: None,
                                    utc_now=lambda: next(clock))
                result = collect(db, adapter, page_size=scope['page_size'], max_pages=scope['max_pages'],
                                 books=scope['books'], scope=scope['filter'], client=client,
                                 now=utc_time(source_run['finished_at']))
                self.assertEqual([request.full_url for request, _ in replay.requests],
                                 [frame['url'] for frame in frames])
                self.assertEqual(replay.responses, [])
                self.assertEqual((result.status, result.pages, result.records, result.unique_records, result.duplicates),
                                 (source_run['status'], source_run['pages'], source_run['records'],
                                  source_run['unique_records'], source_run['duplicates']))
                self.assertEqual(result.status, 'COMPLETE')
                self.assertIsNone(result.next_page)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], len(frames))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM book_captures').fetchone()[0], scope['books'])
                self.assertEqual(db.execute("SELECT COUNT(*) FROM catalogue_entries WHERE verification != 'UNVERIFIED'").fetchone()[0], 0)
                entries = db.execute('SELECT source_id,rules_sha256 FROM catalogue_entries ORDER BY source_id').fetchall()
                books = db.execute('SELECT source_id,source_ts,freshness,liquidity FROM book_captures ORDER BY source_id').fetchall()
        return result.as_dict(), entries, books

    def test_kalshi_complete_live_capture_replays_identically(self):
        first = self.replay(kalshi, 'kalshi')
        self.assertEqual(first, self.replay(kalshi, 'kalshi'))
        self.assertEqual(first[0]['books'], 2)
        self.assertEqual({row[2] for row in first[2]}, {'UNKNOWN_SOURCE_TIME'})

    def test_polymarket_us_complete_live_capture_replays_identically(self):
        first = self.replay(poly, 'poly')
        self.assertEqual(first, self.replay(poly, 'poly'))
        self.assertEqual(first[0]['books'], 1)
        self.assertEqual({row[2] for row in first[2]}, {'FRESH'})
