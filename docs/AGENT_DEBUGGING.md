# Agent Debugging Guide

## Error: "Failed to initialize assistant" / "Internal Server Error"

This error occurs when the agent session creation fails. Here's how to debug it:

### 1. Check Server Logs

Look at your terminal where `uvicorn` is running. You should see detailed error messages like:

```
ERROR - Error creating agent session: <detailed error message>
INFO - Creating context for CV: <cv_id>, JD: <jd_id>
INFO - CV data loaded successfully
INFO - JD data loaded successfully
INFO - Initializing agent with config
INFO - Initializing LLM: llama3.2:latest at http://localhost:11434
INFO - Initializing embeddings: mxbai-embed-large
INFO - Building context document
INFO - Setting up vector store
INFO - Setting up QA chain
INFO - Agent initialization complete
```

### 2. Common Issues and Fixes

#### Issue: "CV not found" or "JD not found"
**Cause**: The CV ID or JD ID doesn't exist in the database

**Fix**:
1. Make sure you've uploaded CVs and a JD
2. Run a search first to get valid cv_id
3. Check that company_name and job_title match exactly

#### Issue: "Failed to connect to Ollama"
**Cause**: Ollama is not running or wrong URL

**Fix**:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve

# Verify models are available
ollama list
```

#### Issue: "ChromaDB connection error"
**Cause**: ChromaDB directory doesn't exist or permissions issue

**Fix**:
```bash
# Check if chroma_db directory exists
ls chroma_db/

# If not, it will be created automatically
# But make sure the application has write permissions
```

#### Issue: "Embedding model not found"
**Cause**: Embedding model not pulled in Ollama

**Fix**:
```bash
ollama pull mxbai-embed-large
```

#### Issue: "LLM model not found"
**Cause**: LLM model not pulled in Ollama

**Fix**:
```bash
ollama pull llama3.2:latest
```

### 3. Step-by-Step Test

#### Step 1: Verify Prerequisites
```bash
# Test Ollama
curl http://localhost:11434/api/tags

# Test MongoDB
python -c "from pymongo import MongoClient; c = MongoClient('mongodb://localhost:27017/'); print(c.list_database_names())"

# Test imports
python -c "from backend.core.agent import CVExplainabilityAgent; print('OK')"
```

#### Step 2: Check Data Exists
1. Log in to the application
2. Upload a JD for a specific company/job
3. Upload some CVs
4. Run a search with "Show Detailed Info" enabled
5. Verify results appear

#### Step 3: Get Valid IDs from Search
When you run a search, the response includes:
```json
{
  "results": [
    {
      "cv_id": "actual_cv_id_here",
      "name": "Candidate Name",
      "combined_score": 0.85,
      ...
    }
  ],
  "jd_id_used": "actual_jd_id_here"
}
```

Use these IDs in the agent request.

#### Step 4: Test Agent Endpoint Manually

Using browser dev tools or curl:

```bash
# First, get auth token by logging in
# Then use it in the request

curl -X POST http://localhost:8000/agent/session \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "cv_id": "YOUR_CV_ID",
    "jd_id": "YOUR_JD_ID",
    "company_name": "YOUR_COMPANY",
    "job_title": "YOUR_JOB_TITLE",
    "scoring_result": {}
  }'
```

### 4. Browser Console Debugging

Open browser dev tools (F12) and check:

#### Console Tab
Look for error messages:
```
[Agent] Opening chat for CV: ...
[Agent] Error creating session: ...
```

#### Network Tab
1. Find the `/agent/session` request
2. Check the **Request** tab to see what was sent
3. Check the **Response** tab to see the error details
4. Check the **Status Code** (should be 200 if successful)

### 5. Quick Fixes

#### Fix 1: Restart Everything
```bash
# Stop the server (Ctrl+C)
# Restart Ollama
ollama serve

# Restart the application
python main.py
```

#### Fix 2: Clear and Reinstall
```bash
# Reinstall dependencies
pip install --upgrade langchain langchain-ollama langchain-chroma

# Restart server
python main.py
```

#### Fix 3: Check Config
Verify `config.yaml` has:
```yaml
llm_model: "llama3.2:latest"
ollama_url: "http://localhost:11434"

embedding:
  model: "mxbai-embed-large"

chroma:
  cv_persist_dir: "./chroma_db"
  cv_collection_name: "cv_sections"
```

### 6. Detailed Error Messages

The server logs will show which step failed:

```
INFO - Creating context for CV: abc123, JD: xyz789
✅ This means the endpoint received the request

INFO - CV data loaded successfully
✅ MongoDB has the CV

INFO - JD data loaded successfully  
✅ MongoDB has the JD

INFO - Initializing LLM: llama3.2:latest at http://localhost:11434
❌ If it fails here: Ollama connection issue

INFO - Initializing embeddings: mxbai-embed-large
❌ If it fails here: Embedding model issue

INFO - Building context document
❌ If it fails here: Data formatting issue

INFO - Setting up vector store
❌ If it fails here: ChromaDB issue

INFO - Setting up QA chain
❌ If it fails here: LangChain configuration issue

INFO - Agent initialization complete
✅ Success!
```

### 7. Test with Minimal Data

Try creating a session right after a successful search:

1. Upload JD
2. Upload 1 CV
3. Run search
4. Immediately click "Ask Agent" on the result
5. Check browser console and server logs

### 8. Still Not Working?

If none of the above helps, gather this information:

1. **Server logs** (full error trace)
2. **Browser console** (all messages)
3. **Request payload** (from Network tab)
4. **Ollama status**: `ollama list`
5. **MongoDB status**: `mongo --eval "db.version()"`
6. **Python version**: `python --version`
7. **Installed packages**: `pip list | grep langchain`

Then you can:
- Check the detailed logs for the specific error
- Search for the error message online
- File an issue with the information above

### 9. Success Indicators

When everything works, you'll see:

**Server Logs:**
```
INFO - Created agent session abc-123-def for cv_id / jd_id
```

**Browser Console:**
```
[Agent] Opening chat for CV: cv_id
[Agent] Session created: abc-123-def
```

**UI:**
- Modal opens with welcome message
- Suggested questions appear
- Input field is active
- You can type and send messages

### 10. Common Success Workflow

```
1. Login ✅
2. Upload JD ✅
3. Upload CVs ✅
4. Search (with details=true) ✅
5. Click "Ask Agent" ✅
6. Modal opens ✅
7. Welcome message shows ✅
8. Ask question ✅
9. Get answer ✅
10. Close modal ✅
```

---

**Pro Tip**: Keep the browser dev tools open and watch both the Console and Network tabs while testing. This gives you real-time feedback on what's happening.
