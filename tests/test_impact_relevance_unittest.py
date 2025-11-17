import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.core.impact_relevance import compute_impact_relevance

class TestImpactRelevance(unittest.TestCase):
    def test_basic_ratio_and_distinct_skills(self):
        impact_events = [
            {"sentence": "Increased data throughput 50% using Python and Spark pipelines"},
            {"sentence": "Reduced infrastructure cost 30% by consolidating Kubernetes clusters"},
            {"sentence": "Launched marketing campaign raising brand awareness 200%"}
        ]
        mandatory_skills = ["python", "spark", "kubernetes"]
        ratio, skills = compute_impact_relevance(impact_events, mandatory_skills)
        self.assertAlmostEqual(ratio, 2/3, places=4)
        self.assertEqual(set(skills), {"python", "spark", "kubernetes"})

    def test_no_events(self):
        ratio, skills = compute_impact_relevance([], ["python"])
        self.assertEqual(ratio, 0.0)
        self.assertEqual(skills, [])

    def test_no_mandatory_skills(self):
        impact_events = [{"sentence": "Improved latency 40% via caching"}]
        ratio, skills = compute_impact_relevance(impact_events, [])
        self.assertEqual(ratio, 0.0)
        self.assertEqual(skills, [])

    def test_all_events_relevant(self):
        impact_events = [
            {"sentence": "Optimized Python ETL reducing cost"},
            {"sentence": "Automated Spark jobs"}
        ]
        mandatory_skills = ["python", "spark"]
        ratio, skills = compute_impact_relevance(impact_events, mandatory_skills)
        self.assertEqual(ratio, 1.0)
        self.assertEqual(set(skills), {"python", "spark"})

if __name__ == '__main__':
    unittest.main()
