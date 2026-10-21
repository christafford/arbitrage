"""CLI exit codes and persistence under HYPOTHETICAL offline transport scenarios."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from predarb import cli
from predarb.provider import HttpClient
from predarb.store import connect
from helpers import Replay, real_response, Response


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'x.sqlite3')

    def invoke(self, *args):
        out, err = StringIO(), StringIO()
        with patch('sys.argv', ['predarb', *args, '--db', self.path]), redirect_stdout(out), redirect_stderr(err):
            status = cli.main()
        return status, out.getvalue(), err.getvalue()

    def test_demo_report_and_no_realized_profit(self):
        status, out, _ = self.invoke('demo')
        self.assertEqual(status, 0)
        self.assertIn('HYPOTHETICAL', out)
        self.assertIn('modeled_profit=$9.000', out)
        status, out, _ = self.invoke('report')
        self.assertEqual(status, 0)
        self.assertIn('NOT realized P&L: $9.00', out)
        self.assertIn('UNVERIFIED', out)

    def test_collectors_partial_complete_error_and_interrupted_exit_codes(self):
        cases = [
            ('collect-kalshi', [real_response('kalshi-page')], 2, 'PARTIAL'),
            ('collect-polymarket-us', [Response(b'{"markets":[]}')], 0, 'COMPLETE'),
            ('collect-polymarket-us', [Response(b'{}', 401)], 1, 'FAILED'),
            ('collect-polymarket-us', [KeyboardInterrupt()], 130, 'INTERRUPTED'),
        ]
        for command, responses, expected_code, expected_status in cases:
            with self.subTest(command=command, status=expected_status):
                replay = Replay(*responses)
                def factory(con, venue):
                    return HttpClient(con, venue, opener=replay, sleep=lambda delay: None)
                with patch('predarb.collector.HttpClient', factory):
                    code, out, err = self.invoke(command, '--limit', '2', '--max-pages', '1', '--books', '0')
                self.assertEqual(code, expected_code)
                with connect(self.path) as db:
                    self.assertEqual(db.execute('SELECT status FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()[0], expected_status)
                self.assertNotIn('Traceback', err)
