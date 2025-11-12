import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.core.scoring_utils import apply_skill_and_impact_adjustments

class TestImpactWeighting(unittest.TestCase):
    def setUp(self):
        self.config = {
            'search': {
                'impact_weight': 0.08,
                'mandatory_strength_factor': 0.15,
                'impact_min_relevance': 0.0,
            }
        }
        self.mandatory_skills = ['python', 'spark', 'kubernetes']

    def test_full_application_with_relevance(self):
        # Base retrieval score
        res = {
            'combined_score': 1.2,
            'skill_mandatory_coverage': 0.6,
            'skill_optional_coverage': 0.4,
            'impact_score': 0.8,  # calibrated
            'impact_raw_score': 5.0,
            'impact_event_count': 3,
            'impact_events': [
                {'sentence': 'Increased pipeline throughput using Python'},
                {'sentence': 'Optimized Spark jobs reducing cost'},
                {'sentence': 'Launched infra consolidation on Kubernetes'}
            ]
        }
        adjusted = apply_skill_and_impact_adjustments(res, self.mandatory_skills, self.config, show_details=True)
        # Skill bonus
        expected_skill_bonus = 0.6 * 0.10 + 0.4 * 0.05  # 0.06 + 0.02 = 0.08
        base_plus_bonus = 1.2 + expected_skill_bonus  # 1.28
        boosted_base = base_plus_bonus * (1 + 0.6 * 0.15)  # 1 + 0.09 = 1.09 -> 1.28 * 1.09 = 1.3952
        # Relevance ratio: all 3 events contain mandatory skills => 1.0
        raw_component = 0.08 * 0.8  # 0.064
        final_component = raw_component * 1.0  # relevance scaling
        expected_final = boosted_base + final_component  # 1.3952 + 0.064 = 1.4592
        self.assertAlmostEqual(adjusted['combined_score_pre_impact'], boosted_base, places=4)
        self.assertAlmostEqual(adjusted['score_components']['impact_component_raw'], raw_component, places=4)
        self.assertAlmostEqual(adjusted['score_components']['impact_component_final'], final_component, places=4)
        self.assertAlmostEqual(adjusted['combined_score'], expected_final, places=4)

    def test_no_impact_due_to_event_threshold(self):
        res = {
            'combined_score': 1.0,
            'skill_mandatory_coverage': 0.5,
            'skill_optional_coverage': 0.3,
            'impact_score': 0.9,
            'impact_raw_score': 4.0,
            'impact_event_count': 1,  # less than threshold => no impact weight
            'impact_events': [
                {'sentence': 'Improved latency 40% with Python'}
            ]
        }
        adjusted = apply_skill_and_impact_adjustments(res, self.mandatory_skills, self.config, show_details=True)
        self.assertEqual(adjusted['score_components']['impact_component_raw'], 0.0)
        self.assertEqual(adjusted['score_components']['impact_component_final'], 0.0)
        # Ensure final score only reflects skill bonus + mandatory strength
        skill_bonus = 0.5 * 0.10 + 0.3 * 0.05  # 0.05 + 0.015 = 0.065
        base_plus_bonus = 1.0 + skill_bonus  # 1.065
        boosted_base = base_plus_bonus * (1 + 0.5 * 0.15)  # factor 1 + 0.075 = 1.075 -> 1.065 * 1.075 = 1.146375
        self.assertAlmostEqual(adjusted['combined_score'], boosted_base, places=4)

    def test_relevance_min_threshold_blocks_component(self):
        config = {
            'search': {
                'impact_weight': 0.08,
                'mandatory_strength_factor': 0.15,
                'impact_min_relevance': 0.5,  # require at least half events relevant
            }
        }
        res = {
            'combined_score': 1.0,
            'skill_mandatory_coverage': 0.5,
            'skill_optional_coverage': 0.3,
            'impact_score': 0.7,
            'impact_raw_score': 3.0,
            'impact_event_count': 3,
            'impact_events': [
                {'sentence': 'Increased brand awareness 200%'},  # no mandatory skill
                {'sentence': 'Optimized Spark pipeline'},        # relevant
                {'sentence': 'Reduced cost via Python tooling'}  # relevant
            ]
        }
        adjusted = apply_skill_and_impact_adjustments(res, self.mandatory_skills, config, show_details=True)
        # relevance ratio = 2/3 ~ 0.666 > 0.5 -> component applies scaled by ratio
        raw_component = 0.08 * 0.7  # 0.056
        final_component = raw_component * (2/3)
        self.assertAlmostEqual(adjusted['score_components']['impact_component_final'], final_component, places=4)

        # Now raise threshold to block
        config_block = {
            'search': {
                'impact_weight': 0.08,
                'mandatory_strength_factor': 0.15,
                'impact_min_relevance': 0.8,  # higher than ratio
            }
        }
        res_block = res.copy()
        adjusted_block = apply_skill_and_impact_adjustments(res_block, self.mandatory_skills, config_block, show_details=True)
        self.assertEqual(adjusted_block['score_components']['impact_component_final'], 0.0)

if __name__ == '__main__':
    unittest.main()
