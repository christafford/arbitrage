import unittest
from decimal import Decimal as D
from predarb.models import AskLevel
from predarb.math import evaluate

class MathTests(unittest.TestCase):
    def test_positive(self):
        e = evaluate([AskLevel(D(".42"),D(100))], [AskLevel(D(".53"),D(100))], max_pairs=D(100),fee_per_pair=D(".01"),reserve_per_pair=D(".005"))
        self.assertEqual(e.net_profit,D("3.500"))
        self.assertEqual(e.contracts,D(100))
    def test_depth_stops_at_bad_marginal(self):
        y=[AskLevel(D(".42"),D(10)),AskLevel(D(".50"),D(10))]
        n=[AskLevel(D(".53"),D(20))]
        e=evaluate(y,n,max_pairs=D(20),fee_per_pair=D(".01"))
        self.assertEqual(e.contracts,D(10))
    def test_no_depth(self):
        e=evaluate([],[],max_pairs=D(10),fee_per_pair=D("0"))
        self.assertEqual(e.contracts,D(0))
    def test_reject_unsorted_and_invalid(self):
        with self.assertRaises(ValueError): AskLevel(D("NaN"),D(10))
        with self.assertRaises(ValueError): AskLevel(D(".5"),D(0))
        with self.assertRaises(ValueError): evaluate([AskLevel(D(".6"),D(1)),AskLevel(D(".5"),D(1))], [AskLevel(D(".2"),D(1))],max_pairs=D(1),fee_per_pair=D(0))
        with self.assertRaises(ValueError): evaluate([],[],max_pairs=D(1),fee_per_pair=D("NaN"))
    def test_partial(self):
        e=evaluate([AskLevel(D(".40"),D("1.5"))],[AskLevel(D(".5"),D("20"))],max_pairs=D(2),fee_per_pair=D("0"))
        self.assertEqual(e.contracts,D("1.5"))
