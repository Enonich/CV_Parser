# 🚀 Quick Start Guide - CV Parser

## Prerequisites

- Python 3.8+
- MongoDB running locally or remotely
- Ollama (optional, for certain features)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd CV_Parser
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   
   Create a `.env` file in the root directory:
   ```env
   MONGODB_URI=mongodb://localhost:27017/
   JWT_SECRET_KEY=your-secret-key-here
   ```

5. **Update config.yaml**
   
   Edit `config.yaml` to match your setup:
   - MongoDB connection strings
   - ChromaDB paths
   - Model settings

## Running the Application

### Start the server
```bash
python main.py
```

The application will be available at:
- **Web Interface**: http://localhost:8000/static/login.html
- **API Docs**: http://localhost:8000/docs

### Default Login
First time? Create an admin account:
```bash
python scripts/migrate_admin.py
```

## Using the Application

### For Users
1. Navigate to http://localhost:8000/static/login.html
2. Login with your credentials
3. Upload CVs and Job Descriptions
4. Search and score candidates

### For Admins
1. Login as admin
2. Access admin dashboard
3. Manage users and companies
4. View analytics

## Project Structure

```
CV_Parser/
├── main.py              # Start here!
├── config.yaml          # Configuration
├── requirements.txt     # Dependencies
├── backend/            # Python backend
├── static/             # Frontend (HTML/CSS/JS)
├── data/               # Databases and files
├── notebooks/          # Jupyter experiments
├── scripts/            # Utility scripts
└── docs/               # Documentation
```

## Common Commands

**Run application:**
```bash
python main.py
```

**Check admin user:**
```bash
python scripts/check_admin.py
```

**Test environment:**
```bash
python scripts/test_env.py
```

## Troubleshooting

### Port already in use
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <process_id> /F

# Linux/Mac
lsof -ti:8000 | xargs kill -9
```

### Import errors
Make sure you're in the project root and virtual environment is activated.

### Database connection issues
Check MongoDB is running and MONGODB_URI in .env is correct.

## Need Help?

- 📖 Full documentation: `docs/PROJECT_STRUCTURE.md`
- 🐛 Bug fixes: `docs/BUG_FIXES.md`
- 👤 Admin features: `docs/ADMIN_FEATURES.md`

## Development

**Add new feature:**
1. Create module in appropriate `backend/` subfolder
2. Add endpoint in `backend/api/workflow.py`
3. Update frontend in `static/`

**Run in development mode:**
```bash
uvicorn backend.api.workflow:app --reload --host 0.0.0.0 --port 8000
```

---

Ready to parse some CVs! 🎉
