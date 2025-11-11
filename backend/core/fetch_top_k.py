import logging
import os
from typing import Any, Dict, List, Optional, Tuple

# Optional MongoDB import (graceful fallback)
try:
    from pymongo import MongoClient  # type: ignore
except Exception:  # pragma: no cover
    MongoClient = None  # type: ignore

import numpy as np
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CVJDVectorSearch:
    """Performs vector search of CVs against a job description with section-wise scoring."""
    
    # Defaults as class-level constants for easy reuse and testing
    DEFAULT_SECTION_WEIGHT: float = 0.05
    DEFAULT_TOP_K: int = 5

    def __init__(
        self,
        cv_persist_dir="./chroma_db_cv",
        jd_persist_dir="./jd_chroma_db",
        cv_collection_name="cv_sections",
        jd_collection_name="job_descriptions",
        model="mxbai-embed-large",
        top_k_per_section: int = DEFAULT_TOP_K,
        config_path: str | None = "cvjd_config.yaml"
    ):
        """Initialize with Chroma collections and embedding model."""
        self.embeddings = OllamaEmbeddings(model=model)
        self.top_k_per_section = top_k_per_section
        
        # Initialize Chroma vector stores
        self.cv_vectorstore = Chroma(
            persist_directory=cv_persist_dir,
            embedding_function=self.embeddings,
            collection_name=cv_collection_name,
            collection_metadata={"hnsw:space": "cosine"}
        )
        self.jd_vectorstore = Chroma(
            persist_directory=jd_persist_dir,
            embedding_function=self.embeddings,
            collection_name=jd_collection_name,
            collection_metadata={"hnsw:space": "cosine"}
        )
        
        # Defaults: Section mapping and weights (can be overridden via YAML config)
        self.section_mapping = {
            "job_title": ["summary"],
            "required_skills": ["skills", "work_experience"],
            "preferred_skills": ["skills", "work_experience"],
            "required_qualifications": ["education", "years_of_experience", "work_experience"],
            "education_requirements": ["education"],
            "experience_requirements": ["work_experience", "years_of_experience"],
            "technical_skills": ["skills"],
            "soft_skills": ["soft_skills"],
            "certifications": ["certifications"],
            "responsibilities": ["work_experience", "projects"]
        }
        self.section_weights = {
            "required_skills": 0.3,
            "preferred_skills": 0.05,
            "required_qualifications": 0.05,
            "education_requirements": 0.05,
            "experience_requirements": 0.05,
            "technical_skills": 0.05,
            "soft_skills": 0.1,
            "certifications": 0.1,
            "responsibilities": 0.1,
            "job_title": 0.05
        }

        # Optional: load overrides from YAML
        if config_path and os.path.exists(config_path) and yaml is not None:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg: Dict[str, Any] = yaml.safe_load(f) or {}
                mapping = cfg.get("section_mapping")
                weights = cfg.get("section_weights")
                if isinstance(mapping, dict) and mapping:
                    self.section_mapping = mapping
                    logger.info("Loaded section_mapping from YAML config")
                if isinstance(weights, dict) and weights:
                    self.section_weights = weights
                    logger.info("Loaded section_weights from YAML config")
                # Optional knobs
                if "top_k_per_section" in cfg:
                    self.top_k_per_section = int(cfg["top_k_per_section"])
                if "model" in cfg and isinstance(cfg["model"], str):
                    # Re-initialize embeddings if model overridden
                    self.embeddings = OllamaEmbeddings(model=cfg["model"])
            except Exception as e:
                logger.warning(f"Failed to load YAML config '{config_path}': {e}")
        elif config_path and os.path.exists(config_path) and yaml is None:
            logger.warning("PyYAML not installed; skipping config load")

        # Validate/normalize weights against mapping
        self._validate_and_normalize_weights()
        
        # Simple cache for cv_id -> identifier (email/phone)
        self._cv_id_cache: Dict[str, str] = {}
        
        # Store Mongo config placeholders (loaded lazily in lookup)
        self._mongo_cfg_loaded = False
        self._mongo_conn_str: Optional[str] = None
        self._mongo_db_name: Optional[str] = None
        self._mongo_collection_name: Optional[str] = None

    def _load_mongo_config(self) -> None:
        """Lazy-load MongoDB connection info from config.yaml if available.

        Expects a YAML structure like:
        mongodb:
          connection_string: ...
          cv_db_name: ...
          cv_collection_name: ...
        """
        if self._mongo_cfg_loaded:
            return
        self._mongo_cfg_loaded = True
        cfg_path = "config.yaml"
        if not os.path.exists(cfg_path) or yaml is None:
            logger.warning("Mongo config not loaded (missing config.yaml or PyYAML)")
            return
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg: Dict[str, Any] = yaml.safe_load(f) or {}
            mongo_cfg = cfg.get("mongodb", {})
            self._mongo_conn_str = mongo_cfg.get("connection_string")
            self._mongo_db_name = mongo_cfg.get("cv_db_name") or mongo_cfg.get("db_name")
            # Some configs may use cv_collection_name or generic collection_name
            self._mongo_collection_name = mongo_cfg.get("cv_collection_name") or mongo_cfg.get("collection_name")
            if not all([self._mongo_conn_str, self._mongo_db_name, self._mongo_collection_name]):
                logger.warning("Incomplete MongoDB config for CV lookup; email resolution may fail")
        except Exception as e:
            logger.warning(f"Failed to read Mongo config: {e}")

    def get_email_from_cv_id(self, cv_id: str) -> str:
        """Resolve original identifier (email or phone) from hashed cv_id using MongoDB.

        Falls back to returning cv_id if resolution fails. Results cached in-memory.
        """
        if not cv_id:
            return "unknown"
        # Cache lookup
        if cv_id in self._cv_id_cache:
            return self._cv_id_cache[cv_id]

        # Load Mongo config lazily
        self._load_mongo_config()
        if MongoClient is None:
            logger.warning("pymongo not installed; cannot resolve email from cv_id")
            self._cv_id_cache[cv_id] = cv_id
            return cv_id
        if not (self._mongo_conn_str and self._mongo_db_name and self._mongo_collection_name):
            logger.warning("MongoDB configuration missing; returning cv_id as identifier")
            self._cv_id_cache[cv_id] = cv_id
            return cv_id
        try:
            client = MongoClient(self._mongo_conn_str, serverSelectionTimeoutMS=3000)
            db = client[self._mongo_db_name]
            coll = db[self._mongo_collection_name]
            # Documents were inserted with _id = hashed cv_id (see CVDataInserter)
            doc = coll.find_one({"_id": cv_id}, {"email": 1, "phone": 1})
            if doc:
                identifier = doc.get("email") or doc.get("phone") or cv_id
            else:
                identifier = cv_id
            self._cv_id_cache[cv_id] = identifier
            return identifier
        except Exception as e:
            logger.warning(f"Lookup failed for cv_id {cv_id}: {e}")
            self._cv_id_cache[cv_id] = cv_id
            return cv_id
        
    def fetch_jd_chunks(self) -> List[Dict]:
        """Fetch all chunks from the job_descriptions collection (metadata + embeddings only)."""
        try:
            logger.info("Querying JD collection for all chunks")
            data = self.jd_vectorstore.get(
                include=["metadatas", "embeddings"]
            )
            chunks = [
                {
                    "metadata": data["metadatas"][i],
                    "embedding": data["embeddings"][i]
                }
                for i in range(len(data.get("embeddings", [])))
            ]
            logger.info(f"Fetched {len(chunks)} JD chunks (metadata + embeddings)")
            
            if len(chunks) == 0:
                all_data = self.jd_vectorstore.get(include=["metadatas"])
                all_jd_ids = set(meta.get("jd_id", "UNKNOWN") for meta in all_data.get("metadatas", []))
                logger.warning(f"No chunks found in job_descriptions. Available JD IDs: {all_jd_ids}")
            
            return chunks
        except Exception as e:
            logger.error(f"Failed to fetch JD chunks: {e}")
            return []
    
    def _validate_and_normalize_weights(self) -> None:
        """Ensure every mapping key has a weight and normalize weights to sum to 1.0."""
        default_weight = self.DEFAULT_SECTION_WEIGHT
        # Fill missing weights
        for key in self.section_mapping.keys():
            if key not in self.section_weights:
                self.section_weights[key] = default_weight
        # Drop extraneous weight keys not in mapping
        for key in list(self.section_weights.keys()):
            if key not in self.section_mapping:
                del self.section_weights[key]
        # Normalize to sum 1.0
        total = float(sum(self.section_weights.values()))
        if total > 0:
            for k in self.section_weights:
                self.section_weights[k] = float(self.section_weights[k]) / total

    def _build_where_clause(self, sections: List[str], cv_id: Optional[str] = None) -> Dict[str, Any]:
        where: Dict[str, Any] = {"section": {"$in": sections}}
        if cv_id:
            return {"$and": [where, {"cv_id": cv_id}]}
        return where

    def search_cv_chunks(
        self,
        jd_chunk_embedding: List[float],
        cv_sections: List[str],
        cv_id: Optional[str] = None
    ) -> List[Dict]:
        """Search CV chunks matching a JD chunk embedding, filtered by CV sections and optional CV ID."""
        try:
            # Access the underlying Chroma client
            collection = self.cv_vectorstore._collection
            # Build where clause with optional cv_id
            where_clause = self._build_where_clause(cv_sections, cv_id)
            
            # Perform query using precomputed embedding
            results = collection.query(
                query_embeddings=[jd_chunk_embedding],
                n_results=self.top_k_per_section,
                where=where_clause,
                include=["documents", "metadatas", "distances"]
            )
            
            # Check if results are empty
            if not results["documents"] or not results["documents"][0]:
                logger.warning(f"No CV chunks found for sections {cv_sections} and cv_id {cv_id}")
                return []
            
            return [
                {
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": results["distances"][0][i],
                    "cv_id": results["metadatas"][0][i]["cv_id"],
                    "section": results["metadatas"][0][i]["section"]
                }
                for i in range(len(results["documents"][0]))
            ]
        except Exception as e:
            logger.error(f"Error searching CV chunks: {e}")
            return []
    
    def compute_section_score(
        self,
        jd_section: str,
        jd_chunks: List[Dict],
        cv_id: Optional[str]
    ) -> Tuple[float, List[Dict]]:
        """Compute similarity score for a JD section against a CV using batched queries.

        Uses cosine similarity conversion: similarity = 1 - distance (when hnsw:space=cosine).
        Deduplicates matches by result ids.
        """
        cv_sections = self.section_mapping.get(jd_section, [])
        if not cv_sections:
            return 0.0, []

        # Collect embeddings for this JD section
        section_embeddings: List[List[float]] = [
            c["embedding"] for c in jd_chunks if c["metadata"].get("section") == jd_section
        ]
        if not section_embeddings:
            return 0.0, []

        try:
            collection = self.cv_vectorstore._collection
            where_clause = self._build_where_clause(cv_sections, cv_id)

            # Batch query for all JD embeddings in this section
            results = collection.query(
                query_embeddings=section_embeddings,
                n_results=self.top_k_per_section,
                where=where_clause,
                include=["metadatas", "distances"]
            )

            if not results or not results.get("ids"):
                return 0.0, []

            similarities: List[float] = []
            matched_chunks: List[Dict] = []
            seen_ids = set()

            # Iterate over each JD query index
            for q_idx in range(len(results["ids"])):
                ids_for_query = results["ids"][q_idx]
                metas_for_query = results["metadatas"][q_idx]
                dists_for_query = results["distances"][q_idx]
                if not ids_for_query:
                    continue
                for r_idx in range(len(ids_for_query)):
                    res_id = ids_for_query[r_idx]
                    if res_id in seen_ids:
                        continue
                    seen_ids.add(res_id)
                    dist = dists_for_query[r_idx]
                    # Cosine space distance -> similarity
                    similarity = 1.0 - float(dist)
                    similarities.append(similarity)
                    meta = metas_for_query[r_idx] or {}
                    matched_chunks.append({
                        "cv_section": meta.get("section"),
                        "cv_id": meta.get("cv_id"),
                        "similarity": similarity,
                        "id": res_id,
                    })

            section_score = float(np.mean(similarities)) if similarities else 0.0
            return section_score, matched_chunks
        except Exception as e:
            logger.error(f"Error in batched section scoring for '{jd_section}': {e}")
            return 0.0, []
    
    def search_and_score_cvs(self, top_k_cvs: Optional[int] = 5) -> List[Dict]:
        """Search and score CVs against the JD in job_descriptions collection."""
        # Fetch JD chunks
        jd_chunks = self.fetch_jd_chunks()
        if not jd_chunks:
            logger.error("No JD chunks found, aborting search")
            return []
        
        # Get all unique CV IDs (single fetch)
        try:
            cv_meta_resp = self.cv_vectorstore.get(include=["metadatas"]) or {}
            cv_metas = cv_meta_resp.get("metadatas", [])
            cv_ids = set(meta.get("cv_id") for meta in cv_metas if meta and meta.get("cv_id") is not None)
        except Exception as e:
            logger.error(f"Failed to enumerate CV IDs: {e}")
            return []
        
        # Score each CV
        cv_scores = []
        for cv_id in cv_ids:
            section_scores = {}
            section_details = {}
            total_score = 0.0
            total_weight = 0.0
            
            # Compute score for each JD section
            for jd_section in self.section_mapping.keys():
                score, matched_chunks = self.compute_section_score(jd_section, jd_chunks, cv_id)
                section_scores[jd_section] = score
                if matched_chunks:
                    section_details[jd_section] = matched_chunks
                    # Only count weight when we have matches to avoid penalizing missing sections
                    weight = self.section_weights.get(jd_section, 0.0)
                    total_score += score * weight
                    total_weight += weight
            
            # Normalize total score by sum of weights
            if total_weight > 0:
                total_score /= total_weight
            else:
                total_score = 0.0
            
            cv_scores.append({
                "cv_id": cv_id,
                "total_score": total_score,
                "section_scores": section_scores,
                "section_details": section_details
            })
        
        # Sort CVs by total score
        cv_scores.sort(key=lambda x: x["total_score"], reverse=True)
        logger.info(f"Ranked {len(cv_scores)} CVs from job_descriptions collection")
        if top_k_cvs is not None and top_k_cvs > 0:
            return cv_scores[:top_k_cvs]
        return cv_scores
    
    def print_results(self, results: List[Dict], show_details: bool = False):
        """Print ranked CVs with section-wise scores and optional details."""
        for i, result in enumerate(results):
            print(f"\n--- CV {i+1} (ID: {result['cv_id']}) ---")
            print(f"Total Score: {result['total_score']:.4f}")
            print("Section Scores:")
            for section, score in result["section_scores"].items():
                print(f"  {section}: {score:.4f}")
            if show_details and result.get("section_details"):
                print("Section Details:")
                for section, matches in result["section_details"].items():
                    print(f"  {section}:")
                    for match in matches:
                        similarity = match.get("similarity")
                        cv_section = match.get("cv_section")
                        print(f"    CV Section: {cv_section} | Similarity: {similarity:.4f}")
            print()

    def close(self) -> None:
        """Persist vector stores and perform any available cleanup."""
        try:
            self.cv_vectorstore.persist()
        except Exception:
            pass
        try:
            self.jd_vectorstore.persist()
        except Exception:
            pass

    def __enter__(self) -> "CVJDVectorSearch":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

# Example usage
if __name__ == "__main__":
    searcher = CVJDVectorSearch(
        cv_persist_dir="../../data/chroma_db",
        jd_persist_dir="../../data/jd_chroma_db",
        cv_collection_name="cv_sections",
        jd_collection_name="job_descriptions",
        model="mxbai-embed-large",
        top_k_per_section=5
    )
    results = searcher.search_and_score_cvs(top_k_cvs=5)
    searcher.print_results(results)