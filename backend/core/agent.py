"""
HR Explainability Agent for CV Scoring

This module provides an AI agent that helps HR recruiters understand CV scoring decisions.
The agent has access to:
- Full CV structured data
- Job description requirements
- Detailed scoring breakdown (hybrid scores, skill coverage, impact events)
- Context from the vector database

The agent can answer questions like:
- "Why did this candidate score highly?"
- "What skills are they missing?"
- "Tell me about their impact achievements"
- "How does their experience align with the role?"
"""

import os
import json
import yaml
from typing import Dict, List, Any, Optional
from datetime import datetime

from langchain_ollama import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_chroma import Chroma
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from pymongo.collection import Collection
from bson import ObjectId

import logging
logger = logging.getLogger(__name__)


class CVScoringContext:
    """
    Builds comprehensive context for the RAG agent by loading CV, JD, and scoring results.
    """
    def __init__(
        self,
        cv_id: str,
        jd_id: str,
        cv_collection: Collection,
        jd_collection: Collection,
        scoring_result: Optional[Dict[str, Any]] = None,
        company_name: Optional[str] = None
    ):
        self.cv_id = cv_id
        self.jd_id = jd_id
        self.cv_collection = cv_collection
        self.jd_collection = jd_collection
        self.scoring_result = scoring_result or {}
        self.company_name = company_name
        self.cv_data = None
        self.jd_data = None

    @staticmethod
    def safe_join(value, default="N/A"):
        """Safely convert lists and values to strings."""
        if value is None:
            return default
        if isinstance(value, list):
            return ', '.join(str(v) for v in value) if value else default
        return str(value)

    def load_cv_data(self) -> Dict[str, Any]:
        """Load CV data from MongoDB by cv_id or _id."""
        query = {"cv_id": self.cv_id}
        self.cv_data = self.cv_collection.find_one(query)
        
        if not self.cv_data:
            # Try with ObjectId if cv_id is a valid ObjectId string
            try:
                if isinstance(self.cv_id, str) and len(self.cv_id) == 24:
                    query = {"_id": ObjectId(self.cv_id)}
                else:
                    query = {"_id": self.cv_id}
                self.cv_data = self.cv_collection.find_one(query)
            except Exception as e:
                logger.warning(f"Could not parse cv_id as ObjectId: {e}")
        
        if not self.cv_data:
            raise ValueError(f"CV not found with ID: {self.cv_id}")
        
        return self.cv_data

    def load_jd_data(self) -> Dict[str, Any]:
        """Load JD data from MongoDB by jd_id or _id."""
        query = {"jd_id": self.jd_id}
        if self.company_name:
            query["company_name"] = self.company_name
        
        self.jd_data = self.jd_collection.find_one(query)
        
        if not self.jd_data:
            # Try with ObjectId
            try:
                if isinstance(self.jd_id, str) and len(self.jd_id) == 24:
                    query = {"_id": ObjectId(self.jd_id)}
                else:
                    query = {"_id": self.jd_id}
                if self.company_name:
                    query["company_name"] = self.company_name
                self.jd_data = self.jd_collection.find_one(query)
            except Exception as e:
                logger.warning(f"Could not parse jd_id as ObjectId: {e}")
        
        if not self.jd_data:
            raise ValueError(f"JD not found with ID: {self.jd_id}")
        
        return self.jd_data

    def _format_work_experience(self, work_exp: List[Dict]) -> str:
        """Format work experience for readable display."""
        if not work_exp:
            return "No work experience listed"
        
        formatted = []
        for exp in work_exp[:5]:  # Top 5 most recent
            title = exp.get('title', 'N/A')
            company = exp.get('company', 'N/A')
            duration = exp.get('duration', 'N/A')
            responsibilities = exp.get('responsibilities', [])
            
            exp_text = f"• {title} at {company} ({duration})"
            if responsibilities:
                resp_sample = responsibilities[:3]  # First 3 responsibilities
                exp_text += "\n  - " + "\n  - ".join(resp_sample)
            formatted.append(exp_text)
        
        return "\n".join(formatted)

    def _format_impact_events(self, impact_events: List[Dict]) -> str:
        """Format impact events for readable display."""
        if not impact_events:
            return "No quantified impact achievements found"
        
        formatted = []
        for event in impact_events[:10]:  # Top 10 impacts
            sentence = event.get('sentence', '')
            score = event.get('event_score', 0)
            verbs = event.get('verbs', [])
            metrics = event.get('metrics', [])
            
            formatted.append(
                f"• {sentence} "
                f"(Score: {score:.2f}, Verbs: {', '.join(verbs)}, "
                f"Metrics: {len(metrics)})"
            )
        
        return "\n".join(formatted)

    def _format_skill_coverage(self) -> str:
        """Format skill coverage details."""
        if not self.scoring_result:
            return "No scoring data available"
        
        mandatory_cov = self.scoring_result.get('skill_mandatory_coverage', 0) * 100
        optional_cov = self.scoring_result.get('skill_optional_coverage', 0) * 100
        mandatory_missing = self.scoring_result.get('skill_mandatory_missing', [])
        depth_score = self.scoring_result.get('skill_depth_score_raw', 0)
        recency_score = self.scoring_result.get('skill_recency_score_raw', 0)
        
        text = f"""Skill Coverage Analysis:
• Mandatory Skills Coverage: {mandatory_cov:.1f}%
• Optional Skills Coverage: {optional_cov:.1f}%
• Missing Mandatory Skills: {', '.join(mandatory_missing) if mandatory_missing else 'None'}
• Skill Depth Score: {depth_score:.2f}
• Skill Recency Score: {recency_score:.2f}"""
        
        return text

    def build_context_document(self) -> str:
        """Build a comprehensive context document for the RAG agent."""
        if not self.cv_data or not self.jd_data:
            self.load_cv_data()
            self.load_jd_data()
        
        # Extract CV information
        candidate_name = self.cv_data.get('name', 'N/A')
        candidate_email = self.cv_data.get('email', 'N/A')
        summary = self.cv_data.get('summary', 'N/A')
        skills = self.safe_join(self.cv_data.get('skills', []))
        education = self.safe_join(self.cv_data.get('education', []))
        work_experience = self._format_work_experience(self.cv_data.get('work_experience', []))
        years_of_experience = self.cv_data.get('years_of_experience', 'N/A')
        
        # Extract JD information
        job_title = self.jd_data.get('job_title', 'N/A')
        company = self.jd_data.get('company_name', 'N/A')
        required_skills = self.safe_join(self.jd_data.get('required_skills', []))
        preferred_skills = self.safe_join(self.jd_data.get('preferred_skills', []))
        responsibilities = self.safe_join(self.jd_data.get('responsibilities', []))
        required_qualifications = self.safe_join(self.jd_data.get('required_qualifications', []))
        
        # Scoring information
        combined_score = self.scoring_result.get('combined_score', 0)
        score_components = self.scoring_result.get('score_components', {})
        skill_coverage_text = self._format_skill_coverage()
        
        # Impact events (if available)
        impact_events = self.scoring_result.get('impact_events', [])
        impact_text = self._format_impact_events(impact_events)
        impact_score = self.scoring_result.get('impact_raw_score', 0)
        
        context = f"""
=== CANDIDATE PROFILE ===
Name: {candidate_name}
Email: {candidate_email}
Years of Experience: {years_of_experience}
Summary: {summary}

Skills: {skills}

Education: {education}

Work Experience:
{work_experience}

=== JOB REQUIREMENTS ===
Position: {job_title}
Company: {company}

Required Skills: {required_skills}
Preferred Skills: {preferred_skills}

Key Responsibilities: {responsibilities}
Qualifications Required: {required_qualifications}

=== SCORING ANALYSIS ===
Overall Combined Score: {combined_score:.4f}

Score Components:
- Vector Similarity: {score_components.get('vector', 0):.4f}
- BM25 Keyword Match: {score_components.get('bm25_norm', 0):.4f}
- Cross-Encoder Score: {score_components.get('ce_global_norm', 0):.4f}
- Penalty Applied: {score_components.get('penalty', 0):.4f}

{skill_coverage_text}

=== IMPACT ACHIEVEMENTS ===
Impact Score: {impact_score:.2f}
Total Impact Events: {len(impact_events)}

{impact_text}

=== SCORING INTERPRETATION ===
The combined score represents a weighted combination of:
1. Semantic similarity between CV and JD (vector embeddings)
2. Keyword matching (BM25 algorithm)
3. Deep semantic understanding (cross-encoder reranking)
4. Skill coverage (mandatory vs optional skills)
5. Skill depth and recency
6. Quantified impact achievements

Higher scores indicate better alignment between the candidate's profile and job requirements.
"""
        return context

    def get_summary(self) -> Dict[str, Any]:
        """Get a quick summary of the context."""
        if not self.cv_data or not self.jd_data:
            self.load_cv_data()
            self.load_jd_data()
        
        return {
            "candidate_name": self.cv_data.get('name', 'N/A'),
            "candidate_email": self.cv_data.get('email', 'N/A'),
            "cv_id": self.cv_id,
            "job_title": self.jd_data.get('job_title', 'N/A'),
            "company": self.jd_data.get('company_name', 'N/A'),
            "jd_id": self.jd_id,
            "combined_score": self.scoring_result.get('combined_score', 0),
            "mandatory_coverage": self.scoring_result.get('skill_mandatory_coverage', 0)
        }


class CVExplainabilityAgent:
    """
    RAG-based agent that explains CV scoring decisions to HR recruiters.
    Uses ChromaDB for context retrieval and Ollama LLM for generation.
    """
    
    def __init__(
        self,
        context: CVScoringContext,
        config: Dict[str, Any],
        company_name: Optional[str] = None
    ):
        self.context = context
        self.company_name = company_name
        self.config = config
        
        try:
            # Initialize LLM
            llm_model = config.get("llm_model", "llama3.2:latest")
            ollama_url = config.get("ollama_url", "http://localhost:11434")
            logger.info(f"Initializing LLM: {llm_model} at {ollama_url}")
            self.llm = Ollama(model=llm_model, base_url=ollama_url)
            
            # Initialize embeddings
            embedding_model = config["embedding"]["model"]
            logger.info(f"Initializing embeddings: {embedding_model}")
            self.embeddings = OllamaEmbeddings(model=embedding_model, base_url=ollama_url)
            
            # Vector store and QA chain
            self.vector_store = None
            self.qa_chain = None
            
            logger.info("Building context document")
            self.context_text = self.context.build_context_document()
            
            logger.info("Setting up vector store")
            self._setup_vector_store()
            
            logger.info("Setting up QA chain")
            self._setup_qa_chain()
            
            logger.info("Agent initialization complete")
            
        except Exception as e:
            logger.error(f"Error during agent initialization: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize agent: {str(e)}")

    def _setup_vector_store(self):
        """Initialize or connect to ChromaDB vector store."""
        cv_persist_dir = self.config["chroma"]["cv_persist_dir"]
        cv_collection_name = self.config["chroma"]["cv_collection_name"]
        
        if self.company_name:
            # Use company-specific collection
            company_fragment = "".join(e for e in self.company_name if e.isalnum()).lower()
            cv_collection_name = f"{company_fragment}_cv_sections"
            cv_persist_dir = os.path.join(cv_persist_dir, company_fragment)
        
        try:
            self.vector_store = Chroma(
                collection_name=cv_collection_name,
                embedding_function=self.embeddings,
                persist_directory=cv_persist_dir
            )
            logger.info(f"✅ Connected to ChromaDB: {cv_collection_name}")
        except Exception as e:
            logger.warning(f"⚠️ Could not connect to ChromaDB: {e}. Creating in-memory store.")
            # Fallback to in-memory store with context document
            docs = [Document(
                page_content=self.context_text,
                metadata={"source": "context", "type": "full_context"}
            )]
            self.vector_store = Chroma.from_documents(
                documents=docs,
                embedding=self.embeddings
            )

    def _setup_qa_chain(self):
        """Initialize the RetrievalQA chain with custom prompt."""
        template = """You are an expert AI assistant helping HR recruiters understand CV scoring decisions.
You have access to comprehensive information about a candidate's CV, the job requirements, and detailed scoring analysis.

Context Information:
{context}

HR Question: {question}

Instructions:
- Provide clear, concise answers based on the available data
- When discussing scores, explain what they mean in practical terms
- Highlight strengths and gaps objectively
- If asked about specific skills or achievements, cite evidence from the CV
- If information is not available in the context, say so honestly
- Be professional and helpful

Answer:"""
        
        PROMPT = PromptTemplate(
            template=template,
            input_variables=["context", "question"]
        )
        
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_store.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )
        logger.info("✅ QA Chain initialized")

    def ask(self, question: str) -> Dict[str, Any]:
        """
        Ask the agent a question about the CV scoring.
        
        Args:
            question: HR's question about the candidate
            
        Returns:
            Dictionary with answer and source documents
        """
        try:
            result = self.qa_chain.invoke({"query": question})
            return {
                "question": question,
                "answer": result["result"],
                "sources": [
                    {
                        "content": doc.page_content[:200] + "...",
                        "metadata": doc.metadata
                    }
                    for doc in result.get("source_documents", [])
                ],
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error in agent.ask: {e}")
            return {
                "question": question,
                "answer": f"I encountered an error processing your question: {str(e)}",
                "sources": [],
                "status": "error",
                "error": str(e)
            }

    def get_suggested_questions(self) -> List[str]:
        """Get suggested questions based on the scoring results."""
        suggestions = [
            "Why did this candidate receive this score?",
            "What are the candidate's main strengths?",
            "What skills is the candidate missing?",
            "Tell me about their relevant experience",
            "What are their most impressive achievements?"
        ]
        
        # Add context-specific suggestions
        if self.context.scoring_result:
            score = self.context.scoring_result.get('combined_score', 0)
            if score < 0.5:
                suggestions.append("What would improve this candidate's score?")
            
            impact_events = self.context.scoring_result.get('impact_events', [])
            if impact_events:
                suggestions.append("Tell me about their quantified impact achievements")
            
            missing_skills = self.context.scoring_result.get('skill_mandatory_missing', [])
            if missing_skills:
                suggestions.append("How critical are the missing mandatory skills?")
        
        return suggestions


class BatchCVScoringContext:
    """
    Builds comprehensive context for the RAG agent with multiple CV results and a single JD.
    This enables the agent to compare and analyze multiple candidates at once.
    """
    def __init__(
        self,
        cv_results: List[Dict[str, Any]],
        jd_id: str,
        jd_collection: Collection,
        cv_collection: Collection,
        company_name: str,
        job_title: str
    ):
        self.cv_results = cv_results  # List of scoring results with cv_id and scores
        self.jd_id = jd_id
        self.jd_collection = jd_collection
        self.cv_collection = cv_collection
        self.company_name = company_name
        self.job_title = job_title
        self.jd_data = None
        self.cv_data_map = {}  # cv_id -> full CV data

    @staticmethod
    def safe_join(value, default="N/A"):
        """Safely convert lists and values to strings."""
        if value is None:
            return default
        if isinstance(value, list):
            return ', '.join(str(v) for v in value) if value else default
        return str(value)

    def load_jd_data(self) -> Dict[str, Any]:
        """Load JD data from MongoDB by jd_id."""
        query = {"jd_id": self.jd_id}
        if self.company_name:
            query["company_name"] = self.company_name
        
        self.jd_data = self.jd_collection.find_one(query)
        
        if not self.jd_data:
            # Try with ObjectId
            try:
                if isinstance(self.jd_id, str) and len(self.jd_id) == 24:
                    query = {"_id": ObjectId(self.jd_id)}
                else:
                    query = {"_id": self.jd_id}
                if self.company_name:
                    query["company_name"] = self.company_name
                self.jd_data = self.jd_collection.find_one(query)
            except Exception as e:
                logger.warning(f"Could not parse jd_id as ObjectId: {e}")
        
        if not self.jd_data:
            raise ValueError(f"JD not found with ID: {self.jd_id}")
        
        logger.info(f"✅ JD data loaded successfully: {self.jd_data.get('job_title', 'N/A')}")
        return self.jd_data

    def load_cv_data_for_all(self):
        """Load CV data for all candidates in the results."""
        for result in self.cv_results:
            cv_id = result.get('cv_id')
            if not cv_id:
                continue
                
            query = {"cv_id": cv_id}
            cv_data = self.cv_collection.find_one(query)
            
            if not cv_data:
                # Try with ObjectId or _id
                try:
                    if isinstance(cv_id, str) and len(cv_id) == 24:
                        query = {"_id": ObjectId(cv_id)}
                    else:
                        query = {"_id": cv_id}
                    cv_data = self.cv_collection.find_one(query)
                except Exception as e:
                    logger.warning(f"Could not find CV with id {cv_id}: {e}")
                    continue
            
            if cv_data:
                self.cv_data_map[cv_id] = cv_data
        
        logger.info(f"✅ Loaded CV data for {len(self.cv_data_map)} candidates")

    def _format_candidate_summary(self, cv_id: str, result: Dict[str, Any]) -> str:
        """Format a single candidate's summary."""
        cv_data = self.cv_data_map.get(cv_id, {})
        
        name = result.get('name') or cv_data.get('name', 'Unknown')
        combined_score = result.get('combined_score', 0)
        mandatory_cov = result.get('skill_mandatory_coverage', 0)
        optional_cov = result.get('skill_optional_coverage', 0)
        missing_mandatory = result.get('skill_mandatory_missing', [])
        
        # Basic info
        years_exp = cv_data.get('years_of_experience', 'N/A')
        summary = cv_data.get('summary', 'No summary available')[:200]
        skills = self.safe_join(cv_data.get('skills', [])[:10])  # Top 10 skills
        
        # Work experience (most recent)
        work_exp = cv_data.get('work_experience', [])
        recent_role = "N/A"
        if work_exp:
            recent = work_exp[0]
            recent_role = f"{recent.get('title', 'N/A')} at {recent.get('company', 'N/A')}"
        
        text = f"""
--- Candidate: {name} ---
CV ID: {cv_id[:16]}...
Combined Score: {combined_score:.4f} ({combined_score*100:.1f}%)
Mandatory Skills Coverage: {mandatory_cov*100:.1f}%
Optional Skills Coverage: {optional_cov*100:.1f}%
Missing Mandatory Skills: {', '.join(missing_mandatory) if missing_mandatory else 'None'}

Years of Experience: {years_exp}
Most Recent Role: {recent_role}
Key Skills: {skills}
Summary: {summary}...
"""
        return text

    def build_context_document(self) -> str:
        """Build a comprehensive context document with all candidates and the JD."""
        if not self.jd_data:
            self.load_jd_data()
        
        if not self.cv_data_map:
            self.load_cv_data_for_all()
        
        # JD Information
        job_title = self.jd_data.get('job_title', 'N/A')
        company = self.jd_data.get('company_name', self.company_name)
        required_skills = self.safe_join(self.jd_data.get('required_skills', []))
        preferred_skills = self.safe_join(self.jd_data.get('preferred_skills', []))
        responsibilities = self.safe_join(self.jd_data.get('responsibilities', []))
        required_qualifications = self.safe_join(self.jd_data.get('required_qualifications', []))
        education_requirements = self.safe_join(self.jd_data.get('education_requirements', []))
        experience_requirements = self.safe_join(self.jd_data.get('experience_requirements', []))
        
        context = f"""
=== JOB DESCRIPTION ===
Position: {job_title}
Company: {company}

Required Skills: {required_skills}
Preferred Skills: {preferred_skills}

Key Responsibilities: {responsibilities}
Required Qualifications: {required_qualifications}
Education Requirements: {education_requirements}
Experience Requirements: {experience_requirements}

=== CANDIDATE POOL ({len(self.cv_results)} candidates) ===
"""
        
        # Add each candidate
        for result in self.cv_results:
            cv_id = result.get('cv_id')
            if cv_id:
                context += self._format_candidate_summary(cv_id, result)
        
        context += """

=== SCORING EXPLANATION ===
The combined score represents a weighted combination of:
1. Semantic similarity between CV and JD (vector embeddings)
2. Keyword matching (BM25 algorithm)
3. Deep semantic understanding (cross-encoder reranking)
4. Skill coverage (mandatory vs optional skills)
5. Skill depth and recency
6. Quantified impact achievements

Candidates are ranked by their combined scores.
Higher mandatory skill coverage indicates better baseline fit.
"""
        
        return context

    def get_summary(self) -> Dict[str, Any]:
        """Get a quick summary of the context."""
        if not self.jd_data:
            self.load_jd_data()
        
        return {
            "job_title": self.jd_data.get('job_title', self.job_title),
            "company": self.jd_data.get('company_name', self.company_name),
            "jd_id": self.jd_id,
            "candidate_count": len(self.cv_results),
            "top_candidate": self.cv_results[0] if self.cv_results else None
        }


class BatchCVExplainabilityAgent:
    """
    RAG-based agent that explains CV scoring decisions for multiple candidates.
    Has access to all candidates and the job description for comparative analysis.
    """
    
    def __init__(
        self,
        context: BatchCVScoringContext,
        config: Dict[str, Any],
        company_name: Optional[str] = None
    ):
        self.context = context
        self.company_name = company_name
        self.config = config
        
        try:
            # Initialize LLM
            llm_model = config.get("llm_model", "llama3.2:latest")
            ollama_url = config.get("ollama_url", "http://localhost:11434")
            logger.info(f"Initializing Batch Agent LLM: {llm_model} at {ollama_url}")
            self.llm = Ollama(model=llm_model, base_url=ollama_url)
            
            # Initialize embeddings
            embedding_model = config["embedding"]["model"]
            logger.info(f"Initializing embeddings: {embedding_model}")
            self.embeddings = OllamaEmbeddings(model=embedding_model, base_url=ollama_url)
            
            # Vector store and QA chain
            self.vector_store = None
            self.qa_chain = None
            
            logger.info("Building batch context document")
            self.context_text = self.context.build_context_document()
            
            logger.info("Setting up vector store")
            self._setup_vector_store()
            
            logger.info("Setting up QA chain")
            self._setup_qa_chain()
            
            logger.info("Batch agent initialization complete")
            
        except Exception as e:
            logger.error(f"Error during batch agent initialization: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize batch agent: {str(e)}")

    def _setup_vector_store(self):
        """Initialize or connect to ChromaDB vector store."""
        # Create in-memory store with context document for batch analysis
        docs = [
            Document(
                page_content=self.context_text,
                metadata={"source": "batch_context", "type": "full_context"}
            )
        ]
        
        # Also add JD as separate document
        jd_text = f"""Job Description:
Position: {self.context.jd_data.get('job_title', 'N/A')}
Company: {self.context.jd_data.get('company_name', 'N/A')}
Required Skills: {self.context.safe_join(self.context.jd_data.get('required_skills', []))}
Responsibilities: {self.context.safe_join(self.context.jd_data.get('responsibilities', []))}
"""
        docs.append(Document(
            page_content=jd_text,
            metadata={"source": "job_description", "type": "jd"}
        ))
        
        self.vector_store = Chroma.from_documents(
            documents=docs,
            embedding=self.embeddings
        )
        logger.info(f"✅ Created in-memory vector store with {len(docs)} documents")

    def _setup_qa_chain(self):
        """Initialize the RetrievalQA chain with custom prompt for batch analysis."""
        template = """You are an expert AI assistant helping HR recruiters compare and analyze multiple candidates.
You have access to comprehensive information about ALL candidates, the job requirements, and detailed scoring analysis.

Context Information:
{context}

HR Question: {question}

Instructions:
- Provide clear, comparative answers when comparing candidates
- When discussing scores, explain what they mean in practical terms
- Highlight relative strengths and gaps across candidates
- If asked about specific candidates, use their names or CV IDs
- If asked about the job description, provide accurate information
- Be professional, objective, and data-driven
- Don't talk about the technical details of how the system works(eg, vector embeddings, BM25, etc.)
- If information is not available, say so honestly

Answer:"""
        
        PROMPT = PromptTemplate(
            template=template,
            input_variables=["context", "question"]
        )
        
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_store.as_retriever(search_kwargs={"k": 10}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )
        logger.info("✅ Batch QA Chain initialized")

    def ask(self, question: str) -> Dict[str, Any]:
        """
        Ask the agent a question about the candidates or job description.
        
        Args:
            question: HR's question about the candidates
            
        Returns:
            Dictionary with answer and source documents
        """
        try:
            result = self.qa_chain.invoke({"query": question})
            return {
                "question": question,
                "answer": result["result"],
                "sources": [
                    {
                        "content": doc.page_content[:200] + "...",
                        "metadata": doc.metadata
                    }
                    for doc in result.get("source_documents", [])
                ],
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error in batch agent.ask: {e}")
            return {
                "question": question,
                "answer": f"I encountered an error processing your question: {str(e)}",
                "sources": [],
                "status": "error",
                "error": str(e)
            }

    def get_suggested_questions(self) -> List[str]:
        """Get suggested questions for batch candidate analysis."""
        suggestions = [
            "Compare the top 3 candidates",
            "Which candidate has the strongest technical skills?",
            "What are the key differences between the candidates?",
            "Who has the most relevant experience?",
            "Which candidates are missing critical skills?",
            "Summarize the strengths and weaknesses of each candidate",
            "What does the job description require?",
            "Which candidate would you recommend and why?"
        ]
        
        return suggestions
