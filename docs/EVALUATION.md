# Evaluation Methodology

This document details how to measure, interpret, and iterate on CV ↔ JD ranking performance.

## 1. Dataset Preparation

Provide ground-truth labels indicating which CVs are relevant for a given Job Description (JD).

### Formats
1. JSONL (job-centric): each line lists a JD and arrays of relevant/non-relevant CV identifiers.
2. CSV (pairwise): each row is a (jd_id, cv_id, label) triple with label ∈ {0,1}.

### Identifier Consistency
Use stable identifiers (e.g., email or internal UUID). Ensure the same IDs appear in your scoring output.

### Minimal Label Set Strategy
If labeling is expensive:
- Label top 10 initial candidates per JD.
- Add 3–5 obvious non-matches for contrast.
- Expand gradually; add borderline cases to refine precision near the decision boundary.

## 2. Metrics

### Precision@k
Measures proportion of the top-k results that are relevant.
Formula: precision@k = (|relevant_in_top_k|) / k
Use small k (e.g., 3,5) to assess immediate usefulness.

### Reciprocal Rank (RR)
Inverse of the rank of the first relevant CV.
Formula: RR = 1 / rank_first_relevant
If no relevant CV is found in the list, RR = 0.

### Spearman Rank Correlation
Quantifies monotonic relationship between two score orderings (e.g., pre-impact vs final scores).
Interpretation:
- High (≥0.9): Only mild reordering; impact adjustments conservative.
- Moderate (0.6–0.85): Intentional reshuffling; verify gains in precision.
- Low (<0.6): Aggressive shifts; ensure benefits justify volatility.

### Lift Statistics
Aggregated change between two score variants.
Reported:
- mean_delta: Average (final − baseline)
- pct_improved: Fraction of candidates whose score increased
- pct_unchanged: Fraction unchanged
- pct_regressed: Fraction decreased

Interpretation:
- Many small positive lifts: calibration working.
- Few large lifts: strong weighting may need damping.
- High regressed percentage: check mandatory strength factor & relevance thresholds.

### Optional Future Metrics
- recall@k: Requires fuller labeling; use once majority of positives are labeled.
- mean_average_precision (MAP): For richer graded relevance sets.
- nDCG: When you add multi-level relevance (e.g., strong vs weak match).

## 3. Workflow

1. Generate baseline scores (e.g., without impact or with conservative thresholds). Capture `combined_score_pre_impact`.
2. Enable full scoring (impact + semantic relevance). Capture `combined_score`.
3. Run evaluation script to produce metrics JSON.
4. Compare precision@k & RR; ensure improvements outweigh any negative shifts.
5. Adjust one parameter at a time: `impact_weight`, `mandatory_strength_factor`, `impact_min_relevance`, `semantic_relevance_threshold`.
6. Iterate until precision@k stabilizes; optionally increase recall with broader skill taxonomy.

## 4. Parameter Tuning Guidance

| Parameter | Increase To | Decrease To | Effect |
|-----------|-------------|-------------|--------|
| impact_weight | Magnify quantified achievements | Reduce achievement influence | Scales impact contribution ceiling |
| mandatory_strength_factor | Prioritize required skill coverage | Balance optional skills | Multiplicative boost on base score |
| impact_min_relevance | Suppress generic achievements | Allow more impact events | Gate by mandatory skill linkage |
| semantic_relevance_threshold | Tighten semantic matches | Recover borderline matches | Applies only if no lexical/alias match |

Start with: impact_weight=0.08, mandatory_strength_factor=0.15, impact_min_relevance=0.0–0.1, semantic_relevance_threshold=0.65.

## 5. Semantic Relevance Fallback Logic

1. Attempt lexical word-boundary match between mandatory skills and impact sentence.
2. Attempt alias match (from taxonomy synonyms).
3. If no match: embed sentence and skill; compute cosine similarity.
4. Count sentence if similarity ≥ threshold AND sentence length above minimal heuristic (avoid short generic fragments).

Why fallback only on absence of lexical/alias matches? Prevent double counting and keep semantic recall targeted.

## 6. Anti-Patterns & Pitfalls

| Pitfall | Symptom | Remedy |
|---------|---------|--------|
| Thresholds too low | Many irrelevant impact sentences counted | Raise semantic_relevance_threshold (→ 0.68–0.70) |
| Mandatory factor too high | Homogeneous high scores for narrow profiles | Reduce mandatory_strength_factor (≤0.20) |
| Impact overweight | Candidates with flashy metrics outrank skill-fit | Lower impact_weight (≤0.05) |
| Sparse labels | Volatile precision estimates | Add more borderline examples |
| Ignoring negative shifts | Regression in strong candidates | Track pct_regressed; investigate causes |

## 7. Expansion Roadmap (Planned)

Future scoring dimensions (not yet implemented):
- Career progression trajectory
- Title normalization & seniority inference
- Tenure & stability scoring
- Semantic skill graph clustering
- Contextual weighting (role vs domain skills)
- Transferable skill mapping

Document each new dimension with: definition, extraction logic, calibration strategy, integration formula, interpretability fields.

## 8. Reporting & Versioning

Maintain dated JSON evaluation reports (e.g., `eval_reports/2025-11-12-impact-semantic.json`). Include:
- parameter snapshot
- metrics
- top-k listing per JD
- differences vs previous run

## 9. Recommended Directory Layout

```
/ eval_reports          # Stored evaluation JSON outputs
/ scripts/evaluate_scoring.py
/ docs/EVALUATION.md    # This file
```

## 10. Example Invocation Snippet (Pseudo-Code)

```python
from evaluation import precision_at_k, reciprocal_rank

results = rank_candidates(jd, candidate_scores)  # your existing logic
relevant_set = {"cv_a", "cv_c"}
precision5 = precision_at_k(results, relevant_set, k=5)
rr = reciprocal_rank(results, relevant_set)
print({"precision@5": precision5, "RR": rr})
```

## 11. Glossary

| Term | Definition |
|------|------------|
| Mandatory Coverage | Fraction of required JD skills matched by CV |
| Impact Event | Sentence/phrase containing verb + metric + outcome |
| Relevance Ratio | Impact sentences referencing mandatory skills / total impact sentences |
| Baseline Score | Score before impact component applied |
| Lift | Change between baseline and final score |

---
If you extend metrics, update this document and link new sections from the README.
