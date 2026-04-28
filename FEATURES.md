# Application Features & Workflow

This document outlines the features of the CV Parser & Scoring Application, organized by the typical user workflow.

## 1. Authentication & Access
Before accessing the system, users must authenticate.
- **Secure Login**: Role-based access control for Recruiters and Admins.
- **Company Isolation**: Users are assigned to specific companies, ensuring data privacy and isolation between tenants.

## 2. Job Description (JD) Management
The hiring process begins with defining the role.
- **JD Upload**: Support for uploading Job Descriptions in **TXT, PDF, or DOCX** formats.
- **Structured Parsing**: The system automatically extracts key requirements:
  - **Job Title**
  - **Required Skills** (Mandatory)
  - **Preferred Skills** (Optional)
  - **Experience & Education Requirements**
  - **Responsibilities**

## 3. Candidate Ingestion (CV Upload)
Recruiters upload candidate documents for the specific job.
- **Drag & Drop Interface**: Easy bulk upload of candidate files.
- **Multi-Format Support**: Handles **PDF, DOCX**, and Image formats (**PNG, JPG, JPEG**) using OCR.
- **Intelligent Parsing**: Automatically extracts structured data from CVs:
  - **Contact Info**: Email (hashed for privacy or displayed), Phone, Links.
  - **Skills**: Normalized against a taxonomy.
  - **Work History**: Roles, companies, dates, and descriptions.
  - **Education**: Degrees and institutions.
  - **Projects & Certifications**.

## 4. Intelligent Scoring & Matching
Once CVs are uploaded, the **Hybrid Scoring Engine** evaluates them against the JD.
1.  **Vector Retrieval (Semantic Search)**:
    - Uses **ChromaDB** and **Ollama embeddings** (specifically the `mxbai-embed-large` model) to find candidates with semantically similar experience.
    - Performs **Section-Specific Retrieval** (e.g., matching JD "Responsibilities" to CV "Projects").
2.  **Keyword Analysis (BM25)**:
    - Applies traditional keyword scoring to ensure exact matches for critical terms are valued.
3.  **Skill Gap Analysis**:
    - **Taxonomy Normalization**: Maps synonyms (e.g., "React.js" -> "React") using `skills_taxonomy.yaml`.
    - **Mandatory vs. Optional**: Heavily penalizes missing mandatory skills while rewarding optional ones.
    - **Depth & Recency**: Calculates skill proficiency based on how recently and frequently a skill was used.
4.  **Impact Assessment**:
    - **Event Extraction**: Identifies quantified achievements (Verb + Metric + Outcome).
    - **Relevance Filtering**: Scores impact events based on their relevance to the job's required skills.
5.  **Cross-Encoder Reranking**:
    - The top candidates undergo a final pass with a **Cross-Encoder model** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) for high-precision similarity scoring.

## 5. Candidate Review & Analysis
Recruiters view the ranked results.
- **Ranked Dashboard**: Candidates are listed by their final weighted score.
- **Score Breakdown**: Detailed visualization of *why* a candidate received their score:
  - Semantic Similarity Score
  - Skill Match Score
  - Impact Score
  - Experience/Education Alignment
- **Detailed View**: Click on any candidate to see their parsed profile, extracted skills, and impact events.

## 6. AI-Powered Insights (The "Why")
For deeper analysis, recruiters interact with the **AI HR Assistant**.
- **Interactive Chat**: A built-in RAG (Retrieval-Augmented Generation) agent.
- **Context-Aware**: The agent has access to the CV, the JD, and the specific scoring logic used.
- **Sample Queries**:
  - *"Why did this candidate score highly?"*
  - *"What mandatory skills are they missing?"*
  - *"Summarize their leadership experience in the context of this role."*

## 7. Admin & System Management
Administrators maintain the system health and user base.
- **User Management**: Create/Edit/Delete users and assign company access.
- **Data Browser**: View all companies, jobs, and CVs in a hierarchical view.
- **Bulk Operations**:
  - **Delete CVs/JDs**: Clean up old data.
  - **Nuclear Option**: Completely remove a company tenant.
- **System Health**: Monitor database status and embedding service availability.
- **Reindexing**: Regenerate embeddings if models are updated.

## Appendix: Technical Stack
- **Backend**: Python, FastAPI
- **Database**: MongoDB (Metadata), ChromaDB (Vector Store)
- **AI/ML**: Ollama (Llama 3, mxbai-embed-large), LangChain, Sentence Transformers
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla + Bootstrap 5)
