"""Discovery tests use isolated HYPOTHETICAL inputs and offline provider replay."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from predarb import cli, discovery as d, discovery_cli, kalshi, polymarket_us, registry
from predarb.provider import HttpClient, Observation
from predarb.store import connect, archive_response, validate_observation, start_run, save_book
from predarb.validation import dumps, utc_time
from helpers import fixture, payload, Replay, Response

DATA = fixture('discovery-hypothetical')
NOW = utc_time(DATA['clock'])
K, P = 'HYPOTHETICAL-K', 'HYPOTHETICAL-P'


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'test.sqlite3')
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        self.seed('kalshi', K)
        self.seed('polymarket_us', P)

    def seed(self, venue, source_id, contract=None, *, at=NOW, available=True):
        registry._record_instrument(self.db, venue, source_id, contract or DATA[venue],
                                    observed_at=at.isoformat(), available=available,
                                    hypothetical=True, now=NOW)

    def search(self, **kwargs):
        return d.discover(self.db, now=NOW, **kwargs)

    def book(self, venue, source_id, *, quantity='10', at=NOW, source_at=None, invalid=False, state='MARKET_STATE_OPEN'):
        adapter = kalshi if venue == 'kalshi' else polymarket_us
        data = payload('kalshi-book-live' if venue == 'kalshi' else 'poly-book-live')
        if venue == 'kalshi':
            data['orderbook_fp'] = {'yes_dollars': [['0.4', quantity]], 'no_dollars': [['0.5', quantity]]}
        else:
            data['marketData'].update(state=state, marketSlug=source_id, transactTime=(source_at or at).isoformat(),
                                      bids=[{'px': {'value': '0.4', 'currency': 'USD'}, 'qty': quantity}],
                                      offers=[{'px': {'value': '0.5', 'currency': 'USD'}, 'qty': quantity}])
            if invalid:
                data['marketData']['offers'][0]['px']['value'] = '2'
        raw = archive_response(self.db, venue, adapter.book_url(source_id), dumps(data).encode(), 200,
                               {'Content-Type': 'application/json'}, at.isoformat(), adapter.SCHEMA_VERSION)
        validate_observation(self.db, raw, 'VALID', None)
        run = start_run(self.db, venue, adapter.SCHEMA_VERSION, {})
        save_book(self.db, run, Observation(raw, adapter.book_url(source_id), at.isoformat(), data),
                  source_id, None if venue == 'kalshi' else (source_at or at).isoformat(), 'FRESH', 'TWO_SIDED')
        return raw

    def test_normalized_subject_dates_thresholds_and_descriptions(self):
        report = self.search()
        row = report['candidates'][0]
        self.assertEqual(row['signals']['dates'], 'MATCH')
        self.assertEqual(row['signals']['thresholds'], 'MATCH')
        self.assertGreater(row['signals']['description_bps'], 5000)
        self.assertEqual(row['features']['kalshi']['thresholds'], [('>', '100000', 'USD')])
        self.assertEqual(row['definition_links']['kalshi'][0], kalshi.detail_url(K))
        self.assertIn('gateway.polymarket.us', row['definition_links']['polymarket_us'][0])
        self.assertFalse(row['trading_authorized'])
        self.assertEqual(row['status'], 'UNVERIFIED')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)

    def test_identical_titles_different_dates_thresholds_or_report_are_demoted(self):
        base = self.search()['candidates'][0]['equivalence_score_bps']
        for key, old, new, warning in [('question', '2030-01-02', '2030-01-03', 'DATES_CONFLICT'),
                                      ('question', '$100k', '$101k', 'THRESHOLDS_CONFLICT'),
                                      ('description', 'FINAL', 'FIRST', 'RESOLUTION_LANGUAGE_DIFFERS')]:
            contract = deepcopy(DATA['polymarket_us'])
            contract[key] = contract[key].replace(old, new)
            self.seed('polymarket_us', 'HYPOTHETICAL-DIFFERENT', contract)
            row = next(r for r in self.search()['candidates'] if r['polymarket_us_id'] == 'HYPOTHETICAL-DIFFERENT')
            self.assertIn(warning, row['warnings'])
            self.assertLess(row['equivalence_score_bps'], base)

    def test_threshold_inclusivity_units_and_missing_are_not_guessed(self):
        left = d.features({'title': 'Bitcoin above $100 on 2030-01-02'})
        for title in ('Bitcoin at least $100 on 2030-01-02', 'Bitcoin above 100% on 2030-01-02'):
            self.assertIn('THRESHOLDS_CONFLICT', d.compare(left, d.features({'title': title}))[2])
        unknown = d.features({'title': 'Bitcoin price'})
        self.assertIn('THRESHOLDS_UNKNOWN', d.compare(left, unknown)[2])
        self.assertEqual(unknown['thresholds'], set())

    def test_event_timestamp_normalization_and_no_close_date_inference(self):
        left = d.features(dict(DATA['kalshi'], uninterpreted_metadata={'occurrence_datetime': '2030-01-02T12:00:00Z'}))
        right = d.features(dict(DATA['polymarket_us'], uninterpreted_metadata={'gameStartTime': '2030-01-02T07:00:00-05:00'}))
        self.assertEqual(left['event_time'], right['event_time'])
        zoned = d.features(dict(DATA['polymarket_us'], endDate='2030-01-02T07:00:00-05:00'))
        self.assertNotIn('CUTOFFS_DIFFER', d.compare(left, zoned)[2])
        self.assertEqual(d.compare(left, right)[1]['dates'], 'MATCH')
        missing = d.features({'title': 'Bitcoin price', 'close_time': '2030-01-02T12:00:00Z'})
        self.assertEqual(missing['dates'], set())
        with self.assertRaises(ValueError):
            d.features({'title': 'Bitcoin', 'gameStartTime': '2030-01-02'})
        with self.assertRaises(ValueError):
            d.features({'title': 100})

    def test_description_retrieval_with_different_titles(self):
        self.seed('kalshi', K, {'title': 'HYPOTHETICAL digital asset milestone', 'rules_primary': DATA['kalshi']['rules_primary']})
        self.seed('polymarket_us', P, {'title': 'HYPOTHETICAL crypto target', 'description': DATA['kalshi']['rules_primary']})
        row = self.search()['candidates'][0]
        self.assertEqual(row['signals']['subject_bps'], 0)
        self.assertEqual(row['signals']['description_bps'], 10000)

    def test_mixed_hypothetical_and_live_never_match(self):
        self.db.execute('DELETE FROM registry_instruments WHERE source_id=?', (P,))
        self.db.commit()
        registry._record_instrument(self.db, 'polymarket_us', 'live-test-only', DATA['polymarket_us'],
                                    observed_at=NOW.isoformat(), available=True, now=NOW)
        self.assertEqual(self.search()['candidates'], [])

    def test_complete_full_catalogue_removes_absent_markets_but_scopes_do_not(self):
        # HYPOTHETICAL mutation of real-format replay records in this isolated database.
        from predarb.collector import collect
        page = payload('kalshi-page')
        page['cursor'] = ''
        for market in page['markets']:
            market['close_time'] = '2030-01-02T12:00:00Z'
        def capture(data, scope=None):
            replay = Replay(Response(dumps(data).encode()))
            client = HttpClient(self.db, 'kalshi', opener=replay, sleep=lambda _: None,
                                utc_now=lambda: NOW.isoformat())
            return collect(self.db, kalshi, books=0, scope=scope, client=client)
        capture(page)
        live_count = len(page['markets'])
        self.assertEqual(self.search()['coverage']['kalshi']['eligible'], live_count + 1)
        capture({'markets': [], 'cursor': ''}, scope='unrelated-event')
        self.assertEqual(self.search()['coverage']['kalshi']['eligible'], live_count + 1)
        capture({'markets': [], 'cursor': ''})
        self.assertEqual(self.search()['coverage']['kalshi']['eligible'], 1)

    def test_raw_book_provenance_tampering_is_not_ranked(self):
        raw = self.book('kalshi', K)
        self.db.execute("UPDATE raw_observations SET body_sha256='wrong' WHERE id=?", (raw,))
        self.db.commit()
        self.assertEqual(d.liquidity(self.db, 'kalshi', K, NOW)['quality'], 'INVALID')

    def test_generic_event_titles_include_contract_participant_identity(self):
        self.seed('kalshi', K, {'title': 'HYPOTHETICAL Bundesliga Relegation', 'yes_sub_title': 'Dortmund'})
        self.seed('polymarket_us', P, {'question': 'HYPOTHETICAL Bundesliga Relegation',
                    'marketSides': [{'long': True, 'description': 'Dortmund', 'team': {'name': 'Dortmund'}}]})
        self.seed('polymarket_us', 'HYPOTHETICAL-OTHER', {'question': 'HYPOTHETICAL Bundesliga Relegation',
                    'marketSides': [{'long': True, 'description': 'Bremen', 'team': {'name': 'Bremen'}}]})
        rows = self.search()['candidates']
        self.assertEqual(rows[0]['polymarket_us_id'], P)
        self.assertGreater(rows[0]['signals']['subject_bps'], rows[1]['signals']['subject_bps'])
        self.assertIn('Dortmund', rows[0]['features']['polymarket_us']['subject_text'])

    def test_score_upper_bound_preserves_winners_and_ties(self):
        left, right = d.features(DATA['kalshi']), d.features(DATA['polymarket_us'])
        score = d.compare(left, right)[0]
        self.assertEqual(d.compare(left, right, min_score=score)[0], score)
        self.assertIsNone(d.compare(left, right, min_score=score+1))
        for i in range(30):
            contract = deepcopy(DATA['polymarket_us'])
            contract['question'] += ' ' + ('unrelated ' * (i % 3))
            self.seed('polymarket_us', f'HYPOTHETICAL-P-{i:02}', contract)
        all_rows = self.search(limit=1000)['candidates']
        self.assertEqual(self.search(limit=3)['candidates'], all_rows[:3])

    def test_threshold_units_must_not_be_invented_or_conflated(self):
        celsius = d.features({'title': 'River City temperature above 30 C'})
        fahrenheit = d.features({'title': 'River City temperature above 30 F'})
        self.assertIn('THRESHOLDS_CONFLICT', d.compare(celsius, fahrenheit)[2])
        unknown = d.features({'title': 'River City temperature above 30'})
        result = d.compare(unknown, unknown)
        self.assertEqual(result[1]['thresholds'], 'VALUE_MATCH_UNITS_UNKNOWN')
        self.assertIn('THRESHOLD_UNITS_UNKNOWN', result[2])
        self.assertIn(('>', '30', 'C'), celsius['thresholds'])

    def test_generic_sports_words_do_not_join_unrelated_participants(self):
        self.seed('kalshi', K, {'title': 'HYPOTHETICAL James Harden total points'})
        self.seed('polymarket_us', P, {'question': 'HYPOTHETICAL Stephen Curry total points'})
        self.assertEqual(self.search()['candidates'], [])

    def test_core_goods_and_core_cpi_and_measure_periods_are_distinct(self):
        goods = d.features({'title': 'Core goods CPI month-over-month above 0.1% on 2030-01-02'})
        core = d.features({'title': 'Core CPI MoM above 0.1% on 2030-01-02'})
        annual = d.features({'title': 'Core CPI YoY above 0.1% on 2030-01-02'})
        self.assertEqual(goods['measure']['metric'], 'core_goods_cpi')
        self.assertEqual(core['measure']['metric'], 'core_cpi')
        self.assertIn('SUBJECT_METRIC_CONFLICT', d.compare(goods, core)[2])
        self.assertIn('SUBJECT_PERIOD_CONFLICT', d.compare(core, annual)[2])
        self.assertGreater(d.compare(core, core)[0], d.compare(goods, core)[0])
        unqualified = d.features({'title': 'CPI forecast'})
        self.assertIsNone(unqualified['measure']['metric'])
        self.assertIn('SUBJECT_METRIC_UNKNOWN', d.compare(goods, unqualified)[2])
        ambiguous = d.features({'title': 'Core CPI MoM', 'description': 'Core goods CPI YoY'})
        self.assertEqual(ambiguous['measure'], {'metric': None, 'period': None})

    def test_declared_official_rule_links_exclude_international_and_spoofed_hosts(self):
        contract = deepcopy(DATA['polymarket_us'])
        official = 'https://www.polymarketexchange.com/files/products/rules.pdf'
        contract['description'] += ' Full rules: ' + official + ' Other links: https://polymarket.com/rules https://polymarket.us.evil.invalid/rules https://user:pass@polymarket.us/private'
        self.seed('polymarket_us', P, contract)
        links = self.search()['candidates'][0]['definition_links']['polymarket_us']
        self.assertIn(official, links)
        self.assertEqual(len(links), 2)

    def test_unrelated_subjects_are_not_candidates(self):
        self.seed('polymarket_us', P, {'question': 'HYPOTHETICAL London mayor election'})
        self.assertEqual(self.search()['candidates'], [])

    def test_no_500_instrument_cap_and_explicit_cap_reports_truncation(self):
        for i in range(501):
            self.seed('kalshi', f'HYPOTHETICAL-A-{i:04}', {'title': 'HYPOTHETICAL unrelated rainfall'})
        self.assertEqual(self.search()['candidates'][0]['kalshi_id'], K)
        capped = self.search(max_instruments=500)
        self.assertEqual(capped['candidates'], [])
        self.assertTrue(capped['coverage']['kalshi']['truncated'])

    def test_stale_future_unavailable_and_expired_excluded(self):
        for at, available in [(NOW - timedelta(days=2), True), (NOW + timedelta(minutes=1), True), (NOW, False)]:
            self.seed('kalshi', K, at=at, available=available)
            self.assertEqual(self.search()['candidates'], [])
        contract = dict(DATA['kalshi'], close_time=NOW.isoformat())
        self.seed('kalshi', K, contract)
        self.assertEqual(self.search()['candidates'], [])

    def test_liquidity_tie_break_exact_quantity_and_source_unknown(self):
        self.seed('polymarket_us', 'HYPOTHETICAL-P-DEEP')
        self.book('kalshi', K, quantity='100')
        self.book('polymarket_us', P, quantity='1.125')
        self.book('polymarket_us', 'HYPOTHETICAL-P-DEEP', quantity='25.50')
        rows = self.search()['candidates']
        self.assertEqual(rows[0]['polymarket_us_id'], 'HYPOTHETICAL-P-DEEP')
        self.assertEqual(rows[0]['liquidity']['paired_depth_proxy'], '25.50')
        self.assertEqual(rows[1]['liquidity']['paired_depth_proxy'], '1.125')
        self.assertEqual(rows[0]['liquidity']['kalshi']['quality'], 'UNKNOWN_SOURCE_TIME')
        self.assertFalse(rows[0]['liquidity']['kalshi']['executable'])

    def test_stale_invalid_missing_and_empty_liquidity(self):
        self.assertEqual(d.liquidity(self.db, 'kalshi', K, NOW)['quality'], 'MISSING')
        self.book('kalshi', K, at=NOW - timedelta(minutes=2))
        self.assertIsNone(d.liquidity(self.db, 'kalshi', K, NOW)['depth_proxy'])
        self.book('polymarket_us', P, invalid=True)
        self.assertEqual(d.liquidity(self.db, 'polymarket_us', P, NOW)['quality'], 'INVALID')
        self.book('polymarket_us', P, state='MARKET_STATE_HALTED')
        unavailable = d.liquidity(self.db, 'polymarket_us', P, NOW)
        self.assertEqual(unavailable['quality'], 'UNAVAILABLE')
        self.assertIsNone(unavailable['depth_proxy'])
        self.book('polymarket_us', P, source_at=NOW-timedelta(minutes=2))
        self.assertEqual(d.liquidity(self.db, 'polymarket_us', P, NOW)['quality'], 'STALE_SOURCE')
        raw = self.book('kalshi', K)
        data = {'orderbook_fp': {'yes_dollars': [], 'no_dollars': [['0.5', '2']]}}
        import hashlib
        body = dumps(data).encode()
        self.db.execute('UPDATE raw_observations SET raw_body=?,body_sha256=? WHERE id=?', (body, hashlib.sha256(body).hexdigest(), raw))
        self.db.commit()
        self.assertEqual(d.liquidity(self.db, 'kalshi', K, NOW)['depth_proxy'], '0')

    def test_queue_refresh_idempotence_rejection_and_use_time_validity(self):
        first = d.refresh_queue(self.db, now=NOW)
        pair = registry.propose(self.db, K, P, 'HYPOTHETICAL human', now=NOW)
        registry.decide(self.db, pair, 'REJECTED', 'HYPOTHETICAL human', 'different rules', now=NOW)
        second = d.refresh_queue(self.db, now=NOW)
        self.assertEqual(first['candidates'][0]['versions'], second['candidates'][0]['versions'])
        self.assertEqual(second['candidates'][0]['prior_reviews'][0]['status'], 'REJECTED')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM discovery_queue').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT status FROM pairs').fetchone()[0], 'REJECTED')
        self.assertEqual(d.queue(self.db, now=NOW+timedelta(days=2))['candidates'], [])

    def test_queue_contains_only_refreshed_members_and_rechecks_changed_evidence(self):
        self.assertEqual(d.queue(self.db, now=NOW)['candidates'], [])
        d.refresh_queue(self.db, now=NOW)
        self.seed('polymarket_us', 'HYPOTHETICAL-NEW')
        queued = d.queue(self.db, now=NOW)
        self.assertEqual(len(queued['candidates']), 1)
        self.assertEqual(queued['coverage']['polymarket_us']['scope'], 'queued_instruments')
        self.assertEqual(queued['coverage']['polymarket_us']['stored'], 2)
        self.assertEqual(queued['coverage']['polymarket_us']['eligible'], 1)
        self.assertEqual(len(self.search()['candidates']), 2)
        self.seed('polymarket_us', P, {'question': 'HYPOTHETICAL unrelated election'})
        self.assertEqual(d.queue(self.db, now=NOW)['candidates'], [])

    def test_queue_transaction_rolls_back_on_storage_error(self):
        d.refresh_queue(self.db, now=NOW)
        self.db.execute("CREATE TRIGGER queue_fail BEFORE INSERT ON discovery_queue BEGIN SELECT RAISE(ABORT,'test'); END")
        self.db.commit()
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            d.refresh_queue(self.db, now=NOW)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM discovery_queue').fetchone()[0], 1)

    def test_schema_five_migration_preserves_registry(self):
        self.db.execute('DROP TABLE discovery_queue')
        self.db.execute('DROP TABLE discovery_state')
        self.db.execute('DROP INDEX discovery_books_source')
        self.db.execute('PRAGMA user_version=5')
        self.db.commit()
        with connect(self.path) as migrated:
            self.assertEqual(migrated.execute('PRAGMA user_version').fetchone()[0], 6)
            self.assertEqual(migrated.execute('SELECT COUNT(*) FROM registry_instruments').fetchone()[0], 2)
            self.assertEqual(migrated.execute('SELECT COUNT(*) FROM discovery_queue').fetchone()[0], 0)

    def test_queue_remains_readable_while_another_writer_holds_lock(self):
        import fcntl
        import os
        d.refresh_queue(self.db, now=NOW)
        fd = os.open(self.path + '.writer.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out = StringIO()
            with patch('sys.argv', ['predarb', 'discovery', 'queue', '--db', self.path]), patch('predarb.registry.now_utc', return_value=NOW), redirect_stdout(out):
                self.assertEqual(cli.main(), 0)
            self.assertEqual(len(json.loads(out.getvalue())['candidates']), 1)
        finally:
            os.close(fd)

    def test_cli_offline_refresh_and_queue(self):
        for command in ('refresh', 'queue'):
            args = ['predarb', 'discovery', command, '--db', self.path] + (['--offline'] if command == 'refresh' else [])
            output = StringIO()
            with patch('sys.argv', args), patch('predarb.registry.now_utc', return_value=NOW), redirect_stdout(output):
                self.assertEqual(cli.main(), 0)
            self.assertEqual(json.loads(output.getvalue())['candidates'][0]['status'], 'UNVERIFIED')


class RefreshTests(unittest.TestCase):
    def run_refresh(self, kframes, pframes, **kwargs):
        with tempfile.TemporaryDirectory() as temp, connect(str(Path(temp)/'db')) as con:
            replays = {'kalshi': Replay(*kframes), 'polymarket_us': Replay(*pframes)}
            def factory(con, venue, **options):
                return HttpClient(con, venue, opener=replays[venue], sleep=lambda _: None,
                                  utc_now=lambda: NOW.isoformat(), **options)
            result = discovery_cli.refresh(con, client_factory=factory, now=NOW, books=0, **kwargs)
            self.assertTrue(all(not r.responses for r in replays.values()))
            self.assertEqual(con.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)
            return result, replays

    def test_both_venues_complete_and_active_filters(self):
        (report, code), replays = self.run_refresh([Response(b'{"markets":[],"cursor":""}')], [Response(b'{"markets":[]}')])
        self.assertEqual(code, 0)
        self.assertEqual(len(report['collection_runs']), 2)
        self.assertIn('status=open', replays['kalshi'].requests[0][0].full_url)
        self.assertIn('active=true', replays['polymarket_us'].requests[0][0].full_url)

    def test_page_cap_returns_partial_and_keeps_continuation(self):
        page = payload('kalshi-page')
        (report, code), _ = self.run_refresh([Response(dumps(page).encode())], [Response(b'{"markets":[]}')], max_pages=1)
        self.assertEqual(code, 2)
        self.assertEqual(report['collection_runs'][0]['status'], 'PARTIAL')
        self.assertIsNotNone(report['collection_runs'][0]['next_page'])

    def test_schema_failure_still_collects_other_venue(self):
        (report, code), _ = self.run_refresh([Response(b'{"bad":"schema"}')], [Response(b'{"markets":[]}')])
        self.assertEqual(code, 1)
        self.assertEqual(report['errors'][0]['venue'], 'kalshi')
        self.assertEqual(report['coverage']['kalshi']['latest_run_status'], 'FAILED')
        self.assertEqual(report['collection_runs'][0]['venue'], 'polymarket_us')

    def test_ranked_details_books_links_and_shared_pacing_clients(self):
        # Altered provider responses are HYPOTHETICAL, stored only in this temporary DB.
        km = payload('kalshi-market-live')['market']
        pm = payload('poly-market-live')['market']
        km.update(title='HYPOTHETICAL Bitcoin above $100000 on 2030-01-02',
                  rules_primary=DATA['kalshi']['rules_primary'], close_time='2030-01-02T12:00:00Z',
                  occurrence_datetime='2030-01-02T12:00:00Z')
        pm.update(question=km['title'], description=km['rules_primary'], endDate=km['close_time'],
                  gameStartTime=km['occurrence_datetime'], active=True, closed=False, status='MARKET_STATUS_OPEN')
        event = payload('kalshi-event-live')
        event['event']['event_ticker'] = km['event_ticker']
        series = payload('kalshi-series-live')
        event['event']['series_ticker'] = series['series']['ticker']
        pbook = payload('poly-book-live')
        pbook['marketData']['marketSlug'] = pm['slug']
        pbook['marketData']['transactTime'] = NOW.isoformat()
        kpage, ppage = {'markets': [km], 'cursor': ''}, {'markets': [pm]}
        for fail_details in (False, True):
            with self.subTest(fail_details=fail_details), tempfile.TemporaryDirectory() as temp, connect(str(Path(temp)/'db')) as con:
                kframes = [kpage, kpage, {'market': km}, event, series, payload('kalshi-book-live')]
                if fail_details:
                    kframes = [kpage, {'bad': 'schema'}]
                pframes = [ppage, {'markets': []}, ppage, {'markets': []}, {'market': pm}, pbook]
                replays = {'kalshi': Replay(*(Response(dumps(f).encode()) for f in kframes)),
                           'polymarket_us': Replay(*(Response(dumps(f).encode()) for f in pframes))}
                created = []
                delays = []
                def factory(con, venue, **options):
                    created.append(venue)
                    return HttpClient(con, venue, opener=replays[venue], sleep=delays.append,
                                      utc_now=lambda: NOW.isoformat(), **options)
                report, code = discovery_cli.refresh(con, client_factory=factory, now=NOW, books=1)
                self.assertEqual(created, ['kalshi', 'polymarket_us'])
                self.assertTrue(delays)
                self.assertTrue(all(not r.responses for r in replays.values()))
                if fail_details:
                    self.assertEqual(code, 1)
                    self.assertEqual(report['candidates'], [])
                    self.assertEqual(report['errors'][0]['stage'], 'detail')
                else:
                    self.assertEqual(code, 0)
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM book_captures').fetchone()[0], 2)
                    links = report['candidates'][0]['definition_links']['kalshi']
                    self.assertIn(series['series']['contract_terms_url'], links)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)

    def test_disk_guard_fails_before_request_and_cli_start(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp, connect(str(Path(temp)/'db')) as con:
            client = discovery_cli.SpaceCheckedClient(con, 'kalshi', min_free_mb=1,
                                                       opener=Replay(), sleep=lambda _: None)
            with patch('predarb.discovery_cli.disk_usage', return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(OSError, 'free disk'):
                    client.get(kalshi.page_url(20, None, None), kalshi.SCHEMA_VERSION, kalshi.validate_page)
                with patch('sys.argv', ['predarb', 'discovery', 'refresh', '--db', str(Path(temp)/'db')]), redirect_stderr(StringIO()):
                    self.assertEqual(cli.main(), 1)

    def test_bad_limits_fail_before_network(self):
        for kwargs in ({'limit': 0}, {'books': 101}, {'request_interval': .01}, {'max_pages': 0}, {'request_interval': float('nan')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                discovery_cli.refresh(None, client_factory=lambda *a, **k: self.fail('network'), **kwargs)
