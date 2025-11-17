# CV Parser & Scoring Web Application

A modern web application for uploading CVs and job descriptions, then getting intelligent matching scores between them.

## Features

- **Drag & Drop File Upload**: Easy file uploading with visual feedback
- **Multiple File Format Support**: 
  - CVs: PDF, DOCX, PNG, JPG, JPEG
  - Job Descriptions: TXT, PDF, DOCX
- **Hybrid Scoring Engine**: Vector similarity + BM25 + cross-encoder + calibrated skill & impact signals
- **Skill-Aware Ranking**: Mandatory vs optional skills with gating + bonus weighting
- **Impact-Aware Ranking**: Quantified achievement (verb + metric + outcome) extraction with relevance filtering to required skills
- **Interpretability**: Per-candidate `score_components`, skill coverage, depth, recency, impact events (details mode)
- **Real-time Scoring**: Efficient multi-stage retrieval and fusion
- **Modern UI**: Responsive design with Bootstrap 5
- **Email Display**: Shows original email addresses instead of hashed IDs

## Quick Start

### Prerequisites

Make sure you have the following installed:
- Python 3.8+
- Required Python packages (see requirements.txt or install individually)

### Installation

1. **Install Dependencies**:
   ```bash
   pip install fastapi uvicorn python-multipart pyyaml
   # Add other dependencies as needed for your specific modules
   ```

2. **Configure the Application**:
   - Ensure `config.yaml` is properly configured with your settings
   - Make sure MongoDB is running (if using MongoDB features)
   - Ensure Ollama is running with the embedding model

3. **Start the Application**:
   ```bash
   python run_webapp.py
       OR
   uvicorn workflow:app --host 0.0.0.0 --port 8000
   ```

4. **Access the Web Interface**:
   - Open your browser and go to: http://localhost:8000
   - API documentation: http://localhost:8000/docs

## How to Use

### Step 1: Upload Files
1. **Upload a Job Description**: Drag and drop or click to upload a job description file (TXT, PDF, or DOCX)
2. **Upload CVs**: Upload one or more CV files (PDF, DOCX, PNG, JPG, or JPEG)

### Step 2: Configure Search
- Set the number of top CVs to return (default: 5)
- Choose whether to show detailed matching information
- Click "Search & Score CVs"

### Step 3: View Results
- Results are displayed with overall scores and section-wise breakdowns
- Each CV shows its email address (original identifier)
- Color-coded scoring: Excellent (green), Good (blue), Fair (yellow), Poor (red)

## API Endpoints

### Web Interface
- `GET /` - Main web application interface
- `GET /static/*` - Static files (CSS, JS, images)

### File Upload
- `POST /upload-cv/` - Upload and process CV files
- `POST /upload-jd/` - Upload and process job description files

### Search & Scoring
- `POST /search-cvs/` - Search and score CVs against job description (returns hybrid + skill + impact enriched ranking)

### Health Check
- `GET /health` - API health status

## Configuration

The application uses `config.yaml` for configuration. Key sections:

```yaml
# MongoDB Configuration
mongodb:
  connection_string: "mongodb://localhost:27017/"
  cv_db_name: "CV"
  cv_collection_name: "CV_Data"
  jd_db_name: "JobDescriptions"
  jd_collection_name: "JD_Data"

# Embedding Configuration
embedding:
  model: "mxbai-embed-large"

# Chroma Vector Store Configuration
chroma:
  cv_persist_dir: "./chroma_db"
  jd_persist_dir: "./jd_chroma_db"
  cv_collection_name: "cv_sections"
  jd_collection_name: "job_descriptions"

# Search Configuration (extended)
search:
  top_k_per_section: 5
  top_k_cvs: 5
  impact_weight: 0.08                 # Max contribution of calibrated impact score (scaled by relevance)
  mandatory_strength_factor: 0.15     # Multiplicative boost: base_score * (1 + mandatory_coverage * factor)
  impact_min_relevance: 0.0           # Minimum fraction of impact events referencing mandatory skills before any impact weight applies
  semantic_skill_relevance: true      # Enable lexical + alias + semantic embedding fallback relevance for impact events
  semantic_relevance_threshold: 0.65  # Cosine similarity threshold for embedding fallback (only if no lexical/alias match)
```

## File Structure

```
├── static/
│   ├── index.html          # Main web interface
│   ├── styles.css          # Custom styling
│   ├── script.js           # Frontend JavaScript
│   ├── cvs/                # Uploaded CV files (temporary)
│   ├── jds/                # Uploaded JD files (temporary)
│   └── extracted_files/    # Processed JSON files
├── workflow.py             # FastAPI application
├── run_webapp.py          # Startup script
├── config.yaml            # Configuration file
└── WEBAPP_README.md       # This file
```

## Troubleshooting
### Impact & Skill Scoring FAQs

1. **Why did a candidate with big achievements rank lower?** Their impact events may not reference mandatory job skills (relevance ratio low → impact component suppressed).
2. **Why is impact_component zero?** Either fewer than 2 impact events detected, relevance below `impact_min_relevance`, or `impact_weight` set to 0.
3. **How to emphasize required skills more?** Raise `mandatory_strength_factor` (e.g., 0.25). Keep it modest to avoid drowning other signals.
4. **How is impact relevance computed?** Fraction of impact sentences containing at least one mandatory skill token (case-insensitive word-boundary match).
5. **What is `combined_score_pre_impact`?** Snapshot after skill bonuses and mandatory strength boost, before adding impact contribution (used for evaluation deltas).
6. **How are semantic skill matches applied?** If an impact sentence has no direct lexical or alias match to a mandatory skill, we embed the sentence and the skill terms and apply a cosine similarity threshold (`semantic_relevance_threshold`). Only sentences above the threshold and not "too short" (to avoid generic phrases) count. This improves recall without inflating weak matches.

### Tuning Workflow

| Objective | Recommended Adjustments |
|-----------|-------------------------|
| Reduce noise from spurious metrics | Increase `impact_min_relevance` to 0.2–0.3 |
| Emphasize required skills strongly | Increase `mandatory_strength_factor` up to 0.25 |
| De-emphasize achievements overall | Lower `impact_weight` (e.g., 0.04) |
| Inspect relevance issues | Enable `show_details` and review `impact_relevance_skills` |
| Improve semantic skill recovery in impact sentences | Set `semantic_skill_relevance: true` and threshold 0.63–0.67 |
| Be more conservative with semantic matches | Raise `semantic_relevance_threshold` toward 0.70 |

**Threshold Notes**
- Start with `semantic_relevance_threshold: 0.65` (balanced precision/recall)
- Raise threshold if unrelated sentences are counted
- Lower (to ~0.62) only if many true skill-linked impact sentences are missed
- Keep `impact_min_relevance` at 0.0–0.15 initially; increase only if generic achievements dominate

### Evaluation
You can quantify scoring improvements using the provided evaluation harness.
See full methodology in [`docs/EVALUATION.md`](./docs/EVALUATION.md).

**Key Metrics**
- `precision_at_k`: How many of the top-k retrieved CVs are known relevant
- `reciprocal_rank`: Position of the first relevant CV (higher is better)
- `spearman_rank_corr`: Correlation between previous and new ranking (measures stability or intentional shift)
- `lift_stats`: Aggregate improvement: average delta, % improved, % unchanged, % regressed

**Workflow**
1. Label a small set of CVs as relevant/non-relevant for at least one JD (store labels or keep a mapping file)
2. Run scoring with current parameters (capture `combined_score_pre_impact` & `combined_score`)
3. Execute the evaluation script to produce a JSON report
4. Inspect lift stats and metric changes; adjust thresholds (`impact_min_relevance`, `semantic_relevance_threshold`, `mandatory_strength_factor`) accordingly

**Interpreting Results**
- Large positive lift but low precision@k → Impact may be overweighting non-relevant achievements
- High precision@k but negative lift for most → Mandatory skill weighting might be too aggressive (inflate certain profiles)
- Low Spearman + improved precision → Acceptable if the goal was to reprioritize genuinely stronger candidates

**Recommended Iteration**
- Tune one parameter at a time until precision@k plateaus
- Re-run after each change; keep prior JSON reports for diffing

**Next Extensions (Optional)**
- Add recall@k once you have fuller relevance labels
- Track calibration percentiles for impact score before/after semantic relevance to ensure distribution stability

### Labeled Dataset Example
Create a lightweight ground-truth file to evaluate ranking quality. Two common formats:

**JSONL (job-centric)**
```json
{"jd_id": "jd_123", "relevant_cv_ids": ["cv_a", "cv_c"], "non_relevant_cv_ids": ["cv_b"]}
{"jd_id": "jd_456", "relevant_cv_ids": ["cv_d"], "non_relevant_cv_ids": []}
```

**CSV (pairwise)**
```csv
jd_id,cv_id,label
jd_123,cv_a,1
jd_123,cv_b,0
jd_123,cv_c,1
jd_456,cv_d,1
```

Load either form in the evaluation script and map labels to sets. For sparse labels, focus on precision@k; for denser labeling add recall@k.

For full methodology and formulas see `docs/EVALUATION.md`.


### Common Issues

1. **"Module not found" errors**: Install missing dependencies
2. **File upload fails**: Check file format and size limits
3. **No results returned**: Ensure both CV and JD files are uploaded
4. **Embedding errors**: Check if Ollama is running with the correct model

### Logs

The application logs important events. Check the console output for:
- File upload status
- Processing errors
- Search results

### Performance Tips

- Use smaller files for faster processing
- Limit the number of CVs returned if you have many uploaded
- Ensure adequate system resources for embedding generation

## Development

### Adding New Features

1. **Backend**: Modify `workflow.py` to add new API endpoints
2. **Frontend**: Update `static/script.js` for new functionality
3. **Styling**: Modify `static/styles.css` for UI changes

### Testing

- Use the built-in FastAPI docs at `/docs` to test API endpoints
- Test file uploads with different formats
- Verify scoring accuracy with known CV-JD matches

## Security Notes

- The application currently runs without authentication
- File uploads are temporarily stored and cleaned up
- Consider adding authentication for production use
- Validate all file uploads for security

## Support

For issues or questions:
1. Check the console logs for error messages
2. Verify all dependencies are installed
3. Ensure configuration files are properly set up
4. Test individual components (MongoDB, Ollama, etc.) separately
