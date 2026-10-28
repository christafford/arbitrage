"""Hypothetical operational scheduling; no live venue or inference requests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from predarb.store import connect, start_run, update_run

spec = importlib.util.spec_from_file_location('m5i_run', Path(__file__).parents[1] / 'scripts/m5i_run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.sqlite3'
        self.index = self.root / 'index.sqlite3'
        with connect(self.source):
            pass
        with connect(self.index):
            pass
        self.config = dict(directory=str(self.root), source=str(self.source), index=str(self.index),
                           ends_at='2099-01-01T00:00:00+00:00')

    def test_collection_resumes_partial_then_waits_after_both_complete(self):
        run = runner.Run(self.config, 'collection')
        with patch.object(run, 'invoke', side_effect=[dict(pages=20,status='PARTIAL'),
                                                     dict(pages=2,status='COMPLETE')]):
            run.collection_step()
        reopened = runner.Run(self.config, 'collection')
        with patch.object(reopened, 'invoke', return_value=dict(pages=23,status='COMPLETE')) as call:
            reopened.collection_step()
            self.assertEqual(call.call_count, 1)
            self.assertIn('kalshi', call.call_args.args)
        self.assertEqual(reopened.saved['completed_rounds'], 1)
        self.assertGreater(reopened.saved['next_due'], time.time() + 21000)
        with patch.object(reopened, 'invoke') as call, patch.object(reopened, 'pause'):
            reopened.collection_step()
            call.assert_not_called()

    def test_page_cap_and_fixed_deadline_survive_restarts(self):
        run = runner.Run(self.config, 'collection')
        run.saved['kalshi_pages'] = 2000
        run.save()
        with self.assertRaisesRegex(RuntimeError, 'ceiling'):
            runner.Run(self.config, 'collection').collection_step()
        expired = dict(self.config, ends_at='2000-01-01T00:00:00+00:00')
        run = runner.Run(expired, 'semantic')
        self.assertEqual(run.run(), 0)
        self.assertEqual(json.loads((self.root/'semantic-status.json').read_text())['state'], 'STOPPED')

    def test_outage_still_retrieves_and_reports_then_backs_off(self):
        run = runner.Run(self.config, 'semantic')
        run.saved['synced_generation'] = [1,2]
        worker = dict(status='FALLBACK', completed={'kalshi':0,'polymarket_us':0})
        with patch.object(runner, 'complete_generation', return_value=[1,2]), \
             patch.object(run, 'invoke', side_effect=[worker, {}, {'venues':{}}]) as call, \
             patch.object(run, 'pause') as pause:
            run.semantic_step()
        self.assertEqual([c.args[0] for c in call.call_args_list], ['index-work','index-retrieve','index-coverage'])
        pause.assert_called_once_with(300)

    def test_changed_generation_requires_completed_sync(self):
        run = runner.Run(self.config, 'semantic')
        with patch.object(runner, 'complete_generation', side_effect=[[1,2],None]), \
             patch.object(run, 'invoke', side_effect=[{'scan_complete':False},{'scan_complete':True}]) as call:
            run.semantic_step()
        self.assertEqual([c.args[0] for c in call.call_args_list], ['index-sync','index-sync'])
        self.assertNotIn('synced_generation', run.saved)
        with patch.object(runner, 'complete_generation', return_value=None), \
             patch.object(run, 'invoke') as call, patch.object(run, 'pause'):
            run.semantic_step()
            call.assert_not_called()

    def test_generation_rejects_partial_failed_and_running_catalogues(self):
        with connect(self.source) as con:
            ids = []
            for venue in ('kalshi','polymarket_us'):
                ident = start_run(con, venue, 'HYPOTHETICAL', {'filter':None})
                update_run(con, ident, status='COMPLETE',pages=1,records=1,unique=1,next_page=None)
                ids.append(ident)
            self.assertEqual(runner.complete_generation(self.source), ids)
            for status in ('PARTIAL','RUNNING','FAILED','INTERRUPTED'):
                update_run(con, ids[0],status=status,pages=1,records=1,unique=1,next_page='cursor')
                self.assertIsNone(runner.complete_generation(self.source))

    def test_three_failures_stop_lane_without_unbounded_retries(self):
        run = runner.Run(self.config, 'collection')
        with patch.object(run, 'guard'), patch.object(run, 'pause') as pause, \
             patch.object(run, 'collection_step', side_effect=RuntimeError('HYPOTHETICAL failure')) as step:
            self.assertEqual(run.run(), 1)
        self.assertEqual(step.call_count, 3)
        self.assertEqual([c.args[0] for c in pause.call_args_list], [60,120])

    def test_space_guard_refuses_low_disk(self):
        run = runner.Run(self.config, 'semantic')
        with patch.object(runner.shutil, 'disk_usage', return_value=type('Disk', (), {'free':1})()):
            with self.assertRaisesRegex(RuntimeError, 'free disk'):
                run.guard()

    def test_real_child_logs_and_readonly_coverage_smoke(self):
        from predarb.semantic import initialize
        with connect(self.source) as source, connect(self.index) as index:
            initialize(index, source)
        run = runner.Run(self.config, 'semantic')
        with patch.object(run, 'guard'):
            report = run.invoke('index-coverage')
        self.assertEqual(report['venues']['kalshi']['source_total'], 0)
        self.assertEqual(len(list(self.root.glob('semantic-*-index-coverage.json'))), 1)
