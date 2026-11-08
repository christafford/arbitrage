"""M5Q synthetic economics and genuine replay-observer regression tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
import unittest

from predarb.economic_signals import reconstruct, Episodes
from predarb.quality_capture import validate_window, validate_config, VERSION, replay
from predarb.validation import load_json, utc_time
from test_continuous_research import hypothetical
import test_quality_recovery


class SignalTests(unittest.TestCase):
    def setUp(self):self.data,self.at,self.books,self.pair=hypothetical()

    def row(self,books=None,pair=None):
        books=self.books if books is None else books
        return reconstruct(books,pair or self.pair,at=self.at,
                           inspected=[b.as_dict(now=self.at) for b in books],provenance={'hypothetical':True})

    def test_discovery_arithmetic_preserves_class_and_unknowns(self):
        r=self.row(pair=dict(self.pair,classification='DISCOVERY'))
        self.assertEqual(r['classification'],'DISCOVERY')
        self.assertEqual(r['status'],'DISCOVERY_QUOTE_DISCREPANCY')
        self.assertFalse(r['strict_arbitrage_eligible'])
        self.assertFalse(r['trading_authorized'])
        self.assertIn('BLOCKED',r['reverse_direction'])
        for c in r['capital_cases']:
            self.assertIsNone(c['fee_adjusted_edge_usd'])
            self.assertIsNone(c['buying_power_required_usd'])
            self.assertIsNone(c['actual_fills'])
            self.assertEqual(sum(c['one_leg_only_loss_before_fees_usd'].values()),c['prefee_capital_usd'])
            self.assertEqual(sum(x['quote_cost'] for x in c['displayed_depth_walks']),c['prefee_capital_usd'])

    def test_missing_stale_invalid_partial_and_clock_fail_closed(self):
        for b in [replace(self.books[1],source_ts=None),
                  replace(self.books[1],source_ts=(self.at-timedelta(seconds=3)).isoformat()),
                  replace(self.books[1],rejections=('INVALID_BOOK:off-grid',)),
                  replace(self.books[1],rejections=('PARTIAL_BOOK',)),
                  replace(self.books[1],rejections=('LOCAL_CLOCK_UNVERIFIED',))]:
            self.assertEqual(self.row([self.books[0],b])['capital_cases'],[])

    def test_depth_limits_and_exact_budget(self):
        from predarb.models import AskLevel
        b=replace(self.books[0],no_asks=(AskLevel(D('.4'),D(2)),))
        for c in self.row([b,self.books[1]])['capital_cases']:
            self.assertEqual(c['maximum_matched_displayed_quantity'],D(2))
            self.assertLessEqual(c['prefee_capital_usd'],D(c['quote_only_budget_usd']))
            self.assertEqual(c['gross_edge_usd'],D('.26'))

    def test_unknown_class_wrong_identity_and_short_route_rejected(self):
        for p in [dict(self.pair,classification='STRICT'),dict(self.pair,kalshi_id='wrong')]:
            with self.assertRaises(ValueError):self.row(pair=p)
        with self.assertRaises(ValueError):self.row([replace(self.books[0],mechanism_no='SHORT'),self.books[1]])

    def test_unchanged_depth_refresh_not_new_depth_opportunity(self):
        a=self.row();b=self.row([replace(x,source_ts=(self.at-timedelta(microseconds=1)).isoformat()) for x in self.books])
        self.assertEqual(a['depth_state_sha256'],b['depth_state_sha256'])
        self.assertNotEqual(a['source_state_sha256'],b['source_state_sha256'])

    def test_episodes_repeated_states_gap_and_rejection(self):
        f=load_json((Path(__file__).parent/'fixtures/m5q-episodes-hypothetical.json').read_bytes())
        self.assertTrue(f['hypothetical']);e=Episodes();base=self.row()
        for sec,positive,depth in zip(f['seconds'],f['positive'],f['depth_states']):
            r=deepcopy(base);r['at']=(self.at+timedelta(seconds=sec)).isoformat()
            r['depth_state_sha256']=depth
            if not positive:r['capital_cases']=[]
            e.add(r)
        result=e.report()
        self.assertEqual(len(result),f['expected_episodes'])
        self.assertEqual(sum(r['samples'] for r in result),f['expected_positive_samples'])
        self.assertEqual(len(e.depths),f['expected_distinct_depth_states'])
        self.assertEqual(result[0]['sampled_span_seconds'],D(2))
        self.assertIsNone(result[0]['continuous_opportunity_seconds'])
        with self.assertRaises(ValueError):e.add(r)

    def test_class_and_source_version_changes_split_episodes(self):
        e=Episodes();r=self.row();e.add(r)
        r=deepcopy(r);r['at']=(self.at+timedelta(seconds=1)).isoformat();r['classification']='DISCOVERY';e.add(r)
        r=deepcopy(r);r['at']=(self.at+timedelta(seconds=2)).isoformat();r['source_versions']['kalshi']='changed';e.add(r)
        self.assertEqual(len(e.report()),3)

    def test_one_pair_scope_is_explicit_fixed_and_never_renews(self):
        validate_window(900,[self.pair],scope='M5Q')
        c=dict(schema=VERSION,scope='M5Q',seconds=900,pairs=[self.pair],started_at=self.at.isoformat(),
               deadline_at=(self.at+timedelta(seconds=900)).isoformat())
        validate_config(c)
        for change in [dict(scope='M5P'),dict(scope='unknown'),dict(seconds=300),dict(pairs=[self.pair]*2),
                       dict(deadline_at=(self.at+timedelta(seconds=901)).isoformat())]:
            with self.assertRaises(ValueError):validate_config(dict(c,**change))


class SignalReplayTests(unittest.TestCase):
    def test_genuine_observer_receives_only_verified_historical_states(self):
        # Reuse the exact genuine fixture setup without inheriting duplicate tests.
        source=test_quality_recovery.GenuineEventReplay();source.setUp()
        try:
            seen=[]
            def observe(saved,engine):
                seen.append(saved['at'])
                self.assertEqual(saved['quality']['timestamp_depth_overlap'],
                    engine.assess(saved['channel'],utc_time(saved['at']))['quality']['timestamp_depth_overlap'])
            audit=replay(source.root,source.fixture['pair'],source.fixture['config'],sample_observer=observe)
            self.assertEqual(len(seen),audit['samples'])
            self.assertEqual(audit['replay'],'PASS')
        finally:source.doCleanups()


class ReconstructionCommandTests(unittest.TestCase):
    @staticmethod
    def module():
        import importlib.util
        path=Path(__file__).parents[1]/'scripts/m5q_reconstruct.py'
        spec=importlib.util.spec_from_file_location('m5q_reconstruct',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_book_roundtrip_and_missing_field_fail_closed(self):
        from predarb.validation import dumps
        _,at,books,_=hypothetical()
        for b in books:
            data=load_json(dumps(b.as_dict(now=at)))
            self.assertEqual(self.module().typed_book(data),b)
            del data['source_ts']
            with self.assertRaises(KeyError):self.module().typed_book(data)

    def test_missing_audit_is_quarantined_not_ranked(self):
        import tempfile
        from predarb.validation import dumps
        _,_,_,pair=hypothetical()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config.json').write_text(dumps({'pairs':[pair]}))
            folder=root/pair['id']/'segment-001';folder.mkdir(parents=True)
            (folder/'observations.jsonl').touch()
            results=list(self.module().m5o_window(root))
            self.assertEqual(len(results),1)
            self.assertTrue(results[0][0]['quarantined'])
            self.assertEqual(results[0][1],[])

    def test_genuine_selection_bytes_schema_and_source_identity(self):
        import hashlib
        from predarb import kalshi,polymarket_us
        from predarb.sports_discovery import features,key
        f=load_json((Path(__file__).parent/'fixtures/m5q-selection-live.json').read_bytes())
        self.assertFalse(f['hypothetical']);identities=[]
        for r in f['responses']:
            self.assertEqual(hashlib.sha256(r['body'].encode()).hexdigest(),r['sha256'])
            utc_time(r['received_at'])
            adapter=kalshi if r['venue']=='kalshi' else polymarket_us
            self.assertEqual(r['schema_version'],adapter.SCHEMA_VERSION)
            data=load_json(r['body'])
            if r['endpoint'].endswith(('/book','/orderbook')):adapter.validate_book(data)
            else:
                adapter.validate_detail(data);identities.append(key(features(data['market'])))
        self.assertEqual(len(identities),6)
        for a,b in zip(identities[::2],identities[1::2]):
            self.assertIsNotNone(a);self.assertEqual(a,b)
