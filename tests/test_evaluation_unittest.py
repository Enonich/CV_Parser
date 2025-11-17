import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.core.evaluation import precision_at_k, reciprocal_rank, spearman_rank_corr, compute_lift_stats

class TestEvaluationMetrics(unittest.TestCase):
    def test_precision_at_k(self):
        labels = {"a": True, "b": False, "c": True}
        ranked = ["a", "b", "c", "d"]
        self.assertEqual(precision_at_k(labels, ranked, 1), 1.0)
        self.assertAlmostEqual(precision_at_k(labels, ranked, 3), 2/3, places=4)

    def test_reciprocal_rank(self):
        labels = {"x": False, "y": True}
        ranked = ["x", "z", "y"]
        self.assertEqual(reciprocal_rank(labels, ranked), 1/3)

    def test_spearman_rank_corr(self):
        a = [10, 9, 8, 7, 6]
        b = [10, 9, 8, 6, 7]  # small swap
        rho = spearman_rank_corr(a, b)
        # Expect positive but less than perfect due to swap; analytical value should be around 0.9 or lower
        self.assertTrue(0.5 < rho < 1.0)

    def test_compute_lift_stats(self):
        feats = [
            {'cv_id': 'a', 'combined_score_pre_impact': 1.0, 'combined_score': 1.1},
            {'cv_id': 'b', 'combined_score_pre_impact': 2.0, 'combined_score': 2.0},
            {'cv_id': 'c', 'combined_score_pre_impact': 3.0, 'combined_score': 2.9},
        ]
        stats = compute_lift_stats(feats)
        self.assertEqual(stats['improved'], 1)
        self.assertEqual(stats['unchanged'], 1)
        self.assertEqual(stats['worsened'], 1)
        self.assertAlmostEqual(stats['avg_delta'], (0.1 + 0.0 - 0.1)/3, places=6)

if __name__ == '__main__':
    unittest.main()
