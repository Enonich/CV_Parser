import os
import sys
import unittest

# Ensure project root (containing 'backend') is on sys.path for direct test invocation / pytest discovery
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.extractors.impact_extraction import extract_impact_features, _extract_metrics, _detect_verbs, _score_event

class TestImpactExtraction(unittest.TestCase):
    def setUp(self):
        self.sample_cv = {
            "work_experience": [
                {"responsibilities": [
                    "Reduced infrastructure costs by 35% resulting in annual savings of $250K",
                    "Implemented automation saving 120 hours per month",
                    "Increased data throughput 60% leading to 20% faster analytics",
                    "Collaborated with team"
                ]}
            ],
            "projects": [
                {"description": "Optimized query engine cutting latency 45% and saving $30K annually"}
            ],
            "achievements": [
                "Spearheaded launch generating $2M new ARR",
            ]
        }

    def test_detect_verbs_basic(self):
        sentence = "Reduced infrastructure costs by 35% resulting in annual savings of $250K"
        verbs = _detect_verbs(sentence)
        self.assertIn("reduced", verbs)
        self.assertNotIn("savings", verbs)

    def test_extract_metrics_percent_and_currency(self):
        sentence = "Reduced infrastructure costs by 35% resulting in annual savings of $250K"
        metrics = _extract_metrics(sentence)
        raw_vals = {m['raw'] for m in metrics}
        # Accept either '35%' or '35' depending on raw formatting
        self.assertTrue(any(rv.startswith('35') for rv in raw_vals))
        currency_metric = next(m for m in metrics if '250k' in m['raw'].lower())
        self.assertEqual(currency_metric['value'], 250000)

    def test_extract_metrics_counts(self):
        sentence = "Implemented automation saving 120 hours per month"
        metrics = _extract_metrics(sentence)
        count_metric = next((m for m in metrics if m['type'] == 'count'), None)
        self.assertIsNotNone(count_metric)
        self.assertEqual(count_metric['value'], 120)

    def test_score_event_components(self):
        sentence = "Reduced infrastructure costs by 35% resulting in annual savings of $250K"
        verbs = _detect_verbs(sentence)
        metrics = _extract_metrics(sentence)
        outcome_phrase = "annual savings of $250K"
        score, components = _score_event(verbs, metrics, outcome_phrase)
        self.assertGreater(score, 0)
        self.assertGreaterEqual(components['verb_weight'], 1.0)
        self.assertGreater(components['metric_magnitude'], 0)
        self.assertGreater(components['outcome_bonus'], 1.0)

    def test_extract_impact_features_aggregation(self):
        features = extract_impact_features(self.sample_cv)
        self.assertGreaterEqual(features['impact_event_count'], 4)
        self.assertGreater(features['raw_impact_score'], 0)
        scores = [e['event_score'] for e in features['impact_events']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_extract_impact_features_top_n_limit(self):
        cv = {
            "work_experience": [
                {"responsibilities": [
                    f"Reduced cost by {i}% saving ${i}K" for i in range(10, 25)
                ]}
            ]
        }
        features = extract_impact_features(cv)
        self.assertGreaterEqual(features['impact_event_count'], 10)
        self.assertEqual(len(features['impact_events']), 8)

    def test_no_false_positive_without_metrics(self):
        cv = {"work_experience": [{"responsibilities": ["Led team initiatives", "Collaborated across departments"]}]}
        features = extract_impact_features(cv)
        self.assertEqual(features['impact_event_count'], 0)
        self.assertEqual(features['raw_impact_score'], 0)

    def test_direction_detection_increase_decrease(self):
        features = extract_impact_features(self.sample_cv)
        dirs = {e['direction'] for e in features['impact_events']}
        self.assertTrue(any(d in {'increase', 'decrease'} for d in dirs))

    def test_event_score_monotonic_with_metric_growth(self):
        base_sentence = "Reduced cost by 10%"
        bigger_sentence = "Reduced cost by 50%"
        verbs_base = _detect_verbs(base_sentence)
        metrics_base = _extract_metrics(base_sentence)
        score_base, _ = _score_event(verbs_base, metrics_base, None)
        verbs_big = _detect_verbs(bigger_sentence)
        metrics_big = _extract_metrics(bigger_sentence)
        score_big, _ = _score_event(verbs_big, metrics_big, None)
        self.assertGreater(score_big, score_base)

if __name__ == '__main__':
    unittest.main()
