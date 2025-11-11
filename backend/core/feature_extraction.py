import os
import re
import yaml
from typing import List, Dict, Tuple, Set

from datetime import datetime
_TAXONOMY_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'skills_taxonomy.yaml')

_VERB_PATTERN = re.compile(r"\b(architected|built|optimized|designed|implemented|migrated|refactored|led|improved|reduced|increased|scaled|automated|integrated)\b", re.IGNORECASE)
_METRIC_PATTERN = re.compile(r"(\b\d+%\b|\b\$\d+[km]?\b|\b\d+ (?:ms|seconds?|minutes?|hours?)\b|\b\d+(?:x|X)\b)")

_STOPWORDS = set(["and","or","the","to","for","in","of","with","on","at","a","an"])

class SkillTaxonomy:
    def __init__(self, taxonomy: Dict[str, any]):
        self.skills = taxonomy.get('skills', {})
        self.families = taxonomy.get('families', {})
        # Build reverse alias map
        self.alias_map: Dict[str, str] = {}
        for canon, meta in self.skills.items():
            self.alias_map[canon.lower()] = canon
            for a in meta.get('aliases', []):
                self.alias_map[a.lower()] = canon
        # Family associations for adjacency credit
        self.family_map: Dict[str, Set[str]] = {}
        for fam, meta in self.families.items():
            related = set(meta.get('related', []))
            self.family_map[fam] = related

    @classmethod
    def load(cls, path: str = _TAXONOMY_PATH) -> 'SkillTaxonomy':
        if not os.path.exists(path):
            return cls({})
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        return cls(data)

    def normalize_skill(self, token: str) -> str:
        return self.alias_map.get(token.lower().strip(), token.lower().strip())

    def expand_to_families(self, skill: str) -> Set[str]:
        canonical = self.normalize_skill(skill)
        meta = self.skills.get(canonical, {})
        families = meta.get('families', [])
        expanded: Set[str] = set()
        for fam in families:
            expanded |= {canonical} | self.family_map.get(fam, set())
        return expanded or {canonical}


def tokenize_text(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9_+#\.]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def extract_skills_from_list(raw_list, taxonomy: SkillTaxonomy) -> Set[str]:
    skills: Set[str] = set()
    if isinstance(raw_list, list):
        for item in raw_list:
            if not item:
                continue
            for token in tokenize_text(str(item)):
                normalized = taxonomy.normalize_skill(token)
                if normalized in taxonomy.skills:
                    skills.add(normalized)
    elif isinstance(raw_list, str):
        for token in tokenize_text(raw_list):
            normalized = taxonomy.normalize_skill(token)
            if normalized in taxonomy.skills:
                skills.add(normalized)
    return skills


def build_cv_skill_set(cv_doc: Dict[str, any], taxonomy: SkillTaxonomy) -> Set[str]:
    skill_sources = []
    for field in ["skills", "technical_skills", "summary", "work_experience", "projects"]:
        val = cv_doc.get(field)
        if val:
            skill_sources.append(val)
    aggregated: Set[str] = set()
    for src in skill_sources:
        aggregated |= extract_skills_from_list(src, taxonomy)
    return aggregated


def build_jd_required_skill_set(jd_doc: Dict[str, any], taxonomy: SkillTaxonomy) -> Set[str]:
    required_fields = ["required_skills", "technical_skills", "required_qualifications"]
    aggregated: Set[str] = set()
    for field in required_fields:
        val = jd_doc.get(field)
        if val:
            aggregated |= extract_skills_from_list(val, taxonomy)
    return aggregated

def build_jd_skill_groups(jd_doc: Dict[str, any], taxonomy: SkillTaxonomy) -> Tuple[Set[str], Set[str]]:
    """Return (mandatory_skills, optional_skills) sets.
    Mandatory: required_skills, required_qualifications, technical_skills
    Optional: preferred_skills, soft_skills, certifications, responsibilities
    Responsibilities treated as optional because they can add context but may not be hard requirements.
    """
    mandatory_fields = ["required_skills", "required_qualifications", "technical_skills"]
    optional_fields = ["preferred_skills", "soft_skills", "certifications", "responsibilities"]
    mandatory: Set[str] = set()
    optional: Set[str] = set()
    for f in mandatory_fields:
        val = jd_doc.get(f)
        if val:
            mandatory |= extract_skills_from_list(val, taxonomy)
    for f in optional_fields:
        val = jd_doc.get(f)
        if val:
            optional |= extract_skills_from_list(val, taxonomy)
    # remove any overlap (mandatory precedence)
    optional -= mandatory
    return mandatory, optional


def compute_skill_coverage(required: Set[str], cv_skills: Set[str], taxonomy: SkillTaxonomy) -> Tuple[float, List[str], Dict[str, float]]:
    if not required:
        return 1.0, [], {}
    matched = 0.0
    detail: Dict[str, float] = {}
    missing = []
    for skill in required:
        if skill in cv_skills:
            matched += 1.0
            detail[skill] = 1.0
        else:
            # adjacency credit via families / related clusters
            fam_expanded = taxonomy.expand_to_families(skill)
            if fam_expanded & cv_skills:
                matched += 0.5
                detail[skill] = 0.5
            else:
                detail[skill] = 0.0
                missing.append(skill)
    coverage = matched / float(len(required))
    return coverage, missing, detail


def depth_indicators(cv_doc: Dict[str, any], skills: Set[str]) -> Dict[str, Dict[str, int]]:
    # Simple heuristic: count verbs + metrics near skill tokens in text fields
    text_fields = []
    for field in ["work_experience", "projects", "summary"]:
        val = cv_doc.get(field)
        if isinstance(val, list):
            text_fields.extend([str(v) for v in val])
        elif isinstance(val, str):
            text_fields.append(val)
    joined = "\n".join(text_fields).lower()
    indicators: Dict[str, Dict[str, int]] = {}
    for skill in skills:
        pattern = re.compile(rf"\b{re.escape(skill)}\b", re.IGNORECASE)
        occurrences = pattern.findall(joined)
        window_matches = 0
        verb_hits = 0
        metric_hits = 0
        # naive sliding window around each occurrence
        for m in pattern.finditer(joined):
            start = max(0, m.start()-80)
            end = min(len(joined), m.end()+80)
            snippet = joined[start:end]
            verb_hits += len(_VERB_PATTERN.findall(snippet))
            metric_hits += len(_METRIC_PATTERN.findall(snippet))
            window_matches += 1
        indicators[skill] = {
            "mentions": len(occurrences),
            "context_windows": window_matches,
            "verbs": verb_hits,
            "metrics": metric_hits
        }
    return indicators


def aggregate_depth_score(indicators: Dict[str, Dict[str,int]], required: Set[str]) -> float:
    if not required:
        return 0.0
    scores = []
    for skill in required:
        meta = indicators.get(skill, {})
        # Weighted heuristic: verbs + metrics amplify depth; mentions provide base
        mentions = meta.get("mentions", 0)
        verbs = meta.get("verbs", 0)
        metrics = meta.get("metrics", 0)
        raw = mentions + 2*verbs + 3*metrics
        scores.append(raw)
    if not scores:
        return 0.0
    max_raw = max(scores)
    if max_raw == 0:
        return 0.0
    # Normalize by max to keep [0,1]
    return sum(s/max_raw for s in scores)/len(scores)


def placeholder_recency(cv_doc: Dict[str, any], required: Set[str]) -> float:
    """Heuristic recency score.
    - Looks for skills in the summary (assumed most recent professional branding)
    - Looks for skills in the first work_experience entry (assumed current/most recent job)
    Safely handles structured dict entries instead of naively joining raw objects.
    """
    summary = (cv_doc.get("summary") or "")
    if isinstance(summary, list):  # sometimes summary might be a list of bullets
        summary = " \n".join(str(s) for s in summary)
    summary_lower = summary.lower()

    work = cv_doc.get("work_experience") or []
    first_entry_text = ""
    if isinstance(work, list) and work:
        first_entry = work[0]
        if isinstance(first_entry, dict):
            # Concatenate string-like fields for context window
            parts = []
            for k, v in first_entry.items():
                if isinstance(v, (str, int, float)):
                    parts.append(str(v))
                elif isinstance(v, list):
                    parts.extend(str(x) for x in v if isinstance(x, (str, int, float)))
            first_entry_text = " ".join(parts)
        else:
            first_entry_text = str(first_entry)
    first_entry_lower = first_entry_text.lower()

    score = 0.0
    for skill in required:
        if skill in summary_lower:
            score += 1.0
        elif skill in first_entry_lower:
            score += 0.7
    return score / max(len(required), 1)

# ===================== Enhanced Recency & Coverage Threshold =====================

DATE_PATTERN = re.compile(r"\b(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+)?(20\d{2}|19\d{2})\b", re.IGNORECASE)

def extract_years(text: str) -> List[int]:
    years = []
    for m in DATE_PATTERN.finditer(text):
        year = m.group(2)
        try:
            years.append(int(year))
        except ValueError:
            continue
    return years

def improved_recency(cv_doc: Dict[str, any], required: Set[str]) -> float:
    """Compute a recency score based on last year each required skill appears in experience entries.
    Scoring: For each skill present, score = 1 / (1 + 0.3 * years_since_last_use). Absent skill contributes 0.
    Returns average across required skills.
    Falls back to placeholder_recency if no date info available.
    """
    work = cv_doc.get("work_experience") or []
    if not isinstance(work, list) or not work:
        return placeholder_recency(cv_doc, required)
    now_year = datetime.utcnow().year
    skill_last_year: Dict[str, int] = {}
    any_years_found = False
    for entry in work:
        # Collect textual content of entry
        if isinstance(entry, dict):
            parts = []
            for k, v in entry.items():
                if isinstance(v, (str, int, float)):
                    parts.append(str(v))
                elif isinstance(v, list):
                    parts.extend(str(x) for x in v if isinstance(x, (str, int, float)))
            text_block = " ".join(parts).lower()
        else:
            text_block = str(entry).lower()
        years = extract_years(text_block)
        if years:
            any_years_found = True
            block_year = max(years)
        else:
            block_year = None
        for skill in required:
            if skill in text_block:
                if block_year is not None:
                    prev = skill_last_year.get(skill)
                    if prev is None or block_year > prev:
                        skill_last_year[skill] = block_year
    if not any_years_found:
        return placeholder_recency(cv_doc, required)
    scores = []
    for skill in required:
        last = skill_last_year.get(skill)
        if last is None:
            scores.append(0.0)
        else:
            years_since = max(0, now_year - last)
            scores.append(1.0 / (1.0 + 0.3 * years_since))
    return sum(scores) / max(len(scores), 1)

def dynamic_coverage_threshold(coverages: List[float]) -> float:
    """Derive a dynamic coverage threshold from distribution.
    Heuristic: use max(0.4, min(p25, 0.7)), capped by median if p25 > median.
    Falls back to 0.4 for very small sample sizes.
    """
    n = len(coverages)
    if n < 6:
        return 0.4
    sorted_cov = sorted(coverages)
    def pct(p: float) -> float:
        idx = int(p * (n - 1))
        return sorted_cov[idx]
    p25 = pct(0.25)
    p50 = pct(0.50)
    threshold = max(0.4, min(p25, 0.7))
    if threshold > p50:
        threshold = p50
    return round(threshold, 3)

