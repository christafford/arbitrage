"""Genuine archived failures plus explicitly hypothetical parsing variations."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from predarb import discovery as d, semantic as s, propositions as p
from predarb.store import connect
from predarb.validation import dumps, utc_time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('genuine_seed', ROOT/'scripts/m5i_evaluate.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
CORPUS = json.loads((ROOT/'tests/fixtures/m5i-contradictions-genuine.json').read_text())
NOW = utc_time(CORPUS['created_at'])


class ParsingTests(unittest.TestCase):
    def test_money_units_magnitudes_and_exact_decimal_boundaries(self):
        # HYPOTHETICAL equivalent wording; no prices or cashflows inferred.
        for text in ('more than 1700 billion dollars','above $1.7 trillion','> $1700000000000','over $1.7t'):
            self.assertEqual(p.thresholds(text), [('>','1700000000000','USD')])
        self.assertEqual(p.thresholds('$19,999.99 or below'), [('<=','19999.99','USD')])
        self.assertEqual(p.thresholds('≥ $19,999.99'), [('>=','19999.99','USD')])
        self.assertEqual(p.thresholds('no more than $0.01'), [('<=','0.01','USD')])

    def test_inclusivity_inverse_and_missing_units_do_not_become_equal(self):
        def f(text):return p.extract({'title':text})
        self.assertIn('PROPOSITION_THRESHOLD_CONFLICT',p.compare(f('above $100'),f('at least $100')))
        self.assertIn('PROPOSITION_DIRECTION_CONFLICT',p.compare(f('above $100'),f('100 or below')))
        self.assertIn('PROPOSITION_THRESHOLD_UNKNOWN',p.compare(f('above $100'),f('above 100')))
        self.assertEqual(f('above 100')['thresholds'],[('>','100','unspecified')])
        self.assertNotIn('PROPOSITION_THRESHOLD_CONFLICT',p.compare(f('above $1 billion'),f('above 1000 million dollars')))
        self.assertNotIn('PROPOSITION_DIRECTION_CONFLICT',p.compare(f('exactly 1 cut'),f('greater than 25 bps')))

    def test_observation_windows_do_not_use_administrative_deadlines(self):
        a=p.extract({'rules_primary':'Price above $10 starting January 1 at 10:00 AM and before December 31 at 11:59 PM.'})
        b=p.extract({'description':'Price above $10 at 12:00 AM ET on January 1.'})
        self.assertIn('OBSERVATION_WINDOW_CONFLICT',p.compare(a,b))
        self.assertIsNone(p.extract({'title':'Price above $10','endDate':'2030-01-01T00:00:00Z'})['observation_window'])

    def test_missing_invalid_and_ambiguous_language_remains_unknown(self):
        self.assertEqual(p.extract({})['thresholds'],[])
        self.assertEqual(p.compare({},{}),['PROPOSITION_EVIDENCE_UNKNOWN'])
        with self.assertRaises(ValueError):p.extract({'title':12})
        with self.assertRaises(ValueError):p.from_public_text(None)
        with self.assertRaisesRegex(ValueError,'schema'):p.from_public_text('{"schema":"unknown","public_contract":{}}')
        self.assertIsNone(p.extract({'title':'How does the Supreme Court decide cases?'})['proposition_type'])
        self.assertIsNone(p.extract({'title':'A championship round with many options'})['rounding'])

    def test_selection_and_assertion_precedence_avoid_example_numbers(self):
        a=p.extract({'question':'Generic wealth question','title':'At least $1.2 trillion',
                     'description':'This resolves Yes if wealth is at least $1.2 trillion. For example, $5 trillion would exceed $4 trillion.'})
        self.assertEqual(a['thresholds'],[('>=','1200000000000','USD')])
        self.assertEqual(p.extract({'question':'Generic wealth question','title':'At least $1.2 trillion'})['thresholds'],a['thresholds'])


class GenuineRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.source=connect(str(Path(self.tmp.name)/'source.sqlite3'))
        self.index=connect(str(Path(self.tmp.name)/'index.sqlite3'))
        self.addCleanup(self.source.close);self.addCleanup(self.index.close)
        evaluation.seed(self.source,CORPUS)  # Hashes and official adapter schemas validated.
        s.sync(self.source,self.index,now=NOW)

    def docs(self,case):
        return [next(s.rows(self.index,'SELECT * FROM semantic_documents WHERE venue=? AND source_id=?',(v,case[v+'_id']))) for v in ('kalshi','polymarket_us')]

    def ranked(self,case):
        # Score of 1 is HYPOTHETICAL stress input, not a live model measurement.
        return s.rank_pair(self.source,self.index,*self.docs(case),{'HYPOTHETICAL_PERFECT_COSINE'},
                           {'cosine':1,'identity':'HYPOTHETICAL'},NOW,s.venue_context(self.source))

    def test_all_four_genuine_misses_flagged_at_perfect_cosine_and_spotify_preserved(self):
        rankings=[]
        for case in CORPUS['cases']:
            with self.subTest(case=case['kalshi_id']):
                result=self.ranked(case);self.assertIsNotNone(result)
                rank,row=result;rankings.append(result)
                self.assertTrue(set(case['expected_conflicts'])<=set(row['known_contradictions']))
                self.assertEqual(bool(row['known_contradictions']),bool(case['expected_conflicts']))
                self.assertEqual(rank[0],bool(case['expected_conflicts']))
                self.assertFalse(row['equivalence_verified']);self.assertFalse(row['trading_authorized'])
        self.assertEqual(sorted(rankings,key=lambda r:r[0])[0][1]['kalshi_id'],'KXTOPSONGSPOTIFY-26-PIN')
        self.assertEqual(self.source.execute('SELECT count(*) FROM pairs').fetchone()[0],0)

    def test_existing_sidecar_features_and_saved_reservoir_are_rechecked_without_resync(self):
        for doc in list(s.rows(self.index,'SELECT * FROM semantic_documents')):
            f=json.loads(doc['features_json']);f.pop('proposition',None)
            self.index.execute('UPDATE semantic_documents SET features_json=? WHERE id=?',(dumps(f),doc['id']))
        before=self.index.execute('SELECT content_hash FROM semantic_documents ORDER BY id').fetchall()
        for case in CORPUS['cases']:
            _,row=self.ranked(case)
            row['known_contradictions']=[];row['warnings']=[];row['equivalence_score_bps']=10000
            self.index.execute('INSERT INTO semantic_candidates VALUES(?,?,?)',(row['kalshi_id'],row['polymarket_us_id'],dumps(row)))
        self.index.commit()
        result=s.retrieve(self.source,self.index,now=NOW,query_ids=[],semantic=False,limit=100)
        for row in result['candidates']:
            case=next(x for x in CORPUS['cases'] if x['kalshi_id']==row['kalshi_id'])
            self.assertTrue(set(case['expected_conflicts'])<=set(row['known_contradictions']))
        self.assertEqual(before,self.index.execute('SELECT content_hash FROM semantic_documents ORDER BY id').fetchall())

    def test_main_queue_rechecks_old_empty_contradictions_at_read_time(self):
        candidates=[]
        for case in CORPUS['cases']:
            _,row=self.ranked(case);row['known_contradictions']=[];row['warnings']=[]
            candidates.append(row)
        report={'algorithm':s.VERSION,'ranked_at':NOW.isoformat(),'candidates':candidates}
        self.source.execute('INSERT INTO discovery_state VALUES(1,?,?)',(NOW.isoformat(),dumps(report)));self.source.commit()
        result=d.queue(self.source,now=NOW,limit=100)
        self.assertEqual(result['candidates'][0]['kalshi_id'],'KXTOPSONGSPOTIFY-26-PIN')
        self.assertEqual(len(result['candidates']),5)
        for row in result['candidates']:
            expected=next(x['expected_conflicts'] for x in CORPUS['cases'] if x['kalshi_id']==row['kalshi_id'])
            self.assertTrue(set(expected)<=set(row['known_contradictions']))
        self.assertEqual(d.queue(self.source,now=NOW+timedelta(days=2))['candidates'],[])

    def test_deterministic_retrieval_also_ranks_clean_proposition_before_conflicts(self):
        pairs=[(c['kalshi_id'],c['polymarket_us_id']) for c in CORPUS['cases']]
        report=d.discover(self.source,now=NOW,limit=100,_pair_keys=pairs)
        self.assertEqual(report['candidates'][0]['kalshi_id'],'KXTOPSONGSPOTIFY-26-PIN')
        for row in report['candidates']:
            expected=next(x['expected_conflicts'] for x in CORPUS['cases'] if x['kalshi_id']==row['kalshi_id'])
            self.assertTrue(set(expected)<=set(row['known_contradictions']))

    def test_changed_and_stale_genuine_definitions_remain_ineligible(self):
        a,b=self.docs(CORPUS['cases'][0]);a['version_id']=-1
        self.assertIsNone(s.rank_pair(self.source,self.index,a,b,set(),None,NOW,s.venue_context(self.source)))
        a,b=self.docs(CORPUS['cases'][0])
        self.assertIsNone(s.rank_pair(self.source,self.index,a,b,set(),None,NOW+timedelta(days=2),s.venue_context(self.source)))


class KeywordFacetTests(unittest.TestCase):
    """Explicitly hypothetical language variations; no legal equivalence labels."""
    def pair(self,a,b):return p.compare(p.extract({'description':a}),p.extract({'description':b}))

    def test_political_offices_require_explicit_scope(self):
        self.assertIn('POLITICAL_OFFICE_CONFLICT',self.pair('Democrats win the State Senate.','Democrats win the US Senator election.'))
        self.assertNotIn('POLITICAL_OFFICE_CONFLICT',self.pair('Democrats win the U.S. Senate.','Democrats win the United States Senate.'))
        self.assertEqual(p.extract({'description':'Democrats win the U.S. Senate.'})['political_office'],'US_SENATE')
        self.assertIsNone(p.extract({'description':'Democrats win the State Senate or the US Senate.'})['political_office'])
        self.assertIn('POLITICAL_OFFICE_UNKNOWN',self.pair('Democrats win the Senate.','Democrats win the State Senate.'))
        self.assertIsNone(p.extract({'description':'Democrats win the Senate. Examples include the State Senate.'})['political_office'])

    def test_ceo_company_action_and_ambiguity(self):
        warnings=self.pair('Elon Musk is confirmed as CEO for X.','Elon Musk departure as CEO of Tesla is announced.')
        self.assertIn('CEO_COMPANY_CONFLICT',warnings);self.assertIn('CEO_ACTION_CONFLICT',warnings)
        self.assertNotIn('CEO_COMPANY_CONFLICT',self.pair('Musk becomes CEO of Twitter.','Musk is appointed CEO at X.'))
        self.assertIsNone(p.extract({'description':'Musk is not appointed CEO of X.'})['ceo_action'])
        self.assertIsNone(p.extract({'description':'Musk becomes CEO of an unspecified company.'})['ceo_company'])
        self.assertIsNone(p.extract({'description':'Musk becomes CEO of X or CEO of Tesla.'})['ceo_company'])
        self.assertIsNone(p.extract({'description':'Musk is appointed then departs as CEO of X.'})['ceo_action'])

    def test_rank_is_not_chart_size_or_an_example(self):
        self.assertIn('RANKING_POSITION_CONFLICT',self.pair('Song A is #2 on Spotify.','Song A is the top song on Spotify.'))
        for wording in ('#1 most streamed song','number 1 song','first-ranked song'):
            self.assertEqual(p.extract({'description':f'Spotify: {wording}.'})['ranking_position'],'1')
        self.assertIsNone(p.extract({'description':'Song A appears in Spotify Top 10 Songs.'})['ranking_position'])
        self.assertIsNone(p.extract({'description':'Spotify song is #1 or #2.'})['ranking_position'])
        self.assertEqual(p.extract({'description':'Song A is #2 on Spotify. An example is the #1 song.'})['ranking_position'],'2')

    def test_fed_direction_is_independent_of_missing_numeric_operator(self):
        self.assertIn('RATE_DIRECTION_CONFLICT',self.pair('The Federal Reserve does a Hike of 25bps.','The Federal Reserve does not change rates.'))
        self.assertIn('RATE_DIRECTION_CONFLICT',self.pair('The Fed cuts rates.','The Fed hikes rates.'))
        for text in ('Fed does not hike rates.','Fed cuts or hikes rates.','Fed rate decision.'):
            self.assertIsNone(p.extract({'description':text})['rate_direction'])
        self.assertEqual(p.extract({'rules_primary':'The Fed hikes rates.','rules_secondary':'If canceled, no change resolves Yes.'})['rate_direction'],'HIKE')


class GenuineKeywordRegressionTests(unittest.TestCase):
    def setUp(self):
        self.corpus=json.loads((ROOT/'tests/fixtures/m5i-keyword-mismatches-genuine.json').read_text())
        self.now=utc_time(self.corpus['created_at'])
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.source=connect(str(Path(self.tmp.name)/'source.sqlite3'));self.index=connect(str(Path(self.tmp.name)/'index.sqlite3'))
        self.addCleanup(self.source.close);self.addCleanup(self.index.close)
        evaluation.seed(self.source,self.corpus);s.sync(self.source,self.index,now=self.now)

    def rank(self,case,cosine=True):
        docs=[next(s.rows(self.index,'SELECT * FROM semantic_documents WHERE venue=? AND source_id=?',(v,case[v+'_id']))) for v in ('kalshi','polymarket_us')]
        return s.rank_pair(self.source,self.index,*docs,{'HYPOTHETICAL_TEST'},
                          {'cosine':1,'identity':'HYPOTHETICAL'} if cosine else None,self.now,s.venue_context(self.source))

    def test_genuine_misses_at_perfect_similarity_and_positive_controls(self):
        for cosine in (True,False):
            for case in self.corpus['cases']:
                with self.subTest(case=case['kalshi_id'],cosine=cosine):
                    rank,row=self.rank(case,cosine)
                    self.assertTrue(set(case['expected_conflicts'])<=set(row['known_contradictions']))
                    self.assertEqual(bool(rank[0]),bool(case['expected_conflicts']))
                    self.assertFalse(row['equivalence_verified']);self.assertFalse(row['trading_authorized'])
        self.assertEqual(self.source.execute('SELECT count(*) FROM pairs').fetchone()[0],0)

    def test_old_features_main_queue_and_reservoir_recompute_without_reembedding(self):
        before=self.index.execute('SELECT content_hash FROM semantic_documents ORDER BY id').fetchall()
        candidates=[]
        for case in self.corpus['cases']:
            _,row=self.rank(case);row['known_contradictions']=[];row['warnings']=[]
            candidates.append(row)
            self.index.execute('INSERT INTO semantic_candidates VALUES(?,?,?)',(row['kalshi_id'],row['polymarket_us_id'],dumps(row)))
        for doc in list(s.rows(self.index,'SELECT * FROM semantic_documents')):
            f=json.loads(doc['features_json']);f['proposition']={'version':'proposition-guards/m5i-v1'}
            self.index.execute('UPDATE semantic_documents SET features_json=? WHERE id=?',(dumps(f),doc['id']))
        self.index.commit()
        result=s.retrieve(self.source,self.index,now=self.now,query_ids=[],semantic=False,limit=100)
        self.assertFalse(result['candidates'][0]['known_contradictions'])
        from predarb.semantic_cli import revalidate_candidates
        main=revalidate_candidates(self.source,candidates,now=self.now)
        for row in main:
            case=next(c for c in self.corpus['cases'] if c['kalshi_id']==row['kalshi_id'])
            self.assertTrue(set(case['expected_conflicts'])<=set(row['known_contradictions']))
        self.assertEqual(revalidate_candidates(self.source,candidates,now=self.now+timedelta(days=2)),[])
        self.assertEqual(before,self.index.execute('SELECT content_hash FROM semantic_documents ORDER BY id').fetchall())

    def test_deterministic_production_path_demotes_all_four_pairs(self):
        pairs=[(c['kalshi_id'],c['polymarket_us_id']) for c in self.corpus['cases']]
        report=d.discover(self.source,now=self.now,limit=100,_pair_keys=pairs)
        for row in report['candidates']:
            case=next(c for c in self.corpus['cases'] if c['kalshi_id']==row['kalshi_id'])
            self.assertTrue(set(case['expected_conflicts'])<=set(row['known_contradictions']))
        self.assertFalse(report['candidates'][0]['known_contradictions'])
