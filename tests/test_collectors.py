"""Provider contract and integration tests, using captured US API bytes offline."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import tempfile
import unittest
from pathlib import Path

from predarb import kalshi, polymarket_us as poly
from predarb.collector import collect, book_freshness
from predarb.provider import HttpClient
from predarb.store import connect
from predarb.validation import SchemaError, dumps, load_json, utc_time
from helpers import fixture, payload, Response, Replay, real_response


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = connect(str(Path(self.temp.name) / 'test.sqlite3'))
        self.addCleanup(self.db.close)

    def client(self, adapter, *responses):
        replay = Replay(*responses)
        client = HttpClient(self.db, adapter.VENUE, opener=replay, sleep=lambda delay: None)
        return client, replay

    def test_real_fixture_integrity_and_schemas(self):
        checks = [('kalshi-page', kalshi.validate_page), ('kalshi-page2', kalshi.validate_page),
                  ('kalshi-market-live', kalshi.validate_detail), ('kalshi-event-live', kalshi.validate_event),
                  ('kalshi-book-live', kalshi.validate_book), ('kalshi-series-live', kalshi.validate_series), ('poly-page', poly.validate_page),
                  ('poly-page2', poly.validate_page), ('poly-market-live', poly.validate_detail),
                  ('poly-book-live', poly.validate_book)]
        for name, validator in checks:
            with self.subTest(name=name):
                entry = fixture(name)
                self.assertIn('REAL_PUBLIC_US_API_SNAPSHOT', entry['provenance'])
                self.assertEqual(hashlib.sha256(entry['body'].encode()).hexdigest(), entry['body_sha256'])
                self.assertNotIn('set-cookie', entry['headers'])
                validator(load_json(entry['body']))

    def test_kalshi_real_two_page_replay_with_details_event_book(self):
        client, replay = self.client(kalshi, *(real_response(name) for name in (
            'kalshi-page', 'kalshi-page2', 'kalshi-market-live', 'kalshi-event-live', 'kalshi-series-live', 'kalshi-book-live')))
        result = collect(self.db, kalshi, page_size=2, max_pages=2, client=client)
        self.assertEqual((result.status, result.pages, result.records, result.unique_records), ('PARTIAL', 2, 4, 4))
        self.assertEqual(result.books, 1)
        self.assertIn('cursor=', replay.requests[1][0].full_url)
        self.assertEqual(self.db.execute('SELECT freshness FROM book_captures').fetchone()[0], 'UNKNOWN_SOURCE_TIME')
        row = self.db.execute('SELECT rules_json,verification FROM catalogue_entries WHERE source_id=?',
                              (payload('kalshi-market-live')['market']['ticker'],)).fetchone()
        self.assertIn('settlement_sources', row[0])
        self.assertIn('rules_secondary', row[0])
        self.assertEqual(row[1], 'UNVERIFIED')
        raw = self.db.execute('SELECT raw_body FROM raw_observations ORDER BY id LIMIT 1').fetchone()[0]
        self.assertEqual(raw, fixture('kalshi-page')['body'].encode())
        self.assertEqual(len(replay.responses), 0)

    def test_poly_real_two_page_replay_with_instrument_metadata_and_book(self):
        client, replay = self.client(poly, *(real_response(name) for name in (
            'poly-page', 'poly-page2', 'poly-market-live', 'poly-book-live')))
        result = collect(self.db, poly, page_size=2, max_pages=2, client=client)
        self.assertEqual((result.status, result.records, result.unique_records), ('PARTIAL', 4, 4))
        self.assertIn('offset=2', replay.requests[1][0].full_url)
        self.assertIn('orderBy=id', replay.requests[1][0].full_url)
        row = self.db.execute('SELECT source_ts,verification FROM book_captures').fetchone()
        self.assertEqual(row, (payload('poly-book-live')['marketData']['transactTime'], 'UNVERIFIED'))
        metadata, rules = self.db.execute('SELECT metadata_json,rules_json FROM catalogue_entries LIMIT 1').fetchone()
        self.assertIn('marketSides', metadata)
        self.assertIn('description', rules)
        self.assertEqual(len(replay.responses), 0)

    def test_terminal_pages_and_reconciliation(self):
        # HYPOTHETICAL terminal responses built from real captured records.
        for adapter, prefix in ((kalshi, 'kalshi'), (poly, 'poly')):
            with self.subTest(venue=adapter.VENUE):
                first = payload(prefix + '-page')
                if adapter is kalshi:
                    first['cursor'] = 'hypothetical-next'
                    last = {'markets': [], 'cursor': ''}
                else:
                    last = {'markets': []}
                client, _ = self.client(adapter, Response(dumps(first).encode()), Response(dumps(last).encode()))
                result = collect(self.db, adapter, page_size=2, max_pages=3, books=0, client=client)
                self.assertEqual((result.status, result.pages, result.records, result.duplicates), ('COMPLETE', 2, 2, 0))
                self.assertIsNone(result.next_page)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM catalogue_entries WHERE run_id=?',
                                                (result.run_id,)).fetchone()[0], result.unique_records)

    def test_poly_short_pages_do_not_falsely_prove_exhaustion(self):
        # HYPOTHETICAL server caps pages below the requested size.
        markets = payload('poly-page')['markets']
        client, replay = self.client(poly, Response(dumps({'markets': markets[:1]}).encode()),
                                     Response(dumps({'markets': markets[1:]}).encode()),
                                     Response(b'{"markets":[]}'))
        result = collect(self.db, poly, page_size=20, max_pages=3, books=0, client=client)
        self.assertEqual((result.status, result.pages, result.records), ('COMPLETE', 3, 2))
        self.assertIn('offset=1', replay.requests[1][0].full_url)
        self.assertIn('offset=2', replay.requests[2][0].full_url)

    def test_real_missing_updated_at_excerpt_preserves_unknown_metadata_clock(self):
        entry = fixture('poly-missing-updated-at-live')
        self.assertIn('REAL_PUBLIC_US_API_EXCERPT', entry['provenance'])
        self.assertEqual(hashlib.sha256(entry['body'].encode()).hexdigest(), entry['body_sha256'])
        self.assertNotIn('set-cookie', entry['headers'])
        utc_time(entry['retrieved_at'])
        market = load_json(entry['body'])['markets'][0]
        self.assertNotIn('updatedAt', market)
        # HYPOTHETICAL replay sequence: captured excerpt plus synthetic terminal page.
        client, replay = self.client(poly, real_response('poly-missing-updated-at-live'), Response(b'{"markets":[]}'))
        result = collect(self.db, poly, page_size=200, max_pages=2, books=0, client=client)
        self.assertEqual((result.status, result.records), ('COMPLETE', 1))
        self.assertIn('offset=1', replay.requests[1][0].full_url)
        source_ts, metadata, verification = self.db.execute('SELECT source_ts,metadata_json,verification FROM catalogue_entries').fetchone()
        self.assertIsNone(source_ts); self.assertNotIn('updatedAt', load_json(metadata))
        self.assertEqual(verification, 'UNVERIFIED')
        self.assertEqual(self.db.execute('SELECT raw_body FROM raw_observations ORDER BY id LIMIT 1').fetchone()[0], entry['body'].encode())
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)

    def test_optional_metadata_update_time_on_page_and_detail_keeps_book_clock(self):
        # HYPOTHETICAL missing/null metadata variations; book time stays provider-supplied.
        for present in (False, True):
            page, detail, book = payload('poly-page'), payload('poly-market-live'), payload('poly-book-live')
            for market in [*page['markets'], detail['market']]:
                if present: market['updatedAt'] = None
                else: market.pop('updatedAt')
            client, _ = self.client(poly, *(Response(dumps(data).encode()) for data in (page, detail, book)))
            now = utc_time(book['marketData']['transactTime']) + timedelta(seconds=61)
            client.utc_now = lambda: now.isoformat()
            result = collect(self.db, poly, page_size=2, max_pages=1, client=client,
                             now=now)
            self.assertEqual(result.status, 'PARTIAL')
            self.assertTrue(all(row[0] is None for row in self.db.execute('SELECT source_ts FROM catalogue_entries WHERE run_id=?', (result.run_id,))))
            self.assertIsNone(self.db.execute('SELECT source_ts FROM raw_observations WHERE endpoint=? ORDER BY id DESC LIMIT 1',
                                             (poly.detail_url(detail['market']['slug']),)).fetchone()[0])
            row = self.db.execute('SELECT source_ts,freshness FROM book_captures WHERE run_id=?', (result.run_id,)).fetchone()
            self.assertEqual(row[0], book['marketData']['transactTime'])
            self.assertEqual(row[1], 'STALE_SOURCE')

    def test_invalid_optional_update_timestamps_are_still_archived_and_rejected(self):
        # HYPOTHETICAL malformed values must not take the missing-value path.
        for value in ('', 'not-a-time', '2026-10-24T05:30:00', 0, False, [], {}):
            with self.subTest(value=value):
                page = payload('poly-page'); page['markets'][0]['updatedAt'] = value
                body = dumps(page).encode()
                client, _ = self.client(poly, Response(body))
                with self.assertRaisesRegex(ValueError, 'raw response archived'):
                    collect(self.db, poly, page_size=2, books=0, client=client)
                self.assertEqual(self.db.execute('SELECT raw_body,validation_status FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone(), (body, 'REJECTED'))

    def test_missing_metadata_update_never_relaxes_required_book_timestamp(self):
        page, detail, book = payload('poly-page'), payload('poly-market-live'), payload('poly-book-live')
        for market in [*page['markets'], detail['market']]: market.pop('updatedAt')
        book['marketData'].pop('transactTime')
        client, _ = self.client(poly, *(Response(dumps(data).encode()) for data in (page, detail, book)))
        with self.assertRaisesRegex(ValueError, 'transactTime'):
            collect(self.db, poly, page_size=2, max_pages=1, client=client)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM book_captures').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT status FROM collection_runs').fetchone()[0], 'FAILED')

    def test_overlap_deduplication_and_counts(self):
        # HYPOTHETICAL overlapping pages caused by catalogue movement.
        first = payload('kalshi-page')
        second = payload('kalshi-page2')
        second['markets'][0] = deepcopy(first['markets'][1])
        second['cursor'] = ''
        client, _ = self.client(kalshi, Response(dumps(first).encode()), Response(dumps(second).encode()))
        result = collect(self.db, kalshi, page_size=2, books=0, client=client)
        self.assertEqual((result.records, result.unique_records, result.duplicates), (4, 3, 1))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], 2)

    def test_repeated_page_and_nonadvancing_cursor_fail_closed(self):
        for kind in ('page', 'cursor', 'empty'):
            with self.subTest(kind=kind):
                first = payload('kalshi-page')
                second = payload('kalshi-page' if kind == 'page' else 'kalshi-page2')
                if kind == 'cursor':
                    second['cursor'] = first['cursor']
                if kind == 'empty':
                    second['markets'] = []
                client, _ = self.client(kalshi, Response(dumps(first).encode()), Response(dumps(second).encode()))
                with self.assertRaises(SchemaError):
                    collect(self.db, kalshi, page_size=2, books=0, client=client)
                self.assertEqual(self.db.execute('SELECT status FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()[0], 'FAILED')

    def test_schema_drift_archived_before_rejection(self):
        for adapter, name, key in ((kalshi, 'kalshi-page', 'rules_primary'), (poly, 'poly-page', 'marketSides')):
            with self.subTest(venue=adapter.VENUE):
                data = payload(name)
                del data['markets'][0][key]
                body = dumps(data).encode()
                client, _ = self.client(adapter, Response(body))
                with self.assertRaisesRegex(ValueError, 'raw response archived'):
                    collect(self.db, adapter, page_size=2, client=client)
                self.assertEqual(self.db.execute('SELECT raw_body,validation_status FROM raw_observations ORDER BY id DESC LIMIT 1').fetchone(),
                                 (body, 'REJECTED'))
                self.assertEqual(self.db.execute('SELECT status FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()[0], 'FAILED')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM catalogue_entries').fetchone()[0], 0)

    def test_detail_event_and_book_identity_mismatch(self):
        for target in ('detail', 'event', 'book', 'poly-id'):
            with self.subTest(target=target):
                adapter = kalshi if target in ('detail', 'event') else poly
                page = payload('kalshi-page' if adapter is kalshi else 'poly-page')
                responses = [Response(dumps(page).encode())]
                detail = payload('kalshi-market-live' if adapter is kalshi else 'poly-market-live')
                if target == 'detail':
                    detail['market']['ticker'] = 'HYPOTHETICAL-WRONG'
                if target == 'poly-id':
                    detail['market']['id'] = 'HYPOTHETICAL-WRONG'
                responses.append(Response(dumps(detail).encode()))
                if target == 'event':
                    event = payload('kalshi-event-live')
                    event['event']['event_ticker'] = 'HYPOTHETICAL-WRONG'
                    responses.append(Response(dumps(event).encode()))
                if target == 'book':
                    book = payload('poly-book-live')
                    book['marketData']['marketSlug'] = 'HYPOTHETICAL-WRONG'
                    responses.append(Response(dumps(book).encode()))
                client, _ = self.client(adapter, *responses)
                with self.assertRaisesRegex(ValueError, 'identity|id mismatch'):
                    collect(self.db, adapter, page_size=2, max_pages=1, client=client)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM book_captures').fetchone()[0], 0)

    def test_scope_and_selection_validation(self):
        client, _ = self.client(poly, real_response('poly-page'))
        with self.assertRaisesRegex(ValueError, 'outside requested scope'):
            collect(self.db, poly, page_size=2, scope='HYPOTHETICAL-WRONG', client=client)
        client, _ = self.client(poly, real_response('poly-page'))
        with self.assertRaisesRegex(ValueError, 'not in the captured catalogue'):
            collect(self.db, poly, page_size=2, max_pages=1, selected=('HYPOTHETICAL-MISSING',), client=client)
        for kwargs in ({'page_size': 0}, {'max_pages': 0}, {'books': 101}, {'max_age': 0}, {'scope': '../bad'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                collect(self.db, poly, **kwargs)

    def test_selected_books_deduplicated_and_empty_partial_liquidity(self):
        for partial in (False, True):
            page = payload('poly-page')
            page['markets'] = page['markets'][:1]
            source_id = page['markets'][0]['slug']
            book = payload('poly-book-live')
            book['marketData']['offers'] = []
            if not partial:
                book['marketData']['bids'] = []
            client, replay = self.client(poly, Response(dumps(page).encode()), Response(b'{"markets":[]}'), real_response('poly-market-live'),
                                         Response(dumps(book).encode()))
            result = collect(self.db, poly, page_size=2, selected=(source_id, source_id), client=client)
            self.assertEqual(result.books, 1)
            self.assertEqual(len(replay.requests), 4)
            self.assertEqual(self.db.execute('SELECT liquidity FROM book_captures ORDER BY observation_id DESC LIMIT 1').fetchone()[0],
                             'PARTIAL' if partial else 'EMPTY')

    def test_interrupt_retains_run_and_completed_page(self):
        client, _ = self.client(poly, real_response('poly-page'), KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            collect(self.db, poly, page_size=2, client=client)
        self.assertEqual(self.db.execute('SELECT status,records,next_page FROM collection_runs').fetchone(),
                         ('INTERRUPTED', 2, '2'))


class ValidationTests(unittest.TestCase):
    def test_missing_or_wrong_type_fields(self):
        for adapter, prefix in ((kalshi, 'kalshi'), (poly, 'poly')):
            for change in ('missing', 'wrong', 'status'):
                with self.subTest(venue=adapter.VENUE, change=change):
                    page = payload(prefix + '-page')
                    if change == 'missing':
                        del page['markets']
                    elif change == 'wrong':
                        page['markets'] = {}
                    else:
                        page['markets'][0]['status'] = 'UNKNOWN_FUTURE_STATUS'
                    with self.assertRaises(SchemaError):
                        adapter.validate_page(page)

    def test_invalid_book_prices_and_quantities(self):
        for adapter, prefix in ((kalshi, 'kalshi'), (poly, 'poly')):
            for invalid in ('NaN', 'Infinity', '-0.1', '1.1', '0', '1', 0.5):
                book = payload(prefix + '-book-live')
                if adapter is kalshi:
                    book['orderbook_fp']['yes_dollars'][0][0] = invalid
                else:
                    book['marketData']['bids'][0]['px']['value'] = invalid
                with self.subTest(venue=adapter.VENUE, invalid=invalid), self.assertRaises(SchemaError):
                    adapter.validate_book(book)
            for invalid in ('NaN', '-1', '0', 1):
                book = payload(prefix + '-book-live')
                if adapter is kalshi:
                    book['orderbook_fp']['yes_dollars'][0][1] = invalid
                else:
                    book['marketData']['bids'][0]['qty'] = invalid
                with self.subTest(quantity=invalid), self.assertRaises(SchemaError):
                    adapter.validate_book(book)

    def test_missing_empty_partial_and_duplicate_book_sides(self):
        for adapter, name, field_name, side in ((kalshi, 'kalshi-book-live', 'orderbook_fp', 'yes_dollars'),
                                               (poly, 'poly-book-live', 'marketData', 'bids')):
            book = payload(name)
            del book[field_name][side]
            with self.assertRaises(SchemaError):
                adapter.validate_book(book)
            book = payload(name)
            book[field_name][side] = []
            adapter.validate_book(book)  # An explicit empty ladder is valid; absence is not.
            book = payload(name)
            book[field_name][side].append(deepcopy(book[field_name][side][0]))
            with self.assertRaises(SchemaError):
                adapter.validate_book(book)

    def test_currency_timestamp_and_json_drift(self):
        book = payload('poly-book-live')
        book['marketData']['bids'][0]['px']['currency'] = 'EUR'
        with self.assertRaises(SchemaError):
            poly.validate_book(book)
        for stamp in (None, '2026-10-21T19:00:00', 'invalid'):
            book = payload('poly-book-live')
            book['marketData']['transactTime'] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(SchemaError):
                poly.validate_book(book)
        for body in (b'{"markets":[],"markets":[]}', b'{"value": NaN}', b'not JSON', b'\xff'):
            with self.assertRaises(SchemaError):
                load_json(body)
        self.assertEqual(load_json(b'{"tick":0.001}')['tick'], Decimal('0.001'))

    def test_metadata_bad_prices_and_empty_rules_remain_unverified(self):
        for adapter, name, price_key, rule_key in ((kalshi, 'kalshi-page', 'yes_bid_dollars', 'rules_primary'),
                                                   (poly, 'poly-page', 'bestBidQuote', 'description')):
            page = payload(name)
            page['markets'][0][rule_key] = ''
            adapter.validate_page(page)  # Preserve missing evidence; never approve equivalence.
            if adapter is kalshi:
                page['markets'][0][price_key] = '-1'
            else:
                page['markets'][0][price_key]['value'] = '-1'
            with self.assertRaises(SchemaError):
                adapter.validate_page(page)

    def test_source_age_includes_time_elapsed_after_receipt(self):
        # HYPOTHETICAL replay: receipt is recent but combined source age is too old.
        now = datetime(2026, 10, 21, 20, tzinfo=timezone.utc)
        received = (now - timedelta(seconds=30)).isoformat()
        source = (now - timedelta(seconds=70)).isoformat()
        self.assertEqual(book_freshness(source, received, now=now), 'STALE_SOURCE')

    def test_fresh_stale_future_and_unknown_source_timestamps(self):
        now = datetime(2026, 10, 21, 20, tzinfo=timezone.utc)
        receipt = now.isoformat()
        for source, at, expected in (
            (now.isoformat(), now, 'FRESH'),
            ((now - timedelta(seconds=61)).isoformat(), now, 'STALE_SOURCE'),
            ((now + timedelta(seconds=6)).isoformat(), now, 'FUTURE_SOURCE_TIME'),
            (None, now, 'UNKNOWN_SOURCE_TIME'),
            (receipt, now + timedelta(seconds=61), 'STALE_RECEIPT'),
            (receipt, now - timedelta(seconds=6), 'FUTURE_RECEIPT')):
            with self.subTest(expected=expected):
                self.assertEqual(book_freshness(source, receipt, now=at), expected)
        with self.assertRaises(ValueError):
            book_freshness(None, receipt, max_age=0)
