# CV Parser - Project Structure

## 📁 Directory Organization

```
CV_Parser/
├── backend/                    # Backend application code
│   ├── api/                   # FastAPI endpoints and routing
│   │   ├── workflow.py       # Main API endpoints
│   │   └── run_webapp.py     # Application startup script
│   ├── core/                  # Core business logic
│   │   ├── auth.py           # Authentication & authorization
│   │   ├── users_db.py       # User management
│   │   ├── reranker.py       # CV reranking logic
│   │   ├── score_cv.py       # Scoring algorithms
│   │   ├── fetch_top_k.py    # Vector search retrieval
│   │   ├── identifiers.py    # Naming and ID utilities
│   │   └── ollama_bge_reranker.py
│   ├── database/              # Database connections
│   │   ├── mongodb.py        # MongoDB for CVs
│   │   └── mongodb_jd.py     # MongoDB for Job Descriptions
│   ├── extractors/            # Text extraction modules
│   │   ├── cv_extractor.py   # CV text extraction
│   │   ├── jd_extractor.py   # JD text extraction
│   │   ├── extraction.py     # Generic extraction
│   │   ├── docstrange_extractor.py
│   │   ├── llama_extractor.py
│   │   ├── resume_parser.py
│   │   └── prof_years_extractor.py
│   └── embedders/             # Vector embedding generation
│       ├── cv_chroma_embedder.py
│       └── jd_embedder.py
├── static/                     # Frontend files (HTML, CSS, JS)
│   ├── index.html            # User interface
│   ├── admin.html            # Admin interface
│   ├── login.html            # Login page
│   ├── app.js                # User dashboard logic
│   ├── admin.js              # Admin dashboard logic
│   ├── login.js              # Authentication logic
│   ├── styles.css            # Styling
│   ├── cvs/                  # Uploaded CV files
│   ├── jds/                  # Uploaded JD files
│   └── extracted_files/      # Processed outputs
├── data/                       # Data files and databases
│   ├── chroma_db/            # ChromaDB vector stores
│   ├── chroma_db_cv/
│   ├── chroma_db_jd/
│   ├── jd_chroma_db/
│   ├── CVs/                  # CV storage
│   ├── extracted_files/      # Extracted data
│   └── *.txt, *.json, *.docx # Sample data files
├── notebooks/                  # Jupyter notebooks
│   ├── CV_Parsing.ipynb
│   ├── docstrange_extractor.ipynb
│   ├── extractor.ipynb
│   ├── professional_exp_calc.ipynb
│   ├── reranker.ipynb
│   └── test.ipynb
├── scripts/                    # Utility scripts
│   ├── check_admin.py        # Admin verification
│   ├── check_collections.py  # Database checks
│   ├── migrate_admin.py      # Migration scripts
│   ├── test_env.py          # Environment testing
│   └── test_flagembedder.py
├── docs/                       # Documentation
│   ├── README.md             # Main documentation
│   ├── PROJECT_STRUCTURE.md  # This file
│   ├── BUG_FIXES.md
│   ├── ADMIN_FEATURES.md
│   ├── ADMIN_PAGE_COMPLETE.md
│   ├── ADMIN_VS_USER_DASHBOARD.md
│   └── USER_INTERFACE_CHANGES.md
├── main.py                     # Main entry point
├── config.yaml                 # Configuration file
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables
└── .gitignore

```

## 🚀 Running the Application

### Option 1: Using main.py (Recommended)
```bash
python main.py
```

### Option 2: Using the backend script
```bash
python backend/api/run_webapp.py
```

### Option 3: Direct uvicorn
```bash
uvicorn backend.api.workflow:app --reload --host 0.0.0.0 --port 8000
```

## 📦 Module Organization

### Backend Structure

**API Layer** (`backend/api/`)
- Handles HTTP requests/responses
- Defines FastAPI routes
- Manages file uploads

**Core Layer** (`backend/core/`)
- Authentication & authorization
- Scoring and ranking algorithms
- Business logic utilities

**Database Layer** (`backend/database/`)
- MongoDB connections
- Data persistence
- CRUD operations

**Extractors** (`backend/extractors/`)
- PDF/DOCX text extraction
- Structured data parsing
- Content preprocessing

**Embedders** (`backend/embedders/`)
- Vector embedding generation
- ChromaDB integration
- Semantic search preparation

### Frontend Structure

**Static Files** (`static/`)
- Pure HTML/CSS/JavaScript
- No build process required
- Tailwind CSS via CDN

## 🔧 Configuration

All configuration is centralized in `config.yaml`:
- Database connection strings
- Model settings
- Vector search parameters
- Reranking options

## 📊 Data Flow

1. **Upload** → Files saved to `static/cvs/` or `static/jds/`
2. **Extract** → Text extracted by `extractors/`
3. **Embed** → Vectors generated by `embedders/`
4. **Store** → Data saved to MongoDB + ChromaDB in `data/`
5. **Search** → Vector search via `fetch_top_k.py`
6. **Rerank** → Cross-encoder reranking via `reranker.py`
7. **Display** → Results shown in frontend

## 🛠️ Development

- **Add new endpoint**: Edit `backend/api/workflow.py`
- **Add new extractor**: Create in `backend/extractors/`
- **Modify UI**: Edit files in `static/`
- **Run tests**: Use scripts in `scripts/`
- **Experiment**: Use notebooks in `notebooks/`

## 📝 Notes

- All Python modules are properly packaged with `__init__.py`
- Import statements use `backend.module.file` format
- Paths are relative to project root
- Configuration loaded from root `config.yaml`
