"""HYPOTHETICAL Kalshi protocol replay; no sockets, credentials or real trades."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
import unittest

from predarb.book_stream import KalshiBookStream, StreamProtocolError
from predarb.orderbooks import walk_depth
from predarb.validation import utc_time
from test_orderbooks import sample


class StreamReplayTests(unittest.TestCase):
    def setUp(self):
        self.case=sample();self.now=utc_time(self.case['clock'])
        self.stream=KalshiBookStream(self.case['kalshi_metadata']['ticker'],self.case['kalshi_metadata'],
                                      metadata_received_at=self.case['clock'])

    def snapshot(self,seq=10,clock=100,sid=7):
        frame=deepcopy(self.case['kalshi_ws_snapshot']);frame.update(seq=seq,sid=sid)
        frame['msg']['clock']=clock
        frame['sending_ts_ms']+=seq-10
        return frame

    def delta(self,seq=11,clock=101,side='yes',price='.4200',quantity='-.50'):
        frame=self.snapshot(seq,clock)
        frame['type']='orderbook_delta'
        frame['msg']={key:value for key,value in frame['msg'].items() if key not in {'yes_dollars_fp','no_dollars_fp'}}
        frame['msg'].update(side=side,price_dollars=price,delta_fp=quantity)
        return frame

    def apply(self,frame,*,generation=None):
        return self.stream.apply(frame,received_at=self.case['clock'],now=self.now,
                                 generation=self.stream.generation if generation is None else generation)

    def test_snapshot_positive_depth_and_exact_signed_updates(self):
        first=self.apply(self.snapshot())
        self.assertEqual(first.issues(now=self.now),())
        self.assertEqual(first.timestamp_kind,'PROVIDER_SEND_TIME')
        self.assertEqual(first.sequence,10)
        updated=self.apply(self.delta())
        self.assertEqual(updated.no_asks[0].quantity,D('1.00'))
        self.assertEqual(walk_depth(updated,'NO','1',now=self.now).quote_cost,D('.58'))
        self.apply(self.delta(12,101,price='.4300',quantity='1.00'))
        self.assertEqual(self.stream.current.no_asks[0].price,D('.57'))
        removed=self.apply(self.delta(13,102,price='.4300',quantity='-1.00'))
        self.assertEqual(removed.no_asks[0].price,D('.58'))

    def test_delta_without_snapshot_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'snapshot required'): self.apply(self.delta())
        self.assertIsNone(self.stream.current)
        self.assertEqual(self.stream.state,'NEEDS_SNAPSHOT')

    def test_gap_duplicate_out_of_order_requires_full_snapshot(self):
        for seq in (10,9,12):
            self.stream.reconnect();self.apply(self.snapshot())
            frame=self.delta(seq);frame['sending_ts_ms']=self.snapshot()['sending_ts_ms']+1
            with self.subTest(seq=seq), self.assertRaisesRegex(ValueError,'sequence gap'): self.apply(frame)
            self.assertIsNone(self.stream.current)
            with self.assertRaisesRegex(ValueError,'fresh snapshot'): self.apply(self.delta(13,103))
            recovered=self.apply(self.snapshot(14,104))
            self.assertEqual(recovered.sequence,14)
            self.assertEqual(self.stream.state,'SYNCED')

    def test_late_snapshot_cannot_bypass_detected_sequence_gap(self):
        self.apply(self.snapshot())
        with self.assertRaises(ValueError): self.apply(self.delta(100,200))
        late=self.snapshot(11,201);late['sending_ts_ms']+=100
        with self.assertRaisesRegex(ValueError,'every observed frame'): self.apply(late)
        recovered=self.snapshot(101,202);recovered['sending_ts_ms']+=100
        self.assertEqual(self.apply(recovered).sequence,101)

    def test_disconnect_reconnect_resets_subscription_and_book_state(self):
        self.apply(self.snapshot());previous=self.stream.generation
        self.stream.disconnect()
        with self.assertRaisesRegex(ValueError,'reconnect required'): self.apply(self.snapshot(11,101))
        self.stream.reconnect()
        with self.assertRaisesRegex(ValueError,'generation'): self.apply(self.snapshot(1,1,sid=8),generation=previous)
        self.assertIsNone(self.stream.current)
        self.assertEqual(self.apply(self.snapshot(1,1,sid=8)).sequence,1)

    def test_clock_can_repeat_on_deltas_and_skip_but_not_regress_or_overlap_snapshot(self):
        self.apply(self.snapshot());self.apply(self.delta(11,200))
        self.apply(self.delta(12,200,quantity='.25'))
        self.apply(self.delta(13,1000,quantity='.25'))
        with self.assertRaisesRegex(ValueError,'clock regressed'): self.apply(self.delta(14,999))
        self.stream.reconnect();self.apply(self.snapshot())
        with self.assertRaisesRegex(ValueError,'overlaps'): self.apply(self.delta(11,100))

    def test_wrong_market_subscription_identity_and_missing_time_invalidate(self):
        for change in ('market','sid','market_id','time','clock','message_type'):
            self.stream.reconnect();self.apply(self.snapshot());frame=self.delta()
            if change=='market': frame['msg']['market_ticker']='HYPOTHETICAL-OTHER'
            if change=='sid': frame['sid']=99
            if change=='market_id': frame['msg']['market_id']='HYPOTHETICAL-OTHER-ID'
            if change=='time': del frame['sending_ts_ms']
            if change=='clock': del frame['msg']['clock']
            if change=='message_type': frame['type']='unknown_protocol_shape'
            with self.subTest(change=change), self.assertRaises(ValueError): self.apply(frame)
            self.assertIsNone(self.stream.current)

    def test_protocol_clock_and_source_time_types_ranges_and_absence_fail_closed(self):
        for key,label,maximum in (('clock','MARKET_CLOCK',2**63-1),
                                  ('sending_ts_ms','SOURCE_TIMESTAMP',253402300799999)):
            for value in (None,True,'HYPOTHETICAL_SECRET',-1,maximum+1):
                with self.subTest(key=key,value=value):
                    self.stream.reconnect();self.apply(self.snapshot());frame=self.delta()
                    (frame['msg'] if key=='clock' else frame)[key]=value
                    with self.assertRaises(StreamProtocolError) as caught:self.apply(frame)
                    self.assertEqual(caught.exception.code,'INVALID_'+label)
                    self.assertNotIn('HYPOTHETICAL_SECRET',str(caught.exception))
                    self.assertIsNone(self.stream.current)
            self.stream.reconnect();frame=self.snapshot()
            del (frame['msg'] if key=='clock' else frame)[key]
            with self.assertRaises(StreamProtocolError) as caught:self.apply(frame)
            self.assertEqual(caught.exception.code,'MISSING_'+label)
        with self.assertRaisesRegex(ValueError,'unknown'):StreamProtocolError('HYPOTHETICAL_SECRET')

    def test_negative_depth_off_grid_delta_or_price_and_crossing_invalidate(self):
        for quantity,price in (('-2.00','.42'),('.001','.42'),('NaN','.42'),('1','.4201'),('1','.48')):
            self.stream.reconnect();self.apply(self.snapshot())
            with self.subTest(quantity=quantity,price=price), self.assertRaises(ValueError):
                self.apply(self.delta(quantity=quantity,price=price))
            self.assertIsNone(self.stream.current)

    def test_full_snapshot_replaces_instead_of_merging_old_levels(self):
        self.apply(self.snapshot());replacement=self.snapshot(11,101)
        replacement['msg']['yes_dollars_fp']=[['.30','2.00']]
        replacement['msg']['no_dollars_fp']=[['.60','1.00']]
        updated=self.apply(replacement)
        self.assertEqual([(level.price,level.quantity) for level in updated.no_asks],[(D('.70'),D('2'))])
        self.assertEqual(len(self.stream.yes),1)

    def test_source_and_receipt_ages_are_rechecked_after_replay(self):
        book=self.apply(self.snapshot())
        with self.assertRaisesRegex(ValueError,'STALE'):
            walk_depth(book,'YES','1',now=self.now+timedelta(seconds=61))
        frame=self.delta();frame['sending_ts_ms']-=100
        with self.assertRaisesRegex(ValueError,'timestamp regressed'): self.apply(frame)

    def test_partial_snapshot_keeps_continuity_but_exposes_no_usable_depth(self):
        frame=self.snapshot();frame['msg']['yes_dollars_fp']=[]
        book=self.apply(frame)
        self.assertIn('PARTIAL_BOOK',book.rejections)
        self.assertEqual(self.stream.state,'SYNCED')
        with self.assertRaises(ValueError): walk_depth(book,'YES','1',now=self.now)
        repaired=self.apply(self.delta(quantity='1.00'))
        self.assertEqual(repaired.issues(now=self.now),())

    def test_metadata_grid_change_discards_prior_depth_and_requires_new_snapshot(self):
        self.apply(self.snapshot())
        metadata=deepcopy(self.case['kalshi_metadata'])
        metadata['price_ranges']=[{'start':'0','end':'1','step':'.02'}]
        self.stream.replace_metadata(metadata,received_at=self.case['clock'])
        self.assertIsNone(self.stream.current)
        with self.assertRaisesRegex(ValueError,'snapshot required'):
            self.apply(self.delta())
        frame=self.snapshot(12,102)
        frame['msg']['yes_dollars_fp']=[['.42','1.50']]
        frame['msg']['no_dollars_fp']=[['.52','1.00']]
        self.assertEqual(self.apply(frame).yes_asks[0].price,D('.48'))

    def test_invalid_depth_does_not_allow_clock_or_send_time_frontier_to_move_back(self):
        self.apply(self.snapshot())
        bad=self.delta(11,200,quantity='-99');bad['sending_ts_ms']+=10
        with self.assertRaisesRegex(ValueError,'negative'): self.apply(bad)
        with self.assertRaisesRegex(ValueError,'clock regressed'): self.apply(self.snapshot(12,150))
        with self.assertRaisesRegex(ValueError,'timestamp regressed'): self.apply(self.snapshot(13,201))
        recovered=self.snapshot(14,202);recovered['sending_ts_ms']+=10
        self.assertEqual(self.apply(recovered).sequence,14)
