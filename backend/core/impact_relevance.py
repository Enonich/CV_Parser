"""Impact relevance computation.

Determines how strongly a candidate's impact events relate to mandatory (required) job skills.
Used to scale impact weighting so that only relevant quantified achievements boost ranking.

Contract:
  compute_impact_relevance(impact_events, mandatory_skills) -> (relevance_ratio, relevant_skills)

Definitions:
  - impact_events: list of dicts (as produced by impact_extraction) each with 'sentence'.
  - mandatory_skills: list of canonical skill strings.
  - relevance_ratio: fraction of impact_events whose sentence contains >=1 mandatory skill token.
  - relevant_skills: distinct mandatory skills matched across all relevant events.

Matching Strategy (phase 1):
  - Case-insensitive substring match on whole skill tokens.
  - Basic word boundary enforced to avoid partial overlaps (e.g., 'go' inside 'goal').
  - Future enhancement: use taxonomy aliases and embedding similarity for fuzzy detection.

Edge Cases:
  - No impact events -> ratio 0.0, empty skill list.
  - Mandatory skills empty -> ratio 0.0.
"""
from __future__ import annotations

import re
from typing import List, Dict, Tuple

WORD_BOUNDARY_TEMPLATE = r"\b{skill}\b"

def _skill_in_sentence(skill: str, sentence: str) -> bool:
    pattern = re.compile(WORD_BOUNDARY_TEMPLATE.format(skill=re.escape(skill.lower())))
    return bool(pattern.search(sentence.lower()))

def compute_impact_relevance(impact_events: List[Dict], mandatory_skills: List[str]) -> Tuple[float, List[str]]:
    if not impact_events or not mandatory_skills:
        return 0.0, []
    relevant_events = 0
    relevant_skills_set = set()
    for ev in impact_events:
        sent = ev.get('sentence', '')
        if not isinstance(sent, str):
            continue
        matched = [s for s in mandatory_skills if _skill_in_sentence(s, sent)]
        if matched:
            relevant_events += 1
            for m in matched:
                relevant_skills_set.add(m)
    total = len(impact_events)
    if total == 0:
        return 0.0, []
    relevance_ratio = relevant_events / total
    return relevance_ratio, sorted(relevant_skills_set)

__all__ = ["compute_impact_relevance"]
