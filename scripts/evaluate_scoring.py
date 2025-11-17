"""Evaluation Harness for Scoring System

Usage (PowerShell):
  python scripts/evaluate_scoring.py --company AcmeCorp --job "Senior Data Engineer" --labels labels.json --k 10

Inputs:
  - Mongo feature collections (features_<job_slug>) with documents containing combined_score & combined_score_pre_impact.
  - labels.json: { "relevance": { "<cv_id>": true/false, ... } }

Outputs:
  - Precision@K
  - Reciprocal Rank
  - Spearman rank correlation (pre vs post impact)
  - Lift distribution stats
  - Top changed candidates summary

Requirements:
  - features persisted via feature_persistence.py
  - pymongo installed

Note: This script is read-only and safe for production; it does not modify DB.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from typing import Dict, List
from pymongo import MongoClient

from backend.core.identifiers import sanitize_fragment
from backend.core.evaluation import precision_at_k, reciprocal_rank, spearman_rank_corr, compute_lift_stats

DEFAULT_CONNECTION = "mongodb://localhost:27017/"

def load_labels(path: str) -> Dict[str, bool]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f) or {}
    return {cid: bool(val) for cid, val in (data.get('relevance') or {}).items()}


def fetch_features(connection_string: str, company: str, job: str) -> List[Dict]:
    client = MongoClient(connection_string)
    db = client[sanitize_fragment(company)]
    coll_name = f"features_{sanitize_fragment(job)}"
    coll = db[coll_name]
    docs = list(coll.find({}, {"cv_id": 1, "combined_score": 1, "combined_score_pre_impact": 1}))
    client.close()
    return docs


def evaluate(company: str, job: str, connection_string: str, labels_path: str, k: int):
    features = fetch_features(connection_string, company, job)
    if not features:
        print("No feature documents found; ensure persistence is enabled and job/company correct.")
        return
    # Build ranked lists
    ranked_post = sorted(features, key=lambda d: d.get('combined_score', -math.inf), reverse=True)
    ranked_pre = sorted(features, key=lambda d: d.get('combined_score_pre_impact', -math.inf), reverse=True)
    post_ids = [d['cv_id'] for d in ranked_post if 'cv_id' in d]
    pre_ids = [d['cv_id'] for d in ranked_pre if 'cv_id' in d]

    labels = load_labels(labels_path)

    # Metrics
    p_at_k_post = precision_at_k(labels, post_ids, k)
    p_at_k_pre = precision_at_k(labels, pre_ids, k)
    rr_post = reciprocal_rank(labels, post_ids)
    rr_pre = reciprocal_rank(labels, pre_ids)
    # For Spearman we need aligned scores lists (order independent but same candidates)
    # Use intersection of candidates having both scores.
    aligned = [f for f in features if f.get('combined_score_pre_impact') is not None and f.get('combined_score') is not None]
    pre_scores = [f['combined_score_pre_impact'] for f in aligned]
    post_scores = [f['combined_score'] for f in aligned]
    spearman = spearman_rank_corr(pre_scores, post_scores)
    lift_stats = compute_lift_stats(aligned)

    # Top lifts
    lifts = [(f['cv_id'], f['combined_score'] - f['combined_score_pre_impact']) for f in aligned]
    lifts.sort(key=lambda x: x[1], reverse=True)
    top_positive = lifts[:5]
    top_negative = [l for l in reversed(lifts[-5:])]

    report = {
        'company': company,
        'job': job,
        'candidate_count': len(features),
        'precision_at_k': {'k': k, 'post': p_at_k_post, 'pre': p_at_k_pre},
        'reciprocal_rank': {'post': rr_post, 'pre': rr_pre},
        'spearman_pre_post': spearman,
        'lift_stats': lift_stats,
        'top_positive_lifts': top_positive,
        'top_negative_lifts': top_negative,
        'labels_loaded': len(labels)
    }

    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Evaluate scoring impact vs baseline.")
    parser.add_argument('--company', required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--connection', default=DEFAULT_CONNECTION)
    parser.add_argument('--labels', default='')
    parser.add_argument('--k', type=int, default=10)
    args = parser.parse_args()
    evaluate(args.company, args.job, args.connection, args.labels, args.k)

if __name__ == '__main__':
    main()
