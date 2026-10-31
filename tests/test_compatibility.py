"""Genuine archived compatibility evaluation and hypothetical parser edge cases."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from contextlib import closing
import sys
import tempfile
import unittest

from predarb import propositions as p, semantic as s, discovery as d
from predarb.backups import readonly
from predarb.validation import utc_time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    spec=importlib.util.spec_from_file_location('compatibility_eval',ROOT/'scripts/m5i_compatibility_evaluate.py')
    evaluation=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluation)
finally:sys.path.pop(0)


class CompatibilityParsingTests(unittest.TestCase):
    """All strings in this class are HYPOTHETICAL language tests."""
    def pair(self,a,b):return p.compare(p.extract({'description':a}),p.extract({'description':b}))

    def test_ranges_preserve_units_precision_and_unknown_inclusion(self):
        a=p.extract({'rules_primary':'GDP growth is between 0.1% to 0.5%.','rules_secondary':'All stated bounds are inclusive.'})
        self.assertEqual(a['interval'],dict(lower='0.1',upper='0.5',unit='%',inclusive=True))
        self.assertIn('PROPOSITION_RANGE_CONFLICT',p.compare(a,p.extract({'description':'GDP growth is above 2.2%.'})))
        self.assertIn('PROPOSITION_RANGE_CONFLICT',self.pair('GDP growth is between 2.1% and 2.5%.','GDP growth is above 2.2%.'))
        self.assertIsNone(p.extract({'description':'GDP growth is between 0.1% and 0.5%.'})['interval']['inclusive'])
        self.assertNotIn('PROPOSITION_RANGE_CONFLICT',p.compare(a,p.extract({'description':'GDP growth is between 0.1 percent and 0.5 percent.'})))
        for text in ('between 1 and 2','between $2 and $1','between 1 and 2 million dollars',
                     'between $1 and 2%','between 1% and 2% or between 3% and 4%'):
            self.assertIsNone(p.extract({'description':text})['interval'])
        self.assertEqual(p.extract({'description':'Price between $0.001 and $0.009.'})['interval']['upper'],'0.009')

    def test_context_uses_assertions_and_does_not_guess_geography(self):
        self.assertIn('GEOGRAPHY_CONFLICT',self.pair('Average gas prices for California are lower than $4.','The US national average price of gas is less than $4.'))
        self.assertNotIn('GEOGRAPHY_CONFLICT',self.pair('The national average regular gas price for the US is below $4.','The US national average price of gas is below $4.'))
        self.assertIsNone(p.extract({'description':'Gas prices fall. For California they are below $4.'})['geography'])
        self.assertIsNone(p.extract({'description':'Gas prices for California or the US national average are below $4.'})['geography'])
        self.assertIn('GEOGRAPHY_UNKNOWN',self.pair('Gas prices are below $4.','Gas prices for California are below $4.'))
        self.assertIn('GEOGRAPHY_CONFLICT',self.pair('Song A is the top song globally on Spotify.','Song A is the top song in the US on Spotify.'))

    def test_event_kind_and_departure_subject_are_separate(self):
        self.assertIn('EVENT_KIND_CONFLICT',self.pair('Album A is the most streamed album on Spotify.','Album A wins Album of the Year at the Grammy Awards.'))
        a='If Alice Example leaves as President of Peru before July 1, 2030, then Yes.'
        b='This market will settle to Yes if Bob Example formally ceases to hold the position of President of Ukraine by July 1, 2030.'
        warnings=self.pair(a,b)
        self.assertIn('NAMED_SUBJECT_CONFLICT',warnings);self.assertIn('OFFICE_COUNTRY_CONFLICT',warnings)
        self.assertIsNone(p.extract({'description':a.replace('Alice Example','Alice Example or Bob Example')})['named_subject'])
        self.assertIsNone(p.extract({'description':a.replace('Alice Example','the incumbent')})['named_subject'])
        self.assertIsNone(p.extract({'description':'Will Alice Example leave office? Examples mention the President of Peru.'})['office_country'])
        self.assertNotIn('NAMED_SUBJECT_CONFLICT',self.pair(a,a))

    def test_same_person_announcement_rule_remains_conflict(self):
        a='If Alice Example has either officially announced their intention to leave as President of Peru or has actually left President of Peru before January 1, 2030, then Yes.'
        b='This market will settle to Yes if Alice Example formally ceases to hold the position of President of Peru by January 1, 2030.'
        warnings=self.pair(a,b)
        self.assertIn('DEPARTURE_BASIS_CONFLICT',warnings)
        self.assertNotIn('NAMED_SUBJECT_CONFLICT',warnings)


class EvaluationMetricsTests(unittest.TestCase):
    """HYPOTHETICAL labels validate accounting, not market quality."""
    def test_unlabeled_pairs_not_counted_as_false_positives_and_k_is_real(self):
        labels=[dict(kalshi_id='yes',polymarket_us_id='q',retrieval_relevant=True,proposition_conflict_expected=False,category='known'),
                dict(kalshi_id='no',polymarket_us_id='q',retrieval_relevant=False,proposition_conflict_expected=True,category='wrong')]
        rows=[dict(kalshi_id=str(i),polymarket_us_id='q',known_contradictions=[]) for i in range(19)]
        rows += [dict(kalshi_id='no',polymarket_us_id='q',known_contradictions=['CONFLICT']),dict(kalshi_id='yes',polymarket_us_id='q',known_contradictions=[])]
        metrics=evaluation.metrics(labels,{'q':rows})
        self.assertEqual(metrics['20']['recall'],0);self.assertEqual(metrics['100']['recall'],1)
        self.assertEqual(metrics['20']['raw']['unlabeled'],19)
        self.assertEqual(metrics['100']['raw']['false_positive'],1)
        self.assertEqual(metrics['100']['unflagged']['precision_labeled'],1)
        self.assertIsNone(evaluation.metrics(labels,{})['20']['raw']['precision_labeled'])

    def test_invalid_labels_and_duplicate_pairs_are_rejected(self):
        corpus=json.loads(evaluation.FIXTURE.read_text())
        for change in ('duplicate','unknown','missing','hypothetical'):
            c=deepcopy(corpus)
            if change=='duplicate':c['cases'].append(c['cases'][0])
            if change=='unknown':c['cases'][0]['retrieval_relevant']=None
            if change=='missing':c['instruments']=[]
            if change=='hypothetical':c['hypothetical']=True
            with self.subTest(change=change),self.assertRaises(ValueError):evaluation.validate(c)

    def test_guard_context_restores_modules_after_failure(self):
        original=d.propositions,s.propositions
        with self.assertRaises(RuntimeError):
            with evaluation.guards(object()):raise RuntimeError('HYPOTHETICAL failure')
        self.assertEqual((d.propositions,s.propositions),original)


class GenuineCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.report=evaluation.run(json.loads(evaluation.FIXTURE.read_text()),Path(cls.temp.name)/'evaluation')

    def test_genuine_controls_and_conflicts_against_frozen_baseline(self):
        before=self.report['variants']['indexed_v2'];after=self.report['variants']['indexed_v3']
        self.assertGreater(before['non_sports_guard_confusion'].get('false_negative',0),0)
        self.assertEqual(after['non_sports_guard_confusion'].get('false_negative',0),0)
        self.assertEqual(after['non_sports_guard_confusion'].get('false_positive',0),0)
        self.assertEqual(self.report['registry_approvals'],0)
        self.assertEqual(self.report['new_inference_requests'],0)

    def test_diversity_keeps_relevant_zero_score_pairs_with_warnings_intact(self):
        result=self.report['variants']['indexed_v3']['retrieved']
        for query,wanted in [('aaagaspc-usgas-low-2026-12-31-lt3pt20','KXAAAGASMIN-26DEC31-3.20')]:
            row=next(c for c in result[query] if c['kalshi_id']==wanted)
            self.assertTrue(row['known_contradictions'])
            self.assertFalse(row['equivalence_verified']);self.assertFalse(row['trading_authorized'])
        metrics=self.report['variants']['indexed_v3']['retrieval']['20']
        self.assertEqual(metrics['found'],18)
        self.assertEqual(len(metrics['missed_pairs']),1)
        self.assertEqual(metrics['missed_pairs'][0]['miss_stage'],'SETTLEMENT_HORIZON_FILTER')

    def test_stale_corpus_is_not_silently_counted_as_retrieval_failure(self):
        corpus=json.loads(evaluation.FIXTURE.read_text());corpus['created_at']='2030-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'ineligible evaluation definitions'):
            evaluation.run(corpus,Path(self.temp.name)/'stale')

    def test_new_conflicts_survive_hypothetical_perfect_cosine(self):
        with closing(readonly(str(Path(self.temp.name)/'evaluation/source.sqlite3'))) as source, closing(readonly(str(Path(self.temp.name)/'evaluation/index.sqlite3'))) as index:
            corpus=json.loads(evaluation.FIXTURE.read_text());now=utc_time(corpus['created_at'])
            for c in corpus['cases']:
                if c['category'] not in ('range','geography','named_subject','event_kind'):continue
                docs=[next(s.rows(index,'SELECT * FROM semantic_documents WHERE venue=? AND source_id=?',(v,c[v+'_id']))) for v in ('kalshi','polymarket_us')]
                rank,row=s.rank_pair(source,index,*docs,{'HYPOTHETICAL_TEST'},
                    {'identity':'HYPOTHETICAL','cosine':1},now,s.venue_context(source))
                self.assertTrue(rank[0]);self.assertTrue(row['known_contradictions'])
                self.assertFalse(row['equivalence_verified']);self.assertFalse(row['trading_authorized'])

    def test_corrupt_genuine_excerpt_fails_closed(self):
        corpus=json.loads(evaluation.FIXTURE.read_text());corpus['instruments'][0]['body_sha256']='incorrect'
        with self.assertRaisesRegex(ValueError,'excerpt hash mismatch'):
            evaluation.run(corpus,Path(self.temp.name)/'corrupt')
