import os
import sys
import unittest
import math

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.core.semantic_skill_matcher import load_skill_semantic_cache, semantic_matches

# Fake embedding function: maps text to a deterministic vector so we can test cosine similarity logic.
# Strategy: each character contributes to a position; simplistic but stable.

def fake_embed(text: str):
    base = [0.0] * 16
    for ch in text.lower():
        idx = (ord(ch) % 16)
        base[idx] += 1.0
    # Normalize magnitude roughly
    mag = math.sqrt(sum(v*v for v in base)) or 1.0
    return [v / mag for v in base]

TAXONOMY = {
    'skills': {
        'python': {'aliases': ['python3', 'py']},
        'kubernetes': {'aliases': ['k8s']},
        'aws': {'aliases': ['amazon web services']}
    }
}

MANDATORY = ['python', 'kubernetes', 'aws']

class TestSemanticSkillMatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = load_skill_semantic_cache(TAXONOMY, fake_embed)

    def test_direct_match(self):
        sent = "Built a Python data pipeline"
        matches = semantic_matches(sent, MANDATORY, self.cache, fake_embed)
        self.assertIn('python', matches['direct'])
        self.assertEqual(matches['semantic'], [])

    def test_alias_match(self):
        sent = "Migrated services to k8s clusters"
        matches = semantic_matches(sent, MANDATORY, self.cache, fake_embed)
        self.assertIn('kubernetes', matches['alias'])
        self.assertEqual(matches['semantic'], [])

    def test_semantic_fallback(self):
        # Sentence doesn't contain literal 'aws' or alias 'amazon web services'
        # but contains a paraphrase 'amazon cloud'
        sent = "Deployed infrastructure on amazon cloud"
        matches = semantic_matches(sent, MANDATORY, self.cache, fake_embed, threshold=0.70)
        # With our fake embed, 'amazon cloud' should be semantically close to 'amazon web services'
        self.assertIn('aws', matches['semantic'])
        self.assertEqual(matches['direct'], [])
        self.assertEqual(matches['alias'], [])

    def test_short_sentence_skips_semantic(self):
        sent = "aws"
        matches = semantic_matches(sent, MANDATORY, self.cache, fake_embed)
        self.assertEqual(matches['all'], [])

    def test_no_duplicates(self):
        sent = "python python3 py"
        matches = semantic_matches(sent, MANDATORY, self.cache, fake_embed)
        self.assertEqual(matches['all'], ['python'])

if __name__ == '__main__':
    unittest.main()
