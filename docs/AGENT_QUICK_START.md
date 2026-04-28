# Quick Start: Using the HR Explainability Agent

## Prerequisites

1. **Ollama installed and running**
   ```powershell
   # Check if Ollama is running
   ollama list
   
   # If not installed, download from: https://ollama.ai
   # Then pull the required model
   ollama pull llama3.2:latest
   ollama pull mxbai-embed-large
   ```

2. **MongoDB running**
   ```powershell
   # Check if MongoDB is running (should be on port 27017)
   ```

3. **Dependencies installed**
   ```powershell
   conda activate my_env
   pip install -r requirements.txt
   ```

## Step-by-Step Usage

### 1. Start the Application

```powershell
# Navigate to project directory
cd C:\Users\Enoch\Documents\GitHub\LLM\CV_Parser

# Activate your conda environment
conda activate my_env

# Start the server
python main.py
```

The server will start on `http://localhost:8000`

### 2. Login

Open your browser and go to: `http://localhost:8000/static/login.html`

Login with your credentials.

### 3. Upload Job Description

1. Click **"Upload JD"** tab
2. Select your company from dropdown (or it's auto-selected for regular users)
3. Drag & drop or click to upload a job description file (TXT, PDF, or DOCX)
4. Wait for processing confirmation

### 4. Upload CVs

1. Click **"Upload CV"** tab
2. Select the same company and job title
3. Upload one or multiple CV files (PDF, DOCX, PNG, JPG, JPEG)
4. Wait for processing confirmation

### 5. Search & Score CVs

1. Click **"Search CVs"** tab
2. Select company and job title
3. Set number of results (default: 10)
4. Enable "Show Detailed Info" for full agent context
5. Click **"Search & Score CVs"**
6. Results will appear with scores and breakdowns

### 6. Ask the Agent

For each CV result:

1. Click the **"Ask Agent"** button (purple, with robot icon)
2. The agent chat modal will open
3. You'll see:
   - Welcome message with candidate summary
   - Overall match score and skill coverage
   - Suggested questions as clickable chips

4. **Try suggested questions** by clicking them, or type your own:
   - "Why did this candidate score highly?"
   - "What skills are they missing?"
   - "Tell me about their achievements"
   - "How does their experience align?"

5. The agent will respond with detailed, contextual answers

6. Continue asking follow-up questions

7. Close the modal when done (session automatically cleaned up)

## Example Conversation

```
You: Why did this candidate score 0.85?

Agent: This candidate scored 0.85 due to strong performance across 
multiple dimensions:

1. Semantic Similarity (0.42): Their CV shows excellent alignment 
   with the job description's technical requirements
   
2. Skill Coverage (90%): They possess 9 out of 10 mandatory skills,
   only missing "Kubernetes"
   
3. Impact Score (0.18): They have 5 quantified achievements including
   "Reduced deployment time by 40%" and "Scaled system to 10M users"
   
4. Cross-encoder Score (0.88): Deep semantic analysis confirms 
   strong match between their experience and role requirements

Their strongest areas are Python development, AWS architecture, and
team leadership.

---

You: What skills are they missing?

Agent: Based on the mandatory skills analysis, this candidate is 
missing:

1. **Kubernetes** - Required for container orchestration
   However, they do have Docker experience which is related
   
They have strong coverage of all other required skills including:
- Python (5+ years)
- AWS (expert level)
- React (3 years)
- PostgreSQL (advanced)

The missing Kubernetes skill could be addressed through training
or certification. Their Docker experience suggests they could
quickly pick up Kubernetes.

---

You: Tell me about their impact achievements

Agent: This candidate has 5 quantified impact achievements:

**Top 3 Most Relevant:**

1. "Reduced deployment time by 40% through CI/CD automation"
   - Impact Score: 0.85
   - Metrics: 40% improvement
   - Relevant to: DevOps, Automation skills

2. "Scaled backend system to handle 10M concurrent users"
   - Impact Score: 0.92
   - Metrics: 10M users
   - Relevant to: System Architecture, Scalability

3. "Led team of 8 developers, increased velocity by 25%"
   - Impact Score: 0.78
   - Metrics: 8 team members, 25% improvement
   - Relevant to: Leadership, Team Management

These achievements demonstrate strong technical execution and
measurable business impact, particularly in scalability and
process improvement.
```

## Tips for Best Results

### 1. Enable Detailed Info
Always check "Show Detailed Info" when searching - this provides the agent with:
- Full skill coverage details
- Impact event extraction
- Section-wise breakdowns
- All score components

### 2. Ask Specific Questions
Better: "What experience do they have with AWS?"
Not: "Tell me everything"

### 3. Use Follow-up Questions
The agent remembers context within the session:
- "What about their Python skills?"
- "And their education?"
- "Compare that to the requirements"

### 4. Try Suggested Questions First
The agent generates context-aware suggestions based on:
- Overall score (high/low)
- Missing skills
- Impact achievements present
- Coverage gaps

### 5. Close Sessions When Done
Click the X to close the modal - this frees up resources.

## Troubleshooting

### "Failed to initialize assistant"

**Cause:** Ollama not running or model not available

**Fix:**
```powershell
# Check Ollama
ollama list

# Pull model if missing
ollama pull llama3.2:latest

# Restart Ollama if needed
```

### "Session not found"

**Cause:** Session expired or server restarted

**Fix:** Close modal and click "Ask Agent" again to create new session

### Slow Responses

**Normal:** 3-5 seconds per answer with local Ollama

**If slower:**
- Check CPU usage (Ollama is CPU-intensive)
- Try smaller model: `ollama pull llama3.2:1b`
- Update `config.yaml`: `llm_model: "llama3.2:1b"`

### Agent Gives Generic Answers

**Cause:** Missing detailed scoring data

**Fix:** 
- Enable "Show Detailed Info" in search
- Ensure CVs and JD were fully processed
- Check MongoDB for complete data

## Advanced Usage

### Custom Questions by Role

**For Technical Roles:**
- "Evaluate their proficiency in [specific technology]"
- "Do they have experience with microservices?"
- "What's their testing/CI-CD background?"

**For Leadership Roles:**
- "What team management experience do they have?"
- "Tell me about their leadership achievements"
- "How large were the teams they've led?"

**For All Roles:**
- "What are the candidate's top 3 strengths?"
- "What concerns should I have about this candidate?"
- "How does their career progression look?"

### Comparing Multiple Candidates

Open agent for each candidate in separate tabs/windows and ask:
- Same question to each
- Compare their answers manually
- Note: Multi-candidate comparison mode coming soon!

## Next Steps

- Read full documentation: `docs/AGENT_INTEGRATION.md`
- Explore voice agent: `voice_agent/run_agent.py`
- Check admin features: `docs/ADMIN_FEATURES.md`

## Support

If you encounter issues:
1. Check logs in the terminal where you ran `python main.py`
2. Verify all prerequisites are running
3. Try the troubleshooting steps above
4. Check the detailed documentation

Happy recruiting! 🚀
