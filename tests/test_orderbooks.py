"""M3 pure book tests; changed and synthetic inputs are HYPOTHETICAL scenarios."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D, localcontext
from hashlib import sha256
import unittest

from predarb.orderbooks import normalize_rest, walk_depth
from predarb.book_stream import KalshiBookStream
from predarb.validation import dumps, load_json, utc_time
from helpers import FIXTURES, fixture, payload


def sample():
    return load_json((FIXTURES / 'm3-hypothetical.json').read_bytes())


def rest(venue='polymarket_us', *, data=None, meta=None, now=None, received=None, metadata_received=None):
    case = sample()
    key = 'kalshi' if venue == 'kalshi' else 'polymarket_us'
    meta = meta if meta is not None else case[key + '_metadata']
    source_id = meta['ticker' if venue == 'kalshi' else 'slug']
    return normalize_rest(venue, source_id, data if data is not None else case[key + '_rest'], meta,
                          received_at=received or case['clock'], metadata_received_at=metadata_received or case['clock'],
                          now=now or utc_time(case['clock']))


class BookNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.case = sample()
        self.now = utc_time(self.case['clock'])

    def test_m3_public_snapshots_preserve_hashes_and_replay_exact_assessments(self):
        capture = load_json((FIXTURES / 'm3-live-snapshots.json').read_bytes())
        self.assertFalse(capture['hypothetical'])
        self.assertEqual(len(capture['cases']), 3)
        for case in capture['cases']:
            with self.subTest(venue=case['venue'], source_id=case['source_id']):
                for raw in (case['metadata'], case['book']):
                    self.assertEqual(sha256(raw['body'].encode()).hexdigest(), raw['body_sha256'])
                    self.assertEqual(raw['status'], 200)
                now = utc_time(case['evaluated_at'])
                book = normalize_rest(case['venue'], case['source_id'], load_json(case['book']['body'].encode()),
                                      load_json(case['metadata']['body'].encode())['market'],
                                      received_at=case['book']['retrieved_at'],
                                      metadata_received_at=case['metadata']['retrieved_at'], now=now)
                self.assertEqual(dumps(book.as_dict(now=now)), dumps(case['expected']))
                self.assertEqual(book.as_dict(now=now)['data_usable'], case['venue'] == 'polymarket_us')

    def test_real_us_capture_semantics_tick_lot_and_depth(self):
        frame = fixture('poly-book-live')
        metadata = payload('poly-market-live')['market']
        now = utc_time(frame['retrieved_at'])
        book = normalize_rest('polymarket_us', metadata['slug'], payload('poly-book-live'), metadata,
                              received_at=frame['retrieved_at'], metadata_received_at=fixture('poly-market-live')['retrieved_at'], now=now)
        self.assertEqual(book.issues(now=now), ())
        self.assertEqual(book.yes_asks[0].price, D('0.6290'))
        self.assertEqual(book.no_asks[0].price, D('0.3720'))
        self.assertEqual(book.no_asks[0].quantity, D('5428.0000'))
        self.assertEqual(book.quantity_step, D('1'))
        self.assertIn('SYNTHETIC_NO', book.mechanism_no)
        self.assertFalse(book.as_dict(now=now)['trading_authorized'])

    def test_real_kalshi_capture_converts_bids_but_unknown_source_time_blocks_use(self):
        frame = fixture('kalshi-book-live')
        metadata = payload('kalshi-market-live')['market']
        now = utc_time(frame['retrieved_at'])
        book = normalize_rest('kalshi', metadata['ticker'], payload('kalshi-book-live'), metadata,
                              received_at=frame['retrieved_at'], metadata_received_at=fixture('kalshi-market-live')['retrieved_at'], now=now)
        self.assertEqual(book.yes_asks[0].price, D('0.9500'))
        self.assertEqual(book.yes_asks[0].quantity, D('7.00'))
        self.assertEqual(book.no_asks[0].price, D('0.9700'))
        self.assertEqual(book.issues(now=now), ('UNKNOWN_SOURCE_TIME',))
        self.assertIsNone(book.source_ts)
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_SOURCE_TIME'):
            walk_depth(book, 'YES', '1', now=now)

    def test_sorted_complementary_asks_preserve_fractional_quantities(self):
        book = rest('kalshi')
        self.assertEqual([(x.price,x.quantity) for x in book.yes_asks], [(D('.47'),D('1')), (D('.49'),D('4'))])
        self.assertEqual([(x.price,x.quantity) for x in book.no_asks], [(D('.58'),D('1.5')), (D('.59'),D('2'))])
        self.assertEqual(book.quantity_step, D('.01'))

    def test_depth_coverage_exhaustion_and_no_double_counting(self):
        book = rest()
        coverage = walk_depth(book, 'YES', D('3'), now=self.now)
        self.assertEqual((coverage.covered,coverage.quote_cost,coverage.complete), (D('3'),D('1.45'),True))
        self.assertEqual([level.quantity for level in coverage.levels], [D('1'),D('2')])
        exhausted = walk_depth(book, 'YES', '5', now=self.now)
        self.assertEqual((exhausted.covered,exhausted.quote_cost,exhausted.reason), (D('4'),D('1.94'),'DEPTH_EXHAUSTED'))
        self.assertFalse(exhausted.complete)
        self.assertEqual(walk_depth(book,'NO','7',now=self.now).quote_cost,D('4.16'))

    def test_depth_revalidates_age_and_rejects_bad_quantity_and_side(self):
        book = rest()
        with self.assertRaisesRegex(ValueError, 'STALE'):
            walk_depth(book,'YES','1',now=self.now+timedelta(seconds=61))
        for side, quantity in (('MAYBE','1'),('YES','0'),('YES','NaN'),('YES','.5'),('YES',0.5)):
            with self.subTest(side=side, quantity=quantity), self.assertRaises(ValueError):
                walk_depth(book,side,quantity,now=self.now)

    def test_freshness_receipt_source_metadata_future_and_no_clock_substitution(self):
        for change,expected in (('source','STALE_SOURCE'),('receipt','STALE_RECEIPT'),('metadata','STALE_METADATA'),
                                ('future','FUTURE_SOURCE'),('future_receipt','FUTURE_RECEIPT')):
            data = deepcopy(self.case['polymarket_us_rest'])
            received = metadata_received = self.case['clock']
            if change == 'source': data['marketData']['transactTime'] = (self.now-timedelta(seconds=61)).isoformat()
            if change == 'receipt': received = metadata_received = (self.now-timedelta(seconds=61)).isoformat()
            if change == 'metadata': metadata_received = (self.now-timedelta(seconds=61)).isoformat()
            if change == 'future': data['marketData']['transactTime'] = (self.now+timedelta(seconds=6)).isoformat()
            if change == 'future_receipt': received = (self.now+timedelta(seconds=6)).isoformat()
            book = rest(data=data,received=received,metadata_received=metadata_received)
            self.assertIn(expected,book.issues(now=self.now))
        book = rest(metadata_received=(self.now+timedelta(seconds=1)).isoformat())
        self.assertIn('METADATA_AFTER_BOOK',book.issues(now=self.now))
        with self.assertRaises(ValueError): book.issues(now=self.now,max_age=0)
        with self.assertRaises(ValueError): book.issues(now=self.now.replace(tzinfo=None))

    def test_missing_empty_and_partial_ladders_fail_closed(self):
        for venue,key,sides in (('kalshi','orderbook_fp',('yes_dollars','no_dollars')),
                                 ('polymarket_us','marketData',('bids','offers'))):
            for change in ('missing','empty','partial'):
                data = deepcopy(self.case[venue+'_rest'])
                if change=='missing': del data[key][sides[0]]
                else:
                    data[key][sides[0]]=[]
                    if change=='empty': data[key][sides[1]]=[]
                book=rest(venue,data=data)
                with self.subTest(venue=venue,change=change):
                    self.assertTrue(book.rejections)
                    self.assertFalse(book.as_dict(now=self.now)['data_usable'])
                    with self.assertRaises(ValueError): walk_depth(book,'YES','1',now=self.now)

    def test_crossed_or_locked_data_rejected_for_both_venues(self):
        for locked in (True,False):
            k=deepcopy(self.case['kalshi_rest'])
            k['orderbook_fp']['yes_dollars']=[['0.4700' if locked else '0.4800','1.00']]
            p=deepcopy(self.case['polymarket_us_rest'])
            p['marketData']['bids']=[{'px':{'value':'0.4700' if locked else '0.4800','currency':'USD'},'qty':'1'}]
            for venue,data in (('kalshi',k),('polymarket_us',p)):
                book=rest(venue,data=data)
                with self.subTest(venue=venue,locked=locked):
                    self.assertIn('crossed or locked',';'.join(book.rejections))
                    self.assertEqual(book.yes_asks,())

    def test_tick_and_lot_validation_missing_unknown_off_grid(self):
        for venue in ('kalshi','polymarket_us'):
            for change in ('price','quantity','missing_tick','missing_lot','unknown_lot'):
                meta=deepcopy(self.case[venue+'_metadata']);data=deepcopy(self.case[venue+'_rest'])
                if venue=='kalshi':
                    if change=='price': data['orderbook_fp']['yes_dollars'][0][0]='0.4101'
                    elif change=='quantity': data['orderbook_fp']['yes_dollars'][0][1]='1.001'
                    elif change=='missing_tick': del meta['price_ranges']
                    else: continue  # Kalshi's documented count granularity is .01; no invented per-market field.
                else:
                    if change=='price': data['marketData']['bids'][0]['px']['value']='0.4201'
                    if change=='quantity': data['marketData']['bids'][0]['qty']='1.5'
                    if change=='missing_tick': del meta['orderPriceMinTickSize']
                    if change=='missing_lot': del meta['minimumTradeQty']
                    if change=='unknown_lot': meta['minimumTradeQty']='2'
                book=rest(venue,data=data,meta=meta)
                with self.subTest(venue=venue,change=change): self.assertTrue(book.rejections)

    def test_piecewise_price_ranges_use_grid_not_structure_label(self):
        meta=deepcopy(self.case['kalshi_metadata'])
        meta['price_level_structure']='HYPOTHETICAL_NEW_LABEL'
        meta['price_ranges']=[{'start':'0','end':'.1','step':'.001'}, {'start':'.1','end':'.9','step':'.01'}, {'start':'.9','end':'1','step':'.001'}]
        data=deepcopy(self.case['kalshi_rest']);data['orderbook_fp']['yes_dollars']=[['.091','1']]
        book=rest('kalshi',data=data,meta=meta)
        self.assertEqual(book.rejections,())
        self.assertEqual(book.no_asks[0].price,D('.909'))
        for bands in ([], [{'start':'0','end':'.5','step':'.01'}],
                      [{'start':'0','end':'.5','step':'.01'},{'start':'.4','end':'1','step':'.01'}],
                      [{'start':'0','end':'1','step':'0'}]):
            meta['price_ranges']=bands
            self.assertTrue(rest('kalshi',meta=meta).rejections)

    def test_fractional_us_lots_supported_only_when_metadata_confirms(self):
        meta=deepcopy(self.case['polymarket_us_metadata']);meta['minimumTradeQty']='.01'
        data=deepcopy(self.case['polymarket_us_rest']);data['marketData']['offers'][0]['qty']='.50'
        book=rest(data=data,meta=meta)
        self.assertEqual(book.issues(now=self.now),())
        self.assertEqual(walk_depth(book,'YES','.25',now=self.now).quote_cost,D('.1175'))

    def test_ambiguous_us_side_identity_currency_closed_and_nonbinary_rejected(self):
        for change in ('side','tradable','identity','currency','state','closed','same_long'):
            meta=deepcopy(self.case['polymarket_us_metadata']);data=deepcopy(self.case['polymarket_us_rest'])
            if change=='side': meta['marketSides'][0]['identifier']='HYPOTHETICAL-WRONG'
            if change=='tradable': meta['marketSides'][0]['tradable']=False
            if change=='identity': data['marketData']['marketSlug']='HYPOTHETICAL-WRONG'
            if change=='currency': data['marketData']['bids'][0]['px']['currency']='EUR'
            if change=='state': data['marketData']['state']='MARKET_STATE_HALTED'
            if change=='closed': meta['closed']=True
            if change=='same_long': meta['marketSides'][1]['long']=True
            with self.subTest(change=change): self.assertTrue(rest(data=data,meta=meta).rejections)
        meta=deepcopy(self.case['kalshi_metadata']);meta['market_type']='scalar'
        self.assertTrue(rest('kalshi',meta=meta).rejections)

    def test_invalid_prices_quantities_duplicates_and_precision_do_not_leak_partial_depth(self):
        for invalid in ('NaN','Infinity','-1','0','1','1.1','0.'+'9'*40):
            data=deepcopy(self.case['polymarket_us_rest']);data['marketData']['offers'][1]['px']['value']=invalid
            self.assertEqual(rest(data=data).yes_asks,())
        data=deepcopy(self.case['kalshi_rest']);data['orderbook_fp']['yes_dollars'].append(data['orderbook_fp']['yes_dollars'][0])
        self.assertTrue(rest('kalshi',data=data).rejections)
        for invalid in ('0','NaN','-1','0.0000000001'):
            data=deepcopy(self.case['polymarket_us_rest']);data['marketData']['offers'][0]['qty']=invalid
            self.assertTrue(rest(data=data).rejections)

    def test_decimal_context_cannot_round_complement_or_depth_cost(self):
        with localcontext() as context:
            context.prec=3
            meta=deepcopy(self.case['polymarket_us_metadata']);meta['minimumTradeQty']='.01'
            meta['orderPriceMinTickSize']='.0001'
            data=deepcopy(self.case['polymarket_us_rest']);data['marketData']['offers'][0].update(px={'value':'.4713','currency':'USD'},qty='123.45')
            book=rest(data=data,meta=meta)
            self.assertEqual(walk_depth(book,'YES','123.45',now=self.now).quote_cost,D('58.181985'))

    def test_known_close_time_is_rechecked_during_depth_use(self):
        meta=deepcopy(self.case['polymarket_us_metadata'])
        meta['endDate']=(self.now+timedelta(seconds=30)).isoformat()
        book=rest(meta=meta)
        self.assertEqual(book.issues(now=self.now),())
        with self.assertRaisesRegex(ValueError,'MARKET_CLOSED'):
            walk_depth(book,'YES','1',now=self.now+timedelta(seconds=31))
