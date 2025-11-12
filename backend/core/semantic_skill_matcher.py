"""Semantic Skill Matcher

Provides hybrid matching of mandatory skills within impact event sentences:
  1. Direct canonical skill word-boundary match.
  2. Alias match from taxonomy.
  3. Semantic embedding fallback (optional) when no direct/alias hit.

The semantic layer is deliberately conservative: it only fires if a sentence has
no direct/alias matches and the cosine similarity between the sentence embedding
and a skill (or its aliases) exceeds a threshold.

Embeddings are cached per skill+alias to avoid recomputation.
This module is model-agnostic; pass any embedding function with signature
  embed(text: str) -> List[float]

Public API:
  load_skill_semantic_cache(taxonomy: dict, embed_fn) -> SemanticSkillCache
  semantic_matches(sentence: str, mandatory_skills: list[str], cache: SemanticSkillCache, embed_fn, threshold=0.78) -> dict

Return structure from semantic_matches:
  {
     'direct': [skills...],
     'alias': [skills...],
     'semantic': [skills...],  # only those added via embedding fallback
     'all': [unique union preserving order canonical->alias->semantic]
  }

Edge Guards:
  - Minimum length for sentence embedding (ignore very short sentences < 15 chars).
  - Ignore semantic match if similarity < threshold.
  - Do not re-add skills already present via direct/alias paths.
  - Lowercases all text for matching; maintains canonical skill names in output.

Future Enhancements:
  - Per-skill custom thresholds based on ambiguity frequency.
  - Negative context filtering ("deprecated", "retired") reducing relevance weight.
"""
from __future__ import annotations

import re
from typing import Dict, List, Callable, Tuple
import numpy as np

WORD_BOUNDARY = r"\b{token}\b"

class SemanticSkillCache:
    def __init__(self):
        # Mapping canonical skill -> { 'aliases': [...], 'vectors': {alias_or_skill: np.array([...])} }
        self.skills: Dict[str, Dict[str, Dict[str, np.ndarray]]] = {}

    def add_skill(self, skill: str, aliases: List[str], embed_fn: Callable[[str], List[float]]):
        vecs = {}
        # Embed the canonical skill phrase itself
        vecs[skill] = np.array(embed_fn(skill), dtype=float)
        for alias in aliases:
            vecs[alias] = np.array(embed_fn(alias), dtype=float)
        self.skills[skill] = {
            'aliases': aliases,
            'vectors': vecs
        }

def _word_boundary_match(token: str, sentence_lower: str) -> bool:
    pattern = re.compile(WORD_BOUNDARY.format(token=re.escape(token.lower())))
    return bool(pattern.search(sentence_lower))

def load_skill_semantic_cache(taxonomy: Dict, embed_fn: Callable[[str], List[float]]) -> SemanticSkillCache:
    cache = SemanticSkillCache()
    skills_def = taxonomy.get('skills', {})
    for canonical, meta in skills_def.items():
        aliases = meta.get('aliases', []) or []
        cache.add_skill(canonical.lower(), [a.lower() for a in aliases], embed_fn)
    return cache

def _embed_sentence(sentence: str, embed_fn: Callable[[str], List[float]]) -> np.ndarray:
    return np.array(embed_fn(sentence), dtype=float)

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

def semantic_matches(sentence: str,
                     mandatory_skills: List[str],
                     cache: SemanticSkillCache,
                     embed_fn: Callable[[str], List[float]],
                     threshold: float = 0.78) -> Dict[str, List[str]]:
    sentence_lower = sentence.lower()
    direct: List[str] = []
    alias: List[str] = []
    semantic: List[str] = []

    # Phase 1: direct & alias matching
    # Guard: extremely short sentences (<=4 chars) often just raw tokens; treat them as insufficient context
    # and skip lexical hit counting to avoid over-credit. Return empty so caller can choose to ignore.
    if len(sentence_lower.strip()) <= 4:
        return {'direct': [], 'alias': [], 'semantic': [], 'all': []}

    for skill in mandatory_skills:
        skill_l = skill.lower()
        entry = cache.skills.get(skill_l)
        if not entry:
            continue
        if _word_boundary_match(skill_l, sentence_lower):
            direct.append(skill)
            continue
        for al in entry['aliases']:
            if _word_boundary_match(al, sentence_lower):
                alias.append(skill)
                break

    if direct or alias:
        # Already have lexical matches; skip semantic fallback to avoid over-inflation.
        ordered = list(dict.fromkeys(direct + alias))
        return {
            'direct': direct,
            'alias': alias,
            'semantic': [],
            'all': ordered
        }

    # Phase 2: semantic fallback only if no lexical hits
    if len(sentence_lower) < 15:
        # Too short for reliable semantic vector comparison
        return {'direct': [], 'alias': [], 'semantic': [], 'all': []}

    sent_vec = _embed_sentence(sentence, embed_fn)
    for skill in mandatory_skills:
        skill_l = skill.lower()
        entry = cache.skills.get(skill_l)
        if not entry:
            continue
        # Compare against canonical + each alias; take max similarity
        vectors = entry['vectors']
        sim_max = 0.0
        for phrase, vec in vectors.items():
            sim = _cosine(sent_vec, vec)
            if sim > sim_max:
                sim_max = sim
        if sim_max >= threshold:
            semantic.append(skill)

    ordered = list(dict.fromkeys(semantic))
    return {
        'direct': [],
        'alias': [],
        'semantic': ordered,
        'all': ordered
    }

__all__ = [
    'SemanticSkillCache',
    'load_skill_semantic_cache',
    'semantic_matches'
]
