"""Scoring utilities for applying skill bonuses, mandatory strength, and impact relevance weighting.

This module factors out the adjustment logic from the workflow for easier unit testing.

Contract:
  apply_skill_and_impact_adjustments(result: dict, mandatory_skills: list[str], config: dict, show_details: bool) -> dict

Inputs (fields expected in `result` before call):
  combined_score or total_score (base retrieval score)
  skill_mandatory_coverage, skill_optional_coverage
  impact_score (calibrated 0..1), impact_raw_score, impact_event_count
  impact_events (optional if show_details)

Adds/updates:
  combined_score_pre_impact
  combined_score (final)
  score_components[...] with breakdown
  impact_relevance_ratio, impact_relevance_skills

Edge Guards:
  - Impact applied only if >=2 events.
  - Relevance ratio gating via impact_min_relevance.
"""
from __future__ import annotations

from typing import Dict, Any, List

from backend.core.impact_relevance import compute_impact_relevance
from backend.core.semantic_skill_matcher import semantic_matches, SemanticSkillCache

MANDATORY_COVERAGE_BONUS_WEIGHT = 0.10
OPTIONAL_COVERAGE_BONUS_WEIGHT = 0.05


def apply_skill_and_impact_adjustments(result: Dict[str, Any],
                                       mandatory_skills: List[str],
                                       config: Dict[str, Any],
                                       show_details: bool = False,
                                       semantic_cache: SemanticSkillCache | None = None,
                                       embed_fn: callable | None = None) -> Dict[str, Any]:
    search_cfg = config.get('search', {}) if config else {}
    impact_weight = float(search_cfg.get('impact_weight', 0.08))
    mandatory_strength_factor = float(search_cfg.get('mandatory_strength_factor', 0.15))
    impact_min_relevance = float(search_cfg.get('impact_min_relevance', 0.0))

    # Skill bonus (additive)
    skill_bonus = (
        result.get('skill_mandatory_coverage', 0.0) * MANDATORY_COVERAGE_BONUS_WEIGHT +
        result.get('skill_optional_coverage', 0.0) * OPTIONAL_COVERAGE_BONUS_WEIGHT
    )
    base_score = result.get('combined_score', result.get('total_score', 0.0)) + skill_bonus

    mandatory_cov = result.get('skill_mandatory_coverage', 0.0)
    boosted_base = base_score * (1.0 + mandatory_cov * mandatory_strength_factor)
    result['combined_score_pre_impact'] = boosted_base

    # Impact relevance
    impact_events = result.get('impact_events', []) if show_details else []
    if not impact_events and result.get('impact_event_count', 0) > 0:
        relevance_ratio, relevant_skills = 0.0, []
    else:
        relevance_ratio, relevant_skills = compute_impact_relevance(impact_events, mandatory_skills)

    # Semantic fallback: if lexical relevance is zero and we have events + cache + embed function
    if show_details and relevance_ratio == 0.0 and impact_events and semantic_cache and embed_fn:
        semantic_hits_events = 0
        semantic_skill_set = set()
        threshold = float(search_cfg.get('semantic_relevance_threshold', 0.78))
        for ev in impact_events:
            sent = ev.get('sentence', '')
            if not isinstance(sent, str) or len(sent) < 15:
                continue
            matches = semantic_matches(sent, mandatory_skills, semantic_cache, embed_fn, threshold=threshold)
            if matches['all']:
                semantic_hits_events += 1
                for sk in matches['all']:
                    semantic_skill_set.add(sk)
        if semantic_hits_events > 0:
            relevance_ratio = semantic_hits_events / max(len(impact_events), 1)
            relevant_skills = sorted(semantic_skill_set)
            result['impact_relevance_semantic_used'] = True
            result['impact_relevance_semantic_threshold'] = threshold
        else:
            result['impact_relevance_semantic_used'] = False
    else:
        result['impact_relevance_semantic_used'] = False
    result['impact_relevance_ratio'] = relevance_ratio
    result['impact_relevance_skills'] = relevant_skills

    # Raw impact component before relevance scaling
    if result.get('impact_event_count', 0) >= 2:
        impact_component_raw = impact_weight * result.get('impact_score', 0.0)
    else:
        impact_component_raw = 0.0

    if relevance_ratio < impact_min_relevance:
        impact_component_final = 0.0
    else:
        impact_component_final = impact_component_raw * (relevance_ratio if relevance_ratio > 0 else 0.0)

    result['combined_score'] = boosted_base + impact_component_final

    sc = result.get('score_components') or {}
    sc.update({
        'skill_bonus': skill_bonus,
        'skill_mandatory_coverage': mandatory_cov,
        'skill_optional_coverage': result.get('skill_optional_coverage', 0.0),
        'mandatory_strength_factor': mandatory_strength_factor,
        'base_score_plus_skill_bonus': base_score,
        'boosted_base_after_mandatory': boosted_base,
        'impact_raw_score': result.get('impact_raw_score'),
        'impact_score_calibrated': result.get('impact_score'),
        'impact_weight_applied': impact_weight if result.get('impact_event_count', 0) >= 2 else 0.0,
        'impact_relevance_ratio': relevance_ratio,
        'impact_relevance_skills': relevant_skills,
        'impact_component_raw': impact_component_raw,
        'impact_component_final': impact_component_final,
        'combined_score_pre_impact': boosted_base,
        'impact_component': impact_component_final,
    })
    result['score_components'] = sc
    return result

__all__ = ['apply_skill_and_impact_adjustments']
