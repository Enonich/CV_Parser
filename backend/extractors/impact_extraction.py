"""Impact extraction module.

Parses CV structured data (work_experience responsibilities, projects, achievements) to
identify STAR-like impact events: action verb + metric + outcome phrase.

Returned structure (contract):
{
  "impact_events": [
     {
       "sentence": str,
       "verbs": [str],              # detected action/performance verbs
       "metrics": [                 # numeric / percentage / currency metrics
          {"raw": str, "value": float, "type": "percent|currency|count", "normalized": float}
       ],
       "outcome_phrase": str | None, # trailing outcome/result phrase if detected
       "direction": "increase|decrease|neutral", # dominant direction semantics
       "event_score": float,        # raw uncalibrated score for this event
       "components": {              # sub-score breakdown
          "verb_weight": float,
          "metric_magnitude": float,
          "outcome_bonus": float,
          "direction_modifier": float
       }
     }
  ],
  "raw_impact_score": float,        # sum of top-N event scores (log-scaled)
  "impact_event_count": int         # total extracted events
}

Scoring heuristic (per event):
  event_score = verb_weight * (1 + log(1 + metric_magnitude)) * outcome_bonus * direction_modifier

Where:
  - verb_weight derived from verb category mapping.
  - metric_magnitude is aggregated normalized metric strength (currency/percent/count).
  - outcome_bonus (>1) if explicit outcome/result phrase detected.
  - direction_modifier favors positive improvements (increase revenue, decrease cost).

Normalization strategy (first pass):
  - Percent: value / 50 (clamped 0..4) before log, giving diminishing returns.
  - Currency: convert k/m/b qualifiers then scale: min(value / 1000, 10000). (Assumes USD or unspecified.)
  - Count: raw integer scaled min(count, 100000).
  - Aggregate metric_magnitude = max(percent_component, currency_component, count_component) to emphasize strongest.

Future TODOs (phase 2):
  - Multi-metric fusion instead of max.
  - Currency localization handling.
  - Outcome sentiment and risk mitigation detection.
  - Percentile calibration (applied in workflow after collection across candidates).
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple, Optional, Any

# ---------------------------
# Patterns & Dictionaries
# ---------------------------

ACTION_VERBS_PRIMARY = {
    # Growth / optimization
    "increased": 1.25, "grew": 1.25, "expanded": 1.2, "boosted": 1.25, "accelerated": 1.3, "optimized": 1.3,
    "improved": 1.25, "enhanced": 1.2, "scaled": 1.3, "launched": 1.15, "delivered": 1.15, "implemented": 1.15,
    "developed": 1.1, "built": 1.1, "designed": 1.1, "architected": 1.2, "automated": 1.25,
    # Efficiency / reduction
    "reduced": 1.3, "decreased": 1.3, "cut": 1.3, "lowered": 1.25, "saved": 1.35, "eliminated": 1.3,
    # Ownership / leadership
    "led": 1.2, "managed": 1.15, "owned": 1.15, "directed": 1.2, "spearheaded": 1.3, "coordinated": 1.1,
    "negotiated": 1.25, "secured": 1.3, "won": 1.25, "achieved": 1.3
}

OUTCOME_CONNECTORS = [
    "resulting in", "resulted in", "leading to", "led to", "yielding", "achieving", "delivering", "producing", "creating"
]

PERCENT_PATTERN = re.compile(r"\b(\d{1,3}(?:\.\d+)?)%\b")
# Range pattern MUST include trailing % after second number to treat as percent range
RANGE_PATTERN = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*[-–]\s*(\d{1,3}(?:\.\d+)?)%")
NUMBER_WITH_QUALIFIER_PATTERN = re.compile(
    r"\b(\$?\d{1,3}(?:[\,\d]{0,3})?(?:\.\d+)?\s*(?:k|m|b|million|billion|thousand))\b",
    re.IGNORECASE
)
PLAIN_INTEGER_PATTERN = re.compile(r"\b\d{1,9}\b")
TEXTUAL_NUMBER_MAP = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000
}

CONTEXT_KEYWORDS = {
    "revenue": "revenue", "arr": "revenue", "sales": "revenue", "pipeline": "revenue",
    "cost": "cost", "expense": "cost", "expenses": "cost", "downtime": "time", "latency": "time",
    "hours": "time", "time": "time", "customers": "customers", "users": "users", "transactions": "transactions"
}

DECREASE_VERBS = {"reduced", "decreased", "cut", "lowered", "saved", "eliminated"}
INCREASE_VERBS = {"increased", "grew", "expanded", "boosted", "accelerated", "scaled"}

QUALIFIER_MAP = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "billion": 1_000_000_000,
}


def _normalize_currency(raw: str) -> Optional[float]:
    raw = raw.lower().replace(",", "").strip()
    # Remove leading $ if exists
    if raw.startswith("$"):
        raw = raw[1:]
    # Split number and potential qualifier
    match = re.match(r"(\d+(?:\.\d+)?)(?:\s*(k|m|b|million|billion|thousand))?", raw)
    if not match:
        return None
    num = float(match.group(1))
    qual = match.group(2)
    if qual:
        num *= QUALIFIER_MAP.get(qual, 1)
    return num


def _normalize_percent(p: str) -> Optional[float]:
    try:
        return float(p.rstrip('%'))
    except ValueError:
        return None


def _extract_metrics(sentence: str) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    lower = sentence.lower()
    # Percent ranges (take midpoint)
    for match in RANGE_PATTERN.finditer(sentence):
        a, b = match.group(1), match.group(2)
        try:
            v1 = float(a); v2 = float(b)
            mid = (v1 + v2) / 2.0
            metrics.append({"raw": f"{a}-{b}%", "value": mid, "type": "percent", "normalized": mid / 50.0})
        except ValueError:
            pass
    # Percentages
    for m in PERCENT_PATTERN.findall(sentence):
        val = _normalize_percent(m + '%')
        if val is not None:
            metrics.append({"raw": m + '%', "value": val, "type": "percent", "normalized": val / 50.0})
    # Currency / qualified numbers
    for m in NUMBER_WITH_QUALIFIER_PATTERN.findall(sentence):
        val = _normalize_currency(m)
        if val is not None:
            metrics.append({"raw": m, "value": val, "type": "currency", "normalized": min(val / 1000.0, 10000.0)})
    # Textual numbers followed by contextual keywords (e.g., "ten percent", "two million")
    tokens = re.split(r"\s+", lower)
    for i, tok in enumerate(tokens):
        if tok in TEXTUAL_NUMBER_MAP:
            # Basic textual number (no chaining multiplication beyond single scale word)
            base = TEXTUAL_NUMBER_MAP[tok]
            nxt = tokens[i+1] if i+1 < len(tokens) else ''
            value = base
            raw_form = tok
            # Percent handling ("ten percent")
            if nxt.startswith('percent') or nxt == 'pct':
                metrics.append({"raw": raw_form + "%", "value": value, "type": "percent", "normalized": value / 50.0})
                continue
            # Currency scale ("two million")
            if nxt in ['million','billion','thousand']:
                mult = QUALIFIER_MAP.get(nxt, 1)
                value = base * mult
                raw_form += f" {nxt}"
                metrics.append({"raw": raw_form, "value": value, "type": "currency", "normalized": min(value / 1000.0, 10000.0)})
                continue
    # Plain counts (avoid duplicates of currency numbers)
    existing_raws = {mm["raw"].lower() for mm in metrics}
    for m in PLAIN_INTEGER_PATTERN.findall(sentence):
        if m.lower() in existing_raws:
            continue
        try:
            val = int(m)
            if val > 10:
                metrics.append({"raw": m, "value": val, "type": "count", "normalized": min(val, 100000)})
        except ValueError:
            continue
    # Add simple context classification to each metric
    for metric in metrics:
        metric['context'] = None
        metric_pos = lower.find(metric['raw'].lower())
        if metric_pos == -1:
            continue

        best_dist = float('inf')
        best_context = None

        for kw, cls in CONTEXT_KEYWORDS.items():
            kw_pos = lower.find(kw)
            while kw_pos != -1:
                dist = abs(metric_pos - kw_pos)
                if dist < best_dist:
                    best_dist = dist
                    best_context = cls
                kw_pos = lower.find(kw, kw_pos + 1)
        
        metric['context'] = best_context
    return metrics


def _detect_verbs(sentence: str) -> List[str]:
    found = []
    lower = sentence.lower()
    for verb in ACTION_VERBS_PRIMARY.keys():
        # Whole word matching
        if re.search(rf"\b{re.escape(verb)}\b", lower):
            found.append(verb)
    return found


def _detect_outcome_phrase(sentence: str) -> Optional[str]:
    lower = sentence.lower()
    for conn in OUTCOME_CONNECTORS:
        idx = lower.find(conn)
        if idx != -1:
            # Outcome phrase is substring after connector (next 120 chars max to avoid huge spans)
            tail = sentence[idx + len(conn):].strip()
            return tail[:120].strip(' .;') if tail else None
    return None


def _direction(verbs: List[str]) -> str:
    if any(v in DECREASE_VERBS for v in verbs):
        return "decrease"
    if any(v in INCREASE_VERBS for v in verbs):
        return "increase"
    return "neutral"


def _score_event(verbs: List[str], metrics: List[Dict[str, Any]], outcome_phrase: Optional[str]) -> Tuple[float, Dict[str, float]]:
    if not verbs or not metrics:
        return 0.0, {"verb_weight": 0.0, "metric_magnitude": 0.0, "outcome_bonus": 1.0, "direction_modifier": 1.0}
    verb_weight = max(ACTION_VERBS_PRIMARY.get(v, 1.0) for v in verbs)
    # Aggregate metric magnitude (use strongest normalized component)
    metric_magnitude = max(m.get("normalized", 0.0) for m in metrics)
    # Outcome bonus
    outcome_bonus = 1.15 if outcome_phrase else 1.0
    direction = _direction(verbs)
    # Favor improvements (increase revenue, decrease cost) – simple multiplier
    direction_modifier = 1.1 if direction in {"increase", "decrease"} else 1.0
    # Context emphasis: revenue gains or cost reductions amplify metric slightly (cap total multiplier)
    has_revenue = any(m.get('context') == 'revenue' for m in metrics)
    has_cost = any(m.get('context') == 'cost' for m in metrics)
    context_multiplier = 1.0
    if has_revenue:
        context_multiplier += 0.05
    if has_cost:
        context_multiplier += 0.05
    if context_multiplier > 1.1:
        context_multiplier = 1.1
    event_score = verb_weight * (1.0 + math.log(1.0 + metric_magnitude)) * outcome_bonus * direction_modifier
    event_score *= context_multiplier
    return event_score, {
        "verb_weight": verb_weight,
        "metric_magnitude": metric_magnitude,
        "outcome_bonus": outcome_bonus,
        "direction_modifier": direction_modifier,
        "context_multiplier": context_multiplier
    }


def _candidate_sentences(cv_doc: Dict[str, Any]) -> List[str]:
    sentences: List[str] = []
    # Work experience responsibilities
    for job in cv_doc.get("work_experience", []) or []:
        for resp in job.get("responsibilities", []) or []:
            if isinstance(resp, str) and len(resp) > 15:
                sentences.append(resp.strip())
    # Projects achievements (if structured as list of dicts with 'description' or 'impact')
    for proj in cv_doc.get("projects", []) or []:
        if isinstance(proj, dict):
            for key in ["description", "impact", "result"]:
                txt = proj.get(key)
                if isinstance(txt, str) and len(txt) > 15:
                    sentences.append(txt.strip())
        elif isinstance(proj, str) and len(proj) > 15:
            sentences.append(proj.strip())
    # Generic achievements field
    for ach in cv_doc.get("achievements", []) or []:
        if isinstance(ach, str) and len(ach) > 15:
            sentences.append(ach.strip())
    return sentences[:1000]  # hard cap safety


def extract_impact_features(cv_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Main public function to extract impact events and aggregate score."""
    sentences = _candidate_sentences(cv_doc)
    impact_events = []
    for sent in sentences:
        verbs = _detect_verbs(sent)
        metrics = _extract_metrics(sent)
        if not verbs and not metrics:
            continue
        outcome_phrase = _detect_outcome_phrase(sent)
        event_score, components = _score_event(verbs, metrics, outcome_phrase)
        if event_score <= 0:
            continue
        impact_events.append({
            "sentence": sent,
            "verbs": verbs,
            "metrics": metrics,
            "outcome_phrase": outcome_phrase,
            "direction": _direction(verbs),
            "event_score": event_score,
            "components": components
        })
    # Rank events by event_score and take top-N (diminishing returns beyond 8)
    impact_events.sort(key=lambda e: e["event_score"], reverse=True)
    TOP_N = 8
    top_events = impact_events[:TOP_N]
    raw_impact_score = sum(e["event_score"] for e in top_events)
    return {
        "impact_events": top_events,
        "raw_impact_score": raw_impact_score,
        "impact_event_count": len(impact_events)
    }


__all__ = ["extract_impact_features"]
