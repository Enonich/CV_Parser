"""Feature persistence utilities.

Persists per-candidate feature vectors (skills, impact, scores) into a MongoDB collection
for later offline analysis / learned weighting. Fails softly (logs warning) on errors.

Collection naming convention:
  features_<job_slug>

Document schema (example):
{
  _id: <cv_id + ':' + job_slug>,
  cv_id: <cv_id>,
  job_slug: <sanitized job title>,
  company: <company_name>,
  timestamp: <ISO datetime>,
  skill_mandatory_coverage: float,
  skill_optional_coverage: float,
  skill_depth_score: float,
  skill_recency_score: float,
  impact_score: float,
  impact_raw_score: float,
  impact_event_count: int,
  combined_score_pre_impact: float,
  combined_score_post_impact: float,
  eligibility_gated_out: bool,
  impact_weight_applied: float,
  version: 1
}
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Dict, Any
from pymongo import MongoClient

from backend.core.identifiers import sanitize_fragment

logger = logging.getLogger(__name__)


def persist_features(connection_string: str, company_name: str, job_title: str, candidate_records: List[Dict[str, Any]]) -> int:
    """Persist candidate feature vectors to MongoDB.

    Returns number of successfully upserted documents.
    """
    try:
        client = MongoClient(connection_string)
        db_name = sanitize_fragment(company_name)
        db = client[db_name]
        job_slug = sanitize_fragment(job_title)
        coll_name = f"features_{job_slug}"  # one collection per job
        coll = db[coll_name]
    except Exception as e:
        logger.warning(f"Feature persistence init failed: {e}")
        return 0

    ts = datetime.datetime.utcnow().isoformat()
    upserted = 0
    for rec in candidate_records:
        try:
            cv_id = rec.get('cv_id')
            if not cv_id:
                continue
            doc = {
                '_id': f"{cv_id}:{job_slug}",
                'cv_id': cv_id,
                'job_slug': job_slug,
                'company': company_name,
                'timestamp': ts,
                'skill_mandatory_coverage': rec.get('skill_mandatory_coverage'),
                'skill_optional_coverage': rec.get('skill_optional_coverage'),
                'skill_depth_score': rec.get('skill_depth_score'),
                'skill_recency_score': rec.get('skill_recency_score'),
                'impact_score': rec.get('impact_score'),
                'impact_raw_score': rec.get('impact_raw_score'),
                'impact_event_count': rec.get('impact_event_count'),
                'combined_score_pre_impact': rec.get('combined_score_pre_impact'),
                'combined_score_post_impact': rec.get('combined_score'),
                'eligibility_gated_out': rec.get('eligibility_gated_out'),
                'impact_weight_applied': rec.get('score_components', {}).get('impact_weight_applied'),
                'version': 1
            }
            coll.update_one({'_id': doc['_id']}, {'$set': doc}, upsert=True)
            upserted += 1
        except Exception as e_doc:
            logger.warning(f"Feature doc upsert failed for cv_id={rec.get('cv_id')}: {e_doc}")
            continue
    try:
        client.close()
    except Exception:
        pass
    logger.info(f"Persisted {upserted} feature vectors to collection '{coll_name}'")
    return upserted

__all__ = ["persist_features"]