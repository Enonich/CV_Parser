# HR Explainability Agent Integration

## Overview

The HR Explainability Agent is an AI-powered assistant that helps HR recruiters understand CV scoring decisions through natural conversation. The agent has comprehensive access to:

- **Complete CV data** - Skills, experience, education, projects, achievements
- **Job description requirements** - Required/preferred skills, qualifications, responsibilities
- **Detailed scoring breakdown** - Vector similarity, BM25, cross-encoder, skill coverage, impact scores
- **Historical context** - Vector database with semantic search capabilities

## Features

### 🤖 Intelligent Question Answering
Ask natural language questions about candidates:
- "Why did this candidate score highly?"
- "What skills are they missing?"
- "Tell me about their quantified achievements"
- "How does their experience align with the role?"
- "What are their strongest qualifications?"

### 📊 Context-Aware Responses
The agent understands:
- Mandatory vs optional skill coverage
- Impact event relevance to job requirements
- Skill depth and recency indicators
- Section-wise performance breakdown
- Cross-encoder reranking adjustments

### 💬 Interactive Chat Interface
- Beautiful modal-based chat UI
- Suggested questions based on scoring context
- Real-time streaming responses
- Source attribution for transparency
- Session management for resource efficiency

## Architecture

### Backend Components

#### 1. `backend/core/agent.py`
Core agent logic with two main classes:

**CVScoringContext:**
- Loads CV and JD data from MongoDB
- Formats scoring results into readable context
- Builds comprehensive context documents for RAG
- Provides summary and metadata extraction

**CVExplainabilityAgent:**
- Initializes LangChain RAG pipeline
- Connects to ChromaDB for semantic retrieval
- Uses Ollama LLM for response generation
- Manages QA chain with custom prompts
- Generates context-aware suggested questions

#### 2. `backend/api/workflow.py` - Agent Endpoints

**POST /agent/session**
- Creates new agent session
- Initializes RAG pipeline with CV + JD + scoring data
- Returns session ID and suggested questions
- Request body:
```json
{
  "cv_id": "candidate_cv_id",
  "jd_id": "job_description_id",
  "company_name": "company",
  "job_title": "job_title",
  "scoring_result": {...}
}
```

**POST /agent/ask**
- Asks question in existing session
- Performs RAG retrieval and LLM generation
- Returns answer with source attribution
- Request body:
```json
{
  "session_id": "uuid",
  "question": "Why did this candidate score highly?"
}
```

**DELETE /agent/session/{session_id}**
- Closes agent session
- Frees up memory resources

**GET /agent/sessions** (Admin only)
- Lists all active agent sessions
- Useful for monitoring and debugging

### Frontend Components

#### 1. `static/index.html` - Agent Modal
Beautiful chat interface with:
- Gradient header with robot icon
- Scrollable message history
- Suggested question chips
- Input field with send button
- Responsive design

#### 2. `static/app.js` - Agent Logic
Functions:
- `openAgentChat(cvId, scoringResult)` - Opens modal and creates session
- Agent question form submission handler
- Event delegation for "Ask Agent" buttons
- Session cleanup on modal close

#### 3. `static/styles.css` - Agent Styling
- Smooth scroll behavior
- Custom scrollbar styling
- Slide-in message animations
- Hover effects for suggestions

## Usage Flow

### 1. Search and Score CVs
```
User → Upload JD → Upload CVs → Search & Score
```

### 2. Open Agent Chat
```
Click "Ask Agent" button on any CV result card
↓
Frontend creates agent session via /agent/session
↓
Backend initializes RAG pipeline with full context
↓
Modal opens with welcome message and suggestions
```

### 3. Ask Questions
```
User types question or clicks suggestion
↓
Frontend sends question via /agent/ask
↓
Backend performs RAG retrieval + LLM generation
↓
Answer appears in chat with sources
```

### 4. Close Session
```
User closes modal
↓
Frontend deletes session via /agent/session/{id}
↓
Backend frees resources
```

## Configuration

### config.yaml
```yaml
# LLM Configuration for Agent
llm_model: "llama3.2:latest"
ollama_url: "http://localhost:11434"

# Embedding model (used for RAG retrieval)
embedding:
  model: "mxbai-embed-large"

# ChromaDB settings (agent uses same vector store)
chroma:
  cv_persist_dir: "./chroma_db"
  cv_collection_name: "cv_sections"
```

## Dependencies

### Core Requirements (already included)
```
langchain>=0.1.0
langchain-community>=0.0.10
langchain-chroma>=0.1.0
langchain-ollama>=0.1.0
chromadb>=0.4.22
```

### Voice Agent Extensions (optional)
```
sounddevice>=0.4.6
openai-whisper>=20231117
pyttsx3>=2.90
scipy>=1.11.0
torch>=2.1.0
```

## Advanced: Voice Agent

The `voice_agent/run_agent.py` script provides hands-free voice interaction:

### Features
- Automatic speech detection (Silero VAD)
- Speech-to-text (OpenAI Whisper)
- Text-to-speech (pyttsx3)
- Hands-free conversation

### Usage
```bash
# Text mode
python voice_agent/run_agent.py text

# Voice mode
python voice_agent/run_agent.py voice
```

## Example Questions

### Scoring Explanation
- "Why did this candidate receive a score of 0.85?"
- "What factors contributed most to their score?"
- "How does the scoring breakdown work?"

### Skills Analysis
- "What mandatory skills does the candidate have?"
- "Which required skills are they missing?"
- "Tell me about their technical depth"
- "How recent is their skill usage?"

### Experience Evaluation
- "Summarize their relevant work experience"
- "Do they have experience with [specific technology]?"
- "What's their career progression like?"

### Impact & Achievements
- "What are their most impressive achievements?"
- "Tell me about quantified results they've delivered"
- "How do their achievements relate to this role?"

### Comparison & Decision Support
- "What would improve this candidate's score?"
- "Are there any red flags I should know about?"
- "What makes this candidate stand out?"

## Session Management

### Memory Considerations
- Each agent session maintains:
  - LangChain QA chain
  - ChromaDB connection
  - Full context document
  - Conversation history (client-side)

### Best Practices
- Close sessions when done (automatic on modal close)
- Admin can monitor active sessions via `/agent/sessions`
- Sessions are cleared on server shutdown
- No persistence between server restarts (by design)

## Troubleshooting

### Agent Not Responding
1. Check Ollama is running: `ollama list`
2. Verify LLM model is available: `ollama pull llama3.2:latest`
3. Check ChromaDB connection in logs
4. Ensure MongoDB has CV and JD data

### Poor Answer Quality
1. Verify scoring_result contains full details (use `show_details: true` in search)
2. Check context document generation in logs
3. Try different LLM models in config.yaml
4. Increase ChromaDB retrieval k value (default: 5)

### Performance Issues
1. Close unused agent sessions
2. Consider using smaller LLM models
3. Reduce ChromaDB search results
4. Use pagination for large conversations

## Future Enhancements

- [ ] Conversation history persistence
- [ ] Multi-candidate comparison mode
- [ ] Export conversation as PDF
- [ ] Fine-tuned prompts per industry
- [ ] Sentiment analysis integration
- [ ] Real-time voice agent in web UI
- [ ] Agent personality customization
- [ ] Multi-language support

## Testing

### Quick Test
1. Upload a JD and some CVs
2. Run search with `show_details: true`
3. Click "Ask Agent" on any result
4. Try suggested questions
5. Ask custom questions

### Example Test Questions
```
"What are the candidate's top 3 strengths?"
"Why did they score 85% on required_skills?"
"Explain their impact achievements"
"How many years of relevant experience do they have?"
"What education background do they have?"
```

## Security Considerations

- Agent sessions are user-scoped (requires authentication)
- Company access is enforced via `_enforce_company_access`
- No sensitive data is logged
- Sessions expire on server restart
- Rate limiting recommended for production

## Performance Metrics

Typical response times (on laptop with local Ollama):
- Session creation: 2-3 seconds
- Question answering: 3-5 seconds
- ChromaDB retrieval: <100ms
- LLM generation: 2-4 seconds

## Credits

Built with:
- **LangChain** - RAG framework
- **Ollama** - Local LLM inference
- **ChromaDB** - Vector database
- **FastAPI** - Backend API
- **Vanilla JS** - Frontend (no framework bloat!)
