"""Evaluation utilities for ranking quality analysis.

Provides core metrics to compare baseline vs impact-weighted rankings using
persisted candidate feature vectors.

Functions:
  precision_at_k(relevance_labels, ranked_ids, k) -> float
  reciprocal_rank(relevance_labels, ranked_ids) -> float
  spearman_rank_corr(list_a, list_b) -> float
  compute_lift_stats(features) -> dict

Expectations:
  - relevance_labels: dict mapping cv_id -> bool (True = relevant / match).
  - ranked_ids: ordered list of cv_ids (highest score first).
  - features: list of dicts each containing 'cv_id', 'combined_score_pre_impact', 'combined_score'.

Spearman implementation is dependency-free (manual). For large N consider scipy.
"""
from __future__ import annotations

from typing import Dict, List, Iterable, Any

def precision_at_k(relevance_labels: Dict[str, bool], ranked_ids: List[str], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = 0
    cutoff = ranked_ids[:k]
    for cid in cutoff:
        if relevance_labels.get(cid, False):
            hits += 1
    return hits / k

def reciprocal_rank(relevance_labels: Dict[str, bool], ranked_ids: List[str]) -> float:
    for idx, cid in enumerate(ranked_ids, start=1):
        if relevance_labels.get(cid, False):
            return 1.0 / idx
    return 0.0

def _rank_positions(values: List[float]) -> Dict[int, int]:
    # Stable ranking: higher value -> better rank (1 = best). Handles ties by average of indices.
    indexed = list(enumerate(values))
    # Sort descending by value
    indexed.sort(key=lambda x: x[1], reverse=True)
    ranks: Dict[int, float] = {}
    i = 0
    while i < len(indexed):
        j = i
        val = indexed[i][1]
        # Collect ties
        while j < len(indexed) and indexed[j][1] == val:
            j += 1
        # Average rank positions (1-based)
        rank_val = sum(range(i + 1, j + 1)) / (j - i)
        for k in range(i, j):
            ranks[indexed[k][0]] = rank_val
        i = j
    return {idx: int(r) if r.is_integer() else r for idx, r in ranks.items()}

def spearman_rank_corr(list_a: List[float], list_b: List[float]) -> float:
    if len(list_a) != len(list_b) or not list_a:
        return 0.0
    ra = _rank_positions(list_a)
    rb = _rank_positions(list_b)
    n = len(list_a)
    # Spearman rho = 1 - (6 * sum(d^2))/(n*(n^2 -1))
    d_sq = 0.0
    for i in range(n):
        d = ra[i] - rb[i]
        d_sq += d * d
    denom = n * (n * n - 1)
    if denom == 0:
        return 0.0
    return 1.0 - (6.0 * d_sq) / denom

def compute_lift_stats(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not features:
        return {
            'count': 0,
            'avg_delta': 0.0,
            'median_delta': 0.0,
            'improved': 0,
            'worsened': 0,
            'unchanged': 0
        }
    deltas = []
    improved = worsened = unchanged = 0
    for f in features:
        pre = f.get('combined_score_pre_impact')
        post = f.get('combined_score')
        if pre is None or post is None:
            continue
        delta = post - pre
        deltas.append(delta)
        if delta > 1e-9:
            improved += 1
        elif delta < -1e-9:
            worsened += 1
        else:
            unchanged += 1
    if not deltas:
        return {
            'count': 0,
            'avg_delta': 0.0,
            'median_delta': 0.0,
            'improved': 0,
            'worsened': 0,
            'unchanged': 0
        }
    deltas.sort()
    n = len(deltas)
    mid = n // 2
    if n % 2 == 1:
        median = deltas[mid]
    else:
        median = 0.5 * (deltas[mid - 1] + deltas[mid])
    return {
        'count': n,
        'avg_delta': sum(deltas) / n,
        'median_delta': median,
        'improved': improved,
        'worsened': worsened,
        'unchanged': unchanged
    }

__all__ = [
    'precision_at_k',
    'reciprocal_rank',
    'spearman_rank_corr',
    'compute_lift_stats'
]
