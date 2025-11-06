"""Identifier and naming utilities for dynamic, job-specific storage.

Provides helpers to sanitize company and job title strings for use as
MongoDB / Chroma collection names and to compute stable hashed IDs.
"""

import hashlib
import re
import os
from typing import Tuple

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

def sanitize_fragment(value: str) -> str:
	"""Sanitize a string fragment for safe collection naming.

	- Lowercase
	- Replace non-alphanumeric with single underscore
	- Trim leading/trailing underscores
	- Collapse multiple underscores
	- Truncate to 48 chars to keep names manageable
	"""
	if not value:
		return "unknown"
	v = value.lower().strip()
	v = _NON_ALNUM_RE.sub("_", v)
	v = re.sub(r"_+", "_", v)
	v = v.strip("_")
	return v[:48] if v else "unknown"

def build_collection_names(company: str, job_title: str) -> Tuple[str, str]:
	"""Return tuple (cv_collection_name, jd_collection_name) for given company/job."""
	company_slug = sanitize_fragment(company)
	job_slug = sanitize_fragment(job_title)
	cv_collection = f"cv_{company_slug}__{job_slug}"
	jd_collection = f"jd_{company_slug}__{job_slug}"
	return cv_collection, jd_collection

def build_mongo_names(company: str, job_title: str) -> Tuple[str, str, str]:
	"""Return tuple (db_name, cv_collection, jd_collection) for Mongo multi-tenancy.

	Design update:
	- Database per company now uses the raw sanitized company slug (no 'cmp_' prefix)
	- Collections remain job-scoped with distinct prefixes to avoid mixing.
	- Fallback 'unknown' when fragment missing.
	"""
	company_slug = sanitize_fragment(company)
	job_slug = sanitize_fragment(job_title)
	db_name = company_slug  # Simpler: just the company slug
	cv_collection = f"cvs_{job_slug}"  # CVs for this job role
	jd_collection = f"jd_{job_slug}"   # JD for this job role
	return db_name, cv_collection, jd_collection

def build_persist_directories(cv_root: str, jd_root: str, company: str) -> Tuple[str, str]:
	"""Return per-company persist directories for Chroma (cv_dir, jd_dir).

	Each company gets isolated subdirectories under configured roots to avoid index
	pollution and to enable clean deletion / backup per tenant.
	"""
	company_slug = sanitize_fragment(company)
	cv_dir = os.path.join(cv_root, company_slug)
	jd_dir = os.path.join(jd_root, company_slug)
	return cv_dir, jd_dir

def compute_jd_id(company: str, job_title: str) -> str:
	"""Compute deterministic JD ID hash from company + job title.

	Format: sha256(f"{job_title.lower()}|{company.lower()}")
	Fallbacks handled by sanitize_fragment.
	"""
	comp = company.lower().strip() if company else ""
	job = job_title.lower().strip() if job_title else ""
	base = f"{job}|{comp}" if job or comp else "unknown"
	return hashlib.sha256(base.encode("utf-8")).hexdigest()

def compute_cv_id(email: str) -> str:
	"""Compute deterministic CV ID from candidate email (lowercased & trimmed)."""
	e = (email or "").lower().strip()
	if not e:
		raise ValueError("Email required for CV ID")
	return hashlib.sha256(e.encode("utf-8")).hexdigest()

