import math
import unittest
from scripts.haruq_formation import (expand,block,generate_candidates,
    hypothesis_probabilities,metrics,automatic_formation)


class ManualExamples(unittest.TestCase):
    def test_counts_and_position(self):
        all9 = list(range(1,10))
        for fields,n in [(([1],[2,4,5,9],[2,4,5,9]),12),
                         (([1,7],[1,7],[2,3,5,9]),8),
                         (([5,7],[5,7],all9),14),
                         (([5],all9,[1]),7),
                         (([3,5],[7],[1,2,3,5]),6),
                         (([2,3,9],[2,3,9],[1,2,3,9]),12)]:
            self.assertEqual(len(expand(*fields,all9)),n)
        t=expand([1,2],[1,2],[3,4,5],all9)
        self.assertNotIn((6,1,2),t)
        self.assertNotIn((1,1,3),t)

    def test_union_and_cost(self):
        box = set(expand([1,3,5,7],[1,3,5,7],[1,3,5,7],range(1,10)))
        sandwich = set(expand([5],range(1,10),[1],range(1,10)))
        self.assertEqual(len(box|sandwich),29)
        self.assertEqual(len(box&sandwich),2)

    def test_missing_bike(self):
        with self.assertRaises(ValueError):
            expand([1],[2],[9],range(1,8))


class AutomaticSelection(unittest.TestCase):
    def setUp(self):
        self.ranked=[{'bike':b,'score':float(7-i)} for i,b in enumerate([1,4,2,5,3,6,7])]
        self.lines=[[1,2,3],[4,5],[6,7]]

    def test_probability_contract(self):
        p=hypothesis_probabilities(self.ranked)
        self.assertEqual(len(p),210)
        self.assertAlmostEqual(sum(p.values()),1)
        extreme=[dict(r,score=1000. if i==0 else -1000.) for i,r in enumerate(self.ranked)]
        self.assertTrue(all(math.isfinite(x) for x in hypothesis_probabilities(extreme).values()))

    def test_automatic_shapes_and_no_purchase(self):
        cs=generate_candidates(self.ranked,self.lines)
        self.assertTrue({'first_fixed','second_fixed','third_fixed','sandwich',
            'pair_reverse','ordered_pair','multiple_winners','pair_plus_sandwich'} <= {c['family'] for c in cs})
        result=automatic_formation(self.ranked,self.lines,eligible=True)
        self.assertIsNotNone(result['selected'])
        self.assertFalse(result['counts_as_purchase'])
        self.assertEqual(result['decision'],'見送り')
        self.assertEqual(result,automatic_formation(self.ranked,self.lines,eligible=True))
        for c in cs:
            self.assertEqual(len(set(c['tickets'])),c['points'])
            self.assertLessEqual(c['points'],24)
            self.assertTrue(all(len(set(t))==3 for t in c['tickets']))

    def test_ineligible_and_missing_inputs(self):
        self.assertIsNone(automatic_formation(self.ranked,self.lines,eligible=False)['selected'])
        self.assertIsNone(automatic_formation(self.ranked,[],eligible=True)['selected'])
        with self.assertRaises(ValueError):
            generate_candidates(self.ranked,[[1,2],[3,4],[5,6]])
        result=automatic_formation(self.ranked,self.lines,eligible=True,odds={(1,2,3):10})
        self.assertIsNone(result['selected'])

    def test_set_ev_allows_negative_components(self):
        a,b=(1,2,3),(1,3,2)
        m=metrics([a,b],{a:.05,b:.01},{a:60,b:10})
        self.assertAlmostEqual(m['expected_return_ratio_hypothesis'],1.55)
        self.assertEqual(m['total_yen'],200)
        # b has individual EV=0.1; it remains in the selected shape.
        self.assertAlmostEqual(m['expected_net_yen_hypothesis'],110)

    def test_priced_whole_shape(self):
        p=hypothesis_probabilities(self.ranked)
        odds={t:10000. for t in p}
        r=automatic_formation(self.ranked,self.lines,eligible=True,odds=odds)
        self.assertIsNotNone(r['selected'])
        self.assertGreaterEqual(r['selected']['metrics']['composite_odds'],3)
        self.assertFalse(r['counts_as_purchase'])
