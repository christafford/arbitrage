"""Actual public identity examples; altered contracts/scopes are HYPOTHETICAL."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from predarb import cli, discovery as d, sports_discovery as s, registry
from predarb.store import connect
from predarb.validation import load_json, utc_time
from helpers import fixture


class SportsIdentityTests(unittest.TestCase):
    def setUp(self):
        self.evidence = fixture('sports-discovery-live')
        self.k, self.p = [load_json(self.evidence['pairs'][1][v]['body'])['market']
                          for v in ('kalshi', 'polymarket_us')]

    def compare(self, k=None, p=None, **kwargs):
        return d.compare(d.features(self.k if k is None else k), d.features(self.p if p is None else p), **kwargs)

    def test_actual_same_event_pairs_survive_alias_and_midnight_clock_differences(self):
        self.assertFalse(self.evidence['hypothetical'])
        for pair in self.evidence['pairs']:
            with self.subTest(pair=pair['kalshi']['source_id']):
                features = []
                for venue in ('kalshi', 'polymarket_us'):
                    raw = pair[venue]
                    self.assertEqual(hashlib.sha256(raw['body'].encode()).hexdigest(), raw['body_sha256'])
                    features.append(d.features(load_json(raw['body'])['market']))
                result = d.compare(*features)
                self.assertIsNotNone(result)
                self.assertEqual(result[1]['sports_identity'], 'MATCH')
                self.assertEqual(result[1]['settlement_equivalence'], 'UNVERIFIED')
                self.assertIn('SPORTS_SETTLEMENT_REVIEW_REQUIRED', result[2])
                self.assertIn('OCCURRENCE_AND_START_TIMES_NOT_COMPARABLE', result[2])
                self.assertEqual(features[0]['sports']['scheduled_date'], '2026-10-25')
                self.assertEqual(features[1]['sports']['scheduled_date'], '2026-10-25')
                warning = ('POSTPONEMENT_WINDOW_CONFLICT' if result[1]['league'] == 'NFL'
                           else 'POSTPONEMENT_WINDOW_INTERPRETATION_REQUIRED')
                self.assertIn(warning, result[2])

    def test_actual_non_sports_categories_with_generic_future_metadata(self):
        for item in fixture('us-category-futures-live')['records']:
            with self.subTest(category=item['label']):
                self.assertEqual(hashlib.sha256(item['body'].encode()).hexdigest(),item['body_sha256'])
                contract=load_json(item['body'])['market']
                self.assertEqual(s.features(contract) is not None,item['expected_sports_gate'])
                envelope=deepcopy(contract)
                envelope['uninterpreted_metadata']={key:envelope.pop(key) for key in
                    ('category','sportsMarketType','sportsMarketTypeV2') if key in envelope}
                self.assertEqual(s.features(envelope) is not None,item['expected_sports_gate'])

    def test_non_sports_future_exception_requires_explicit_category_and_known_types(self):
        # These modifications are HYPOTHETICAL compatibility/error scenarios.
        contract={'title':'Bitcoin price','category':'crypto','sportsMarketType':'futures',
                  'sportsMarketTypeV2':'SPORTS_MARKET_TYPE_FUTURE'}
        self.assertIsNone(s.features(contract))
        for changes in ({'category':None},{'category':'unknown-category'},
                        {'category':'sports'}, {'sportsMarketType':'basketball_team_full_game_winner'},
                        {'sportsMarketTypeV2':'SPORTS_MARKET_TYPE_NEW'},
                        {'sportsMarketTypeV2':'SPORTS_MARKET_TYPE_UNSPECIFIED'},
                        {'ticker':'KXNBAGAME-HYPOTHETICAL'}, {'slug':'aec-nfl-hypothetical'},
                        {'description':'A professional basketball game'},
                        {'marketSides':[{'team':{'league':'NBA','name':'Lakers'}}]}):
            with self.subTest(changes=changes):
                self.assertIsNotNone(s.features(dict(contract,**changes)))

    def test_actual_soccer_college_football_false_match_is_excluded(self):
        rows = self.evidence['unrelated_sports']
        for row in rows:
            self.assertEqual(hashlib.sha256(row['body'].encode()).hexdigest(), row['body_sha256'])
        features = [d.features(load_json(row['body'])['market']) for row in rows]
        self.assertTrue(all(f['sports'] is not None for f in features))
        self.assertTrue(all(not f['sports']['supported'] for f in features))
        self.assertIsNone(d.compare(*features))
        self.assertIsNone(d.compare(features[0], features[0]))

    def test_missing_bad_or_conflicting_date_never_falls_back_to_clocks_or_identifier(self):
        for replacement in ('Oct 26, 2026', 'Feb 30, 2026', '2030-01-01', 'an unknown date'):
            p = deepcopy(self.p)
            p['description'] = p['description'].replace('Oct 25, 2026', replacement)
            self.assertIsNone(self.compare(p=p), replacement)
        p = deepcopy(self.p); p['description'] += ' Also scheduled for Oct 26, 2026.'
        self.assertIsNone(self.compare(p=p))

    def test_ambiguous_la_and_conflicting_selected_team_are_excluded(self):
        k = deepcopy(self.k)
        k['rules_primary'] = k['rules_primary'].replace('Los Angeles L', 'Los Angeles')
        self.assertIsNone(self.compare(k=k))
        k = deepcopy(self.k); k['yes_sub_title'] = 'Utah'
        self.assertIsNone(self.compare(k=k))
        p = deepcopy(self.p)
        for side in p['marketSides']: side['long'] = not side['long']
        self.assertIsNone(self.compare(p=p))

    def test_opponent_and_league_conflicts_are_excluded(self):
        p = deepcopy(self.p)
        p['description'] = p['description'].replace('UTA Jazz', 'PHX Suns')
        self.assertIsNone(self.compare(p=p))
        for side in p['marketSides']: side['team']['league'] = 'nfl'
        self.assertIsNone(self.compare(p=p))
        k = deepcopy(self.k); k['ticker'] = k['ticker'].replace('KXNBA', 'KXNFL')
        self.assertIsNone(self.compare(k=k))
        p = deepcopy(self.p); p['slug'] = p['slug'].replace('aec-nba-', 'aec-nfl-')
        self.assertIsNone(self.compare(p=p))

    def test_props_spreads_period_markets_and_unknown_types_are_excluded(self):
        for key, value in [('sportsMarketType', 'basketball_team_first_half_winner'),
                           ('sportsMarketType', 'basketball_player_total_points'),
                           ('sportsMarketTypeV2', 'SPORTS_MARKET_TYPE_SPREAD'),
                           ('marketType', 'spread'), ('sportsMarketType', None)]:
            p = deepcopy(self.p); p[key] = value
            self.assertIsNone(self.compare(p=p), (key, value))
        k = deepcopy(self.k); k['ticker'] = k['ticker'].replace('GAME', 'SPREAD')
        self.assertIsNone(self.compare(k=k))

    def test_missing_malformed_or_multiple_side_mappings_are_not_inferred(self):
        for transform in [lambda p:p.pop('marketSides'),
                          lambda p:p['marketSides'].pop(),
                          lambda p:p['marketSides'][0].pop('team'),
                          lambda p:p['marketSides'][0]['team'].pop('league'),
                          lambda p:p['marketSides'][1].update(long=True),
                          lambda p:p['marketSides'][1].update(identifier='different'),
                          lambda p:p['marketSides'][0].update(description='Clippers')]:
            p = deepcopy(self.p); transform(p)
            self.assertIsNone(self.compare(p=p))

    def test_league_scoped_names_and_explicit_abbreviations(self):
        for league, name, expected in [('NBA','NY Knicks','NYK'),('NBA','GS Warriors','GSW'),
                                       ('NBA','NO Pelicans','NOP'),('NBA','PHO Suns','PHX'),
                                       ('NBA','SA Spurs','SAS'),('NBA','Los Angeles L','LAL'),
                                       ('NFL','Los Angeles R','LAR'),('NFL','New York G','NYG')]:
            self.assertEqual(s.team(league, name), expected)
        self.assertIsNone(s.team('NBA', 'Los Angeles'))
        self.assertIsNone(s.team('NFL', 'New York'))
        self.assertIsNone(s.team('NBA', 'Broncos'))
        self.assertIsNone(s.team('NFL', 'Nuggets'))

    def test_unknown_postponement_does_not_gain_equivalence_or_invent_duration(self):
        p = deepcopy(self.p)
        p['description'] = p['description'].replace('within two calendar days', 'within a venue-defined period')
        result = self.compare(p=p)
        self.assertIn('POSTPONEMENT_WINDOW_UNKNOWN', result[2])
        score = result[0]
        self.assertEqual(self.compare(p=p, min_score=score)[0], score)
        self.assertIsNone(self.compare(p=p, min_score=score+1))

    def test_parsing_survives_registry_metadata_envelope(self):
        p = deepcopy(self.p)
        fields = ('category', 'sportsMarketType', 'sportsMarketTypeV2', 'marketType', 'gameStartTime')
        p['uninterpreted_metadata'] = {field:p.pop(field) for field in fields if field in p}
        self.assertEqual(self.compare(p=p), self.compare())


class SportsQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name)/'test.sqlite3')
        self.db = connect(self.path); self.addCleanup(self.db.close)
        self.now = utc_time('2026-10-25T19:00:00Z')
        # Actual public payloads embedded in an explicitly hypothetical registry
        # test. No real decisions or live eligibility are manufactured.
        self.pair = fixture('sports-discovery-live')['pairs'][1]
        for venue, source in [('kalshi','HYPOTHETICAL-K'),('polymarket_us','HYPOTHETICAL-P')]:
            contract = load_json(self.pair[venue]['body'])['market']
            registry._record_instrument(self.db,venue,source,contract,observed_at=self.now.isoformat(),
                                        available=True,hypothetical=True,now=self.now)

    def test_index_retrieves_same_game_without_generic_word_overlap_and_preserves_rejection(self):
        report = d.refresh_queue(self.db, now=self.now, sports_only=True)
        self.assertEqual(len(report['candidates']), 1)
        candidate = report['candidates'][0]
        self.assertEqual(candidate['match_basis'], 'SPORTS_EVENT_IDENTITY')
        self.assertFalse(candidate['equivalence_verified'])
        self.assertEqual(candidate['status'], 'UNVERIFIED')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0], 0)
        pair = registry.propose(self.db, 'HYPOTHETICAL-K','HYPOTHETICAL-P','HYPOTHETICAL human',now=self.now)
        registry.decide(self.db,pair,'REJECTED','HYPOTHETICAL human','different payout rules',now=self.now)
        report = d.refresh_queue(self.db,now=self.now,sports_only=True)
        self.assertEqual(report['candidates'][0]['prior_reviews'][0]['status'], 'REJECTED')
        self.assertEqual(d.queue(self.db,now=self.now+timedelta(days=2),sports_only=True)['candidates'], [])

    def test_non_sports_scope_and_cli_flag(self):
        generic = fixture('discovery-hypothetical')
        for venue in ('kalshi','polymarket_us'):
            registry._record_instrument(self.db,venue,'HYPOTHETICAL-GENERIC-'+venue,generic[venue],
                                        observed_at=self.now.isoformat(),available=True,hypothetical=True,now=self.now)
        self.assertEqual(len(d.discover(self.db,now=self.now)['candidates']), 2)
        self.assertEqual(len(d.discover(self.db,now=self.now,sports_only=True)['candidates']), 1)
        for action in ('refresh','queue'):
            args=['predarb','discovery',action,'--db',self.path,'--sports-only']
            if action=='refresh':args.append('--offline')
            out=StringIO()
            with patch('sys.argv',args),patch('predarb.registry.now_utc',return_value=self.now),redirect_stdout(out):
                self.assertEqual(cli.main(),0)
            result=json.loads(out.getvalue())
            self.assertEqual(result['candidate_scope'],'NBA_NFL_GAME_WINNERS')
            self.assertEqual(len(result['candidates']),1)


if __name__ == '__main__': unittest.main()
