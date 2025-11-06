# CV Parser & Scoring Web Application

A modern web application for uploading CVs and job descriptions, then getting intelligent matching scores between them.

## Features

- **Drag & Drop File Upload**: Easy file uploading with visual feedback
- **Multiple File Format Support**: 
  - CVs: PDF, DOCX, PNG, JPG, JPEG
  - Job Descriptions: TXT, PDF, DOCX
- **Real-time Scoring**: Advanced vector similarity matching
- **Detailed Results**: Section-wise scoring with visual progress bars
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
- `POST /search-cvs/` - Search and score CVs against job description

#### Per-Request Reranking
Add a `rerank` boolean to the request body to override global configuration:

Example body:
```json
{
  "top_k_cvs": 5,
  "show_details": true,
  "rerank": true
}
```

Behavior:
* If `rerank` is provided it takes precedence over `search.rerank_enabled` in `config.yaml`.
* If `rerank` is `true` but global reranking is disabled, the cross-encoder reranker is lazily initialized.
* Response now includes a top-level `reranked` flag.
* Each result contains:
  - `vector_score`: base weighted similarity
  - `cross_encoder_score`: pair semantic score (only if reranked & model available)
  - `coverage_score`: heuristic coverage of JD sections matched
  - `final_score`: fused score when reranked, otherwise equals `vector_score`

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

# Search Configuration
search:
  top_k_per_section: 5
  top_k_cvs: 5
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
