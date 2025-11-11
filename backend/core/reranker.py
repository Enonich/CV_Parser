import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import pymongo
import math
import re
from collections import Counter

try:
    from sentence_transformers import CrossEncoder as STCrossEncoder
    _HAS_ST = True
except Exception:
    _HAS_ST = False

from backend.core.identifiers import build_mongo_names, sanitize_fragment

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ✅ UNIFIED FIELD DEFINITIONS
JD_FIELDS = [
    "job_title", "required_skills", "required_qualifications", "preferred_skills",
    "education_requirements", "experience_requirements", "technical_skills",
    "soft_skills", "certifications", "responsibilities", "description", "full_text"
]

CV_FIELDS = [
    "summary", "years_of_experience", "work_experience", "education",
    "skills", "soft_skills", "certifications", "projects", "job_title",
    "languages", "awards", "publications"  # Extended fields
]


class BM25Scorer:
    """BM25 keyword-based scoring for CV-JD matching.
    
    Implements Okapi BM25 algorithm for lexical/keyword matching.
    Complements semantic search by catching exact term matches.
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """Initialize BM25 scorer.
        
        Args:
            k1: Term frequency saturation parameter (default 1.5)
            b: Length normalization parameter (default 0.75)
        """
        self.k1 = k1
        self.b = b
        
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple tokenization: lowercase, split on non-alphanumeric."""
        if not text:
            return []
        # Convert to lowercase and split on non-alphanumeric
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens
    
    def _compute_idf(self, query_tokens: List[str], corpus_texts: List[str]) -> Dict[str, float]:
        """Compute IDF (Inverse Document Frequency) for query terms.
        
        IDF = log((N - df + 0.5) / (df + 0.5) + 1)
        where N = total documents, df = document frequency of term
        """
        N = len(corpus_texts)
        if N == 0:
            return {}
        
        # Count documents containing each term
        df: Dict[str, int] = Counter()
        for text in corpus_texts:
            tokens = set(self._tokenize(text))
            for token in tokens:
                df[token] += 1
        
        # Compute IDF for query terms
        idf: Dict[str, float] = {}
        for term in set(query_tokens):
            doc_freq = df.get(term, 0)
            idf[term] = math.log((N - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
        
        return idf
    
    def score(self, query_text: str, corpus_texts: List[str]) -> List[float]:
        """Compute BM25 scores for each document in corpus against query.
        
        Args:
            query_text: Query text (e.g., JD text)
            corpus_texts: List of document texts (e.g., CV texts)
            
        Returns:
            List of BM25 scores, same length as corpus_texts
        """
        if not corpus_texts:
            return []
        
        query_tokens = self._tokenize(query_text)
        if not query_tokens:
            return [0.0] * len(corpus_texts)
        
        # Tokenize all documents
        doc_tokens_list = [self._tokenize(text) for text in corpus_texts]
        
        # Compute average document length
        doc_lengths = [len(tokens) for tokens in doc_tokens_list]
        avgdl = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 0.0
        
        # Compute IDF
        idf = self._compute_idf(query_tokens, corpus_texts)
        
        # Compute BM25 score for each document
        scores: List[float] = []
        for doc_tokens, doc_len in zip(doc_tokens_list, doc_lengths):
            if doc_len == 0:
                scores.append(0.0)
                continue
            
            # Count term frequencies in document
            tf = Counter(doc_tokens)
            
            # Compute BM25 score
            score = 0.0
            for term in query_tokens:
                if term not in tf:
                    continue
                
                term_freq = tf[term]
                term_idf = idf.get(term, 0.0)
                
                # BM25 formula
                numerator = term_freq * (self.k1 + 1)
                denominator = term_freq + self.k1 * (1 - self.b + self.b * (doc_len / avgdl))
                score += term_idf * (numerator / denominator)
            
            scores.append(score)
        
        return scores
    
    def score_with_saturation(
        self,
        query_text: str,
        corpus_texts: List[str],
        k_strategy: str = "median",
        min_k: float = 1.0
    ) -> Tuple[List[float], float]:
        """Compute BM25 scores then apply saturation normalization.

        Saturation formula: norm = raw / (raw + k)
        Where k is chosen for stability across subsets.

        Args:
            query_text: Query text (JD aggregate)
            corpus_texts: List of CV texts
            k_strategy: How to choose k ("median" | "mean" | numeric string)
            min_k: Floor value to prevent division explosion
        Returns:
            (normalized_scores, k_used)
        """
        raw_scores = self.score(query_text, corpus_texts)
        if not raw_scores:
            return ([0.0] * len(corpus_texts), min_k)
        # Determine k
        try:
            if k_strategy == "median":
                import statistics
                k_val = statistics.median(raw_scores)
            elif k_strategy == "mean":
                k_val = sum(raw_scores) / max(len(raw_scores), 1)
            else:
                k_val = float(k_strategy)
        except Exception:
            k_val = sum(raw_scores) / max(len(raw_scores), 1)
        k_val = max(k_val, min_k)
        normalized = [ (s / (s + k_val)) if s > 0 else 0.0 for s in raw_scores ]
        return normalized, k_val


class CVJDReranker:
    """Reranks CVs against job descriptions using cross-encoder models.
    
    Combines production-ready MongoDB integration with clean text construction logic.
    """
    
    def __init__(
        self,
        mongo_uri: str,
        mongo_db: str = "cv_db",
        cv_collection: str = "cvs",
        jd_collection: str = "job_descriptions",
        model_name: str = "BAAI/bge-reranker-base"
    ):
        """Initialize MongoDB client and cross-encoder model."""
        # Initialize MongoDB
        try:
            self.mongo_client = pymongo.MongoClient(mongo_uri)
            self.cv_db = self.mongo_client[mongo_db]
            self.cv_collection = self.cv_db[cv_collection]
            self.jd_collection = self.cv_db[jd_collection]
            logger.info("✅ MongoDB client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}")
            raise ValueError("MongoDB connection failed. Provide a valid mongo_uri.")
        
        # Initialize BM25 scorer
        self.bm25_scorer = BM25Scorer(k1=1.5, b=0.75)
        logger.info("✅ BM25 scorer initialized")
        
        # Initialize cross-encoder with optimal path detection
        try:
            self.model_name = model_name
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.use_st = False
            
            if _HAS_ST:
                self.cross_encoder = STCrossEncoder(model_name, device=self.device)
                self.use_st = True
                self.tokenizer = self.cross_encoder.tokenizer
                logger.info(f"✅ Using sentence-transformers CrossEncoder on {self.device}")
            else:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.cross_encoder = AutoModelForSequenceClassification.from_pretrained(model_name)
                self.cross_encoder.to(self.device)
                logger.info(f"✅ Using transformers model on {self.device}")
        except Exception as e:
            logger.error(f"Failed to initialize cross-encoder: {e}")
            raise RuntimeError(f"Failed to load model {model_name}")

    # ========================================
    # CORE TEXT CONSTRUCTION (UNIFIED)
    # ========================================
    
    def _build_text_from_doc(self, doc: Dict[str, Any], fields: List[str]) -> str:
        """Build structured text from document using specified fields.
        
        Handles different data types intelligently:
        - years_of_experience: Formatted as readable text
        - Lists: Joined with separator
        - Dicts: Key-value pairs
        - Strings: Cleaned and stripped
        """
        parts: List[str] = []
        
        for field in fields:
            val = doc.get(field)
            if val is None or val == "":
                continue
            
            # Special handling for experience
            if field == "years_of_experience":
                parts.append(f"{val} years experience")
            # Lists: ["SQL", "Python"] → "SQL | Python"
            elif isinstance(val, list):
                list_str = " | ".join(str(x) for x in val if x)
                if list_str:
                    parts.append(list_str)
            # Dicts: {"minimum_years": "2"} → "minimum_years: 2"
            elif isinstance(val, dict):
                dict_str = " | ".join(f"{k}: {v}" for k, v in val.items() if v)
                if dict_str:
                    parts.append(dict_str)
            # Numbers (except years_of_experience already handled)
            elif isinstance(val, (int, float)) and field != "years_of_experience":
                parts.append(str(val))
            # Strings
            elif isinstance(val, str) and val.strip():
                parts.append(val.strip())
        
        return "\n".join(p for p in parts if p)

    # ========================================
    # CORE SCORING (UNIFIED)
    # ========================================
    
    def _score_pairs(self, pairs: List[List[str]], batch_size: int = 8) -> List[float]:
        """Score CV-JD pairs using cross-encoder with optimal batching.
        
        Args:
            pairs: List of [jd_text, cv_text] pairs
            batch_size: Batch size for processing
            
        Returns:
            List of relevance scores (higher = more relevant)
        """
        if not pairs:
            return []
        
        max_length = getattr(self.tokenizer, 'model_max_length', 512)
        scores: List[float] = []
        
        # Optimal path: sentence-transformers CrossEncoder
        if self.use_st:
            try:
                scores = self.cross_encoder.predict(pairs).tolist()
                return scores
            except Exception as e:
                logger.warning(f"Sentence-transformers path failed, falling back to raw transformers: {e}")
                self.use_st = False  # Disable for future calls
        
        # Fallback: Raw transformers with batching
        for i in range(0, len(pairs), batch_size):
            batch_pairs = pairs[i:i + batch_size]
            try:
                features = self.tokenizer(
                    batch_pairs,
                    padding=True,
                    truncation=True,
                    max_length=max_length,
                    return_tensors="pt"
                ).to(self.device)
                
                with torch.no_grad():
                    logits = self.cross_encoder(**features).logits
                    
                    # Apply sigmoid normalization for better score distribution
                    if logits.ndim == 2 and logits.shape[1] == 1:
                        batch_scores = torch.sigmoid(logits.squeeze(1))
                    else:
                        batch_scores = torch.sigmoid(logits[:, 0])
                    
                    scores.extend(batch_scores.cpu().tolist())
            except Exception as e:
                logger.error(f"Scoring batch {i//batch_size + 1} failed: {e}")
                scores.extend([0.0] * len(batch_pairs))
        
        return scores

    # ========================================
    # SCORE CALIBRATION & TOKEN ESTIMATION
    # ========================================

    @staticmethod
    def _calibrate_scores(scores: List[float], mode: Optional[str]) -> List[float]:
        if not scores or mode is None:
            return scores
        if mode == 'minmax':
            mn = min(scores); mx = max(scores)
            if mx > mn:
                return [(s - mn)/(mx-mn) for s in scores]
            return [0.0 for _ in scores]
        if mode == 'zscore':
            import math
            mean = sum(scores)/len(scores)
            var = sum((s-mean)**2 for s in scores)/len(scores)
            if var <= 0:
                return [0.0 for _ in scores]
            std = math.sqrt(var)
            return [(s-mean)/std for s in scores]
        return scores

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text)//4

    def _compute_bm25_scores(
        self,
        jd_text: str,
        cv_texts: List[str],
        k_strategy: str = "median"
    ) -> Tuple[List[float], float]:
        """Compute BM25 saturation-normalized scores and k.

        Returns tuple (scores, k_used).
        """
        if not jd_text or not cv_texts:
            return ([0.0] * len(cv_texts), 1.0)
        try:
            scores, k_val = self.bm25_scorer.score_with_saturation(
                query_text=jd_text,
                corpus_texts=cv_texts,
                k_strategy=k_strategy,
                min_k=1.0
            )
            return scores, k_val
        except Exception as e:
            logger.error(f"BM25 saturation scoring failed: {e}")
            return ([0.0] * len(cv_texts), 1.0)

    # ========================================
    # DOCUMENT FETCHING (IMPROVED)
    # ========================================
    
    def _fetch_jd_doc(
        self,
        company_name: str,
        job_title: str,
        jd_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch JD document with comprehensive fallback logic.
        
        Priority:
        1. Dynamic collection (company-specific)
        2. Static collection with exact match
        3. Sanitized field match
        4. Case-insensitive regex match
        """
        # Try dynamic collection first
        try:
            db_name_dyn, _, jd_coll_dyn_name = build_mongo_names(company_name, job_title)
            dyn_db = self.mongo_client[db_name_dyn]
            dyn_jd_coll = dyn_db[jd_coll_dyn_name]
            
            # If jd_id provided, try exact match first
            if jd_id:
                jd_doc = dyn_jd_coll.find_one({"_id": jd_id})
                if jd_doc:
                    return jd_doc
                # Try sanitized jd_id
                jd_doc = dyn_jd_coll.find_one({"_id": sanitize_fragment(jd_id)})
                if jd_doc:
                    return jd_doc
            
            # Load all docs from job-specific collection (simplified approach)
            jd_docs = list(dyn_jd_coll.find({}))
            if jd_docs:
                return jd_docs[0]
        except Exception as e:
            logger.warning(f"Dynamic JD fetch failed: {e}")
        
        # Fallback to static collection
        try:
            jd_doc = self.jd_collection.find_one({
                "company_name": company_name,
                "job_title": job_title
            })
            if jd_doc:
                return jd_doc
            jd_doc = self.jd_collection.find_one({
                "company_name_sanitized": sanitize_fragment(company_name),
                "job_title_sanitized": sanitize_fragment(job_title)
            })
            if jd_doc:
                return jd_doc
            jd_doc = self.jd_collection.find_one({
                "company_name": {"$regex": f"^{company_name}$", "$options": "i"},
                "job_title": {"$regex": f"^{job_title}$", "$options": "i"}
            })
            return jd_doc
        except Exception as e:
            logger.error(f"Static JD fallback failed: {e}")
            return None

    def _fetch_cv_doc(
        self,
        cv_id: str,
        company_name: Optional[str] = None,
        job_title: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch CV document from dynamic or static collection."""
        if company_name and job_title:
            try:
                db_name_dyn, cv_coll_dyn_name, _ = build_mongo_names(company_name, job_title)
                dyn_db = self.mongo_client[db_name_dyn]
                dyn_cv_coll = dyn_db[cv_coll_dyn_name]
                cv_doc = dyn_cv_coll.find_one({"_id": cv_id})
                if cv_doc:
                    return cv_doc
                cv_doc = dyn_cv_coll.find_one({"cv_id": cv_id})
                if cv_doc:
                    return cv_doc
            except Exception as e:
                logger.warning(f"Dynamic CV fetch failed for {cv_id}: {e}")
        try:
            cv_doc = self.cv_collection.find_one({"_id": cv_id})
            if cv_doc:
                return cv_doc
            return self.cv_collection.find_one({"cv_id": cv_id})
        except Exception as e:
            logger.error(f"Static CV fallback failed for {cv_id}: {e}")
            return None

    def rerank_cvs_direct(
        self,
        cv_results: List[Dict],
        jd_doc: Dict[str, Any],
        batch_size: int = 8,
        calibrate: Optional[str] = None,
        with_meta: bool = False
    ) -> Union[List[Dict], Tuple[List[Dict], Dict[str, Any]]]:
        jd_text = self._build_text_from_doc(jd_doc, JD_FIELDS)
        meta: Dict[str, Any] = {
            "mode": "direct",
            "model_path": "sentence-transformers" if self.use_st else "hf",
            "calibration": calibrate,
            "jd_char_len": len(jd_text),
            "jd_token_est": self._estimate_tokens(jd_text),
            "cv_count": len(cv_results),
            "missing_cv_count": 0
        }
        if not jd_text:
            logger.warning("JD text empty; skipping rerank")
            for r in cv_results:
                r["cross_encoder_score"] = 0.0
                r["ce_status"] = "missing_jd"
            return (cv_results, meta) if with_meta else cv_results
        cv_texts, valid_results = [], []
        for result in cv_results:
            cv_text = self._build_text_from_doc(result, CV_FIELDS)
            if cv_text:
                cv_texts.append(cv_text)
                valid_results.append(result)
                result["ce_status"] = "ok"
            else:
                result["cross_encoder_score"] = 0.0
                result["ce_status"] = "no_text"
                meta["missing_cv_count"] += 1
        if not cv_texts:
            logger.warning("No CV texts built; returning original order")
            return (cv_results, meta) if with_meta else cv_results
        
        # Compute cross-encoder scores
        pairs = [[jd_text, cv_text] for cv_text in cv_texts]
        ce_scores = self._score_pairs(pairs, batch_size)
        ce_scores = self._calibrate_scores(ce_scores, calibrate)

        # Compute BM25 scores (saturation normalized)
        bm25_scores, bm25_k = self._compute_bm25_scores(jd_text, cv_texts, k_strategy="median")
        meta["bm25_normalization"] = {"method": "saturation", "k": bm25_k, "strategy": "median"}

        # Assign scores to results
        for result, ce_score, bm25_score in zip(valid_results, ce_scores, bm25_scores):
            result["cross_encoder_score"] = float(ce_score)
            result["bm25_score"] = float(bm25_score)

        # Compute per-section cross-encoder scores
        section_ce_scores: Dict[str, List[float]] = {}
        for jd_field in JD_FIELDS:
            jd_section_text = self._build_text_from_doc(jd_doc, [jd_field])
            if jd_section_text:
                section_pairs = [[jd_section_text, cv_text] for cv_text in cv_texts]
                section_scores = self._score_pairs(section_pairs, batch_size)
                section_scores = self._calibrate_scores(section_scores, calibrate)
                section_ce_scores[jd_field] = section_scores
            else:
                section_ce_scores[jd_field] = [0.0] * len(cv_texts)

        for i, result in enumerate(valid_results):
            result["cross_encoder_section_scores"] = {field: scores[i] for field, scores in section_ce_scores.items()}

        sorted_results = sorted(cv_results, key=lambda x: x.get("cross_encoder_score", 0.0), reverse=True)
        if with_meta:
            if cv_texts:
                meta["avg_cv_char_len"] = sum(len(t) for t in cv_texts) / len(cv_texts)
                meta["avg_cv_token_est"] = sum(self._estimate_tokens(t) for t in cv_texts) / len(cv_texts)
            return sorted_results, meta
        return sorted_results

    def rerank_cvs_for_job(
        self,
        cv_results: List[Dict],
        company_name: str,
        job_title: str,
        batch_size: int = 8,
        calibrate: Optional[str] = None,
        with_meta: bool = False
    ) -> Union[List[Dict], Tuple[List[Dict], Dict[str, Any]]]:
        jd_doc = self._fetch_jd_doc(company_name, job_title)
        meta: Dict[str, Any] = {
            "mode": "for_job",
            "company": company_name,
            "job_title": job_title,
            "model_path": "sentence-transformers" if self.use_st else "hf",
            "calibration": calibrate,
            "cv_count": len(cv_results),
            "missing_cv_count": 0
        }
        if not jd_doc:
            logger.warning(f"No JD found for {company_name}/{job_title}; skipping rerank")
            for r in cv_results:
                r["cross_encoder_score"] = 0.0
                r["ce_status"] = "missing_jd"
            return (cv_results, meta) if with_meta else cv_results
        jd_text = self._build_text_from_doc(jd_doc, JD_FIELDS)
        meta["jd_char_len"] = len(jd_text)
        meta["jd_token_est"] = self._estimate_tokens(jd_text)
        if not jd_text:
            logger.warning("JD text empty after construction; skipping rerank")
            for r in cv_results:
                r["cross_encoder_score"] = 0.0
                r["ce_status"] = "missing_jd"
            return (cv_results, meta) if with_meta else cv_results
        cv_id_list = [r.get("cv_id") for r in cv_results if r.get("cv_id")]
        cv_docs_map: Dict[str, Dict[str, Any]] = {}
        if cv_id_list:
            try:
                db_name_dyn, cv_coll_dyn_name, _ = build_mongo_names(company_name, job_title)
                dyn_db = self.mongo_client[db_name_dyn]
                dyn_cv_coll = dyn_db[cv_coll_dyn_name]
                dyn_docs = list(dyn_cv_coll.find({"$or": [
                    {"_id": {"$in": cv_id_list}},
                    {"cv_id": {"$in": cv_id_list}}
                ]}))
                for d in dyn_docs:
                    key = d.get("_id") or d.get("cv_id")
                    if key:
                        cv_docs_map[key] = d
            except Exception as e:
                logger.warning(f"Batch dynamic CV fetch failed: {e}")
            if not cv_docs_map:
                try:
                    static_docs = list(self.cv_collection.find({"$or": [
                        {"_id": {"$in": cv_id_list}},
                        {"cv_id": {"$in": cv_id_list}}
                    ]}))
                    for d in static_docs:
                        key = d.get("_id") or d.get("cv_id")
                        if key:
                            cv_docs_map[key] = d
                except Exception as e:
                    logger.warning(f"Static batch CV fetch failed: {e}")
        cv_texts: List[str] = []
        valid_results: List[Dict] = []
        for result in cv_results:
            cv_id = result.get("cv_id")
            if not cv_id:
                result["cross_encoder_score"] = 0.0
                result["ce_status"] = "missing_cv"
                meta["missing_cv_count"] += 1
                continue
            cv_doc = cv_docs_map.get(cv_id)
            if not cv_doc:
                result["cross_encoder_score"] = 0.0
                result["ce_status"] = "missing_cv"
                meta["missing_cv_count"] += 1
                continue
            cv_text = self._build_text_from_doc(cv_doc, CV_FIELDS)
            if not cv_text:
                cv_text = cv_doc.get("full_text", "")
            if cv_text:
                cv_texts.append(cv_text)
                valid_results.append(result)
                result["ce_status"] = "ok"
            else:
                result["cross_encoder_score"] = 0.0
                result["ce_status"] = "no_text"
                meta["missing_cv_count"] += 1
        if not cv_texts:
            logger.warning("No CV texts available for reranking")
            return (cv_results, meta) if with_meta else cv_results
        
        # Compute cross-encoder scores
        pairs = [[jd_text, cv_text] for cv_text in cv_texts]
        ce_scores = self._score_pairs(pairs, batch_size)
        ce_scores = self._calibrate_scores(ce_scores, calibrate)

        # Compute BM25 scores (saturation normalized)
        bm25_scores, bm25_k = self._compute_bm25_scores(jd_text, cv_texts, k_strategy="median")
        meta["bm25_normalization"] = {"method": "saturation", "k": bm25_k, "strategy": "median"}

        # Assign scores to results
        for result, ce_score, bm25_score in zip(valid_results, ce_scores, bm25_scores):
            result["cross_encoder_score"] = float(ce_score)
            result["bm25_score"] = float(bm25_score)

        cv_results.sort(key=lambda x: x.get("cross_encoder_score", 0.0), reverse=True)
        if cv_texts:
            meta["avg_cv_char_len"] = sum(len(t) for t in cv_texts) / len(cv_texts)
            meta["avg_cv_token_est"] = sum(self._estimate_tokens(t) for t in cv_texts) / len(cv_texts)
        if with_meta:
            return cv_results, meta
        logger.info(f"✅ Reranked {len(cv_results)} CVs for company='{company_name}' job='{job_title}'")
        return cv_results

    def rerank_cvs_with_jd_id(
        self,
        cv_results: List[Dict],
        company_name: str,
        job_title: str,
        jd_id: str,
        batch_size: int = 8,
        calibrate: Optional[str] = None,
        with_meta: bool = False
    ) -> Union[List[Dict], Tuple[List[Dict], Dict[str, Any]]]:
        jd_doc = self._fetch_jd_doc(company_name, job_title, jd_id)
        meta: Dict[str, Any] = {
            "mode": "with_jd_id",
            "company": company_name,
            "job_title": job_title,
            "jd_id": jd_id,
            "model_path": "sentence-transformers" if self.use_st else "hf",
            "calibration": calibrate,
            "cv_count": len(cv_results),
            "missing_cv_count": 0
        }
        if not jd_doc:
            logger.warning(f"JD id '{jd_id}' not found; skipping rerank")
            for r in cv_results:
                r["cross_encoder_score"] = 0.0
                r["ce_status"] = "missing_jd"
            return (cv_results, meta) if with_meta else cv_results
        jd_text = self._build_text_from_doc(jd_doc, JD_FIELDS)
        meta["jd_char_len"] = len(jd_text)
        meta["jd_token_est"] = self._estimate_tokens(jd_text)
        if not jd_text:
            logger.warning(f"JD id '{jd_id}' produced empty text; skipping rerank")
            for r in cv_results:
                r["cross_encoder_score"] = 0.0
                r["ce_status"] = "missing_jd"
            return (cv_results, meta) if with_meta else cv_results
        cv_id_list = [r.get("cv_id") for r in cv_results if r.get("cv_id")]
        cv_docs_map: Dict[str, Dict[str, Any]] = {}
        if cv_id_list:
            try:
                db_name_dyn, cv_coll_dyn_name, _ = build_mongo_names(company_name, job_title)
                dyn_db = self.mongo_client[db_name_dyn]
                dyn_cv_coll = dyn_db[cv_coll_dyn_name]
                dyn_docs = list(dyn_cv_coll.find({"$or": [
                    {"_id": {"$in": cv_id_list}},
                    {"cv_id": {"$in": cv_id_list}}
                ]}))
                for d in dyn_docs:
                    key = d.get("_id") or d.get("cv_id")
                    if key:
                        cv_docs_map[key] = d
            except Exception as e:
                logger.warning(f"Batch dynamic CV fetch failed: {e}")
            if not cv_docs_map:
                try:
                    static_docs = list(self.cv_collection.find({"$or": [
                        {"_id": {"$in": cv_id_list}},
                        {"cv_id": {"$in": cv_id_list}}
                    ]}))
                    for d in static_docs:
                        key = d.get("_id") or d.get("cv_id")
                        if key:
                            cv_docs_map[key] = d
                except Exception as e:
                    logger.warning(f"Static batch CV fetch failed: {e}")
        cv_texts: List[str] = []
        valid_results: List[Dict] = []
        for result in cv_results:
            cv_id = result.get("cv_id")
            if not cv_id:
                result["cross_encoder_score"] = 0.0
                result["ce_status"] = "missing_cv"
                meta["missing_cv_count"] += 1
                continue
            cv_doc = cv_docs_map.get(cv_id)
            if not cv_doc:
                result["cross_encoder_score"] = 0.0
                result["ce_status"] = "missing_cv"
                meta["missing_cv_count"] += 1
                continue
            cv_text = self._build_text_from_doc(cv_doc, CV_FIELDS)
            if not cv_text:
                cv_text = cv_doc.get("full_text", "")
            if cv_text:
                cv_texts.append(cv_text)
                valid_results.append(result)
                result["ce_status"] = "ok"
            else:
                result["cross_encoder_score"] = 0.0
                result["ce_status"] = "no_text"
                meta["missing_cv_count"] += 1
        if not cv_texts:
            logger.warning("No CV texts available for reranking with jd_id")
            return (cv_results, meta) if with_meta else cv_results
        
        # Compute cross-encoder scores
        pairs = [[jd_text, cv_text] for cv_text in cv_texts]
        ce_scores = self._score_pairs(pairs, batch_size)
        ce_scores = self._calibrate_scores(ce_scores, calibrate)

        # Compute BM25 scores (saturation normalized)
        bm25_scores, bm25_k = self._compute_bm25_scores(jd_text, cv_texts, k_strategy="median")
        meta["bm25_normalization"] = {"method": "saturation", "k": bm25_k, "strategy": "median"}

        # Assign scores to results
        for result, ce_score, bm25_score in zip(valid_results, ce_scores, bm25_scores):
            result["cross_encoder_score"] = float(ce_score)
            result["bm25_score"] = float(bm25_score)

        cv_results.sort(key=lambda x: x.get("cross_encoder_score", 0.0), reverse=True)
        if cv_texts:
            meta["avg_cv_char_len"] = sum(len(t) for t in cv_texts) / len(cv_texts)
            meta["avg_cv_token_est"] = sum(self._estimate_tokens(t) for t in cv_texts) / len(cv_texts)
        if with_meta:
            return cv_results, meta
        logger.info(f"✅ Reranked {len(cv_results)} CVs using jd_id='{jd_id}' company='{company_name}' job='{job_title}'")
        return cv_results


sample_jd = {
    "job_title": "Data Analyst","required_skills": ["SQL", "Python", "Excel"],"technical_skills": ["SQL", "Python (pandas)", "Excel"],"experience_requirements": {"minimum_years": "2"}
}
sample_cvs = [
    {
        "cv_id": "cv_001","email": "candidate1@example.com","total_score": 0.85,"summary": "Data Analyst with SQL and Python experience","years_of_experience": 3.5,"skills": ["SQL", "Python", "Tableau"],
    },
    {
        "cv_id": "cv_002","email": "candidate2@example.com","total_score": 0.82,"summary": "Business Analyst with Excel skills","years_of_experience": 1.5,"skills": ["Excel", "PowerPoint"],
    }
]
try:
    reranker = CVJDReranker(mongo_uri="mongodb://localhost:27017/", mongo_db="cv_db")
    results, meta = reranker.rerank_cvs_direct(sample_cvs, sample_jd, with_meta=True, calibrate='minmax')
    print(meta)
    for r in results:
        print(r['cv_id'], r['cross_encoder_score'], r['ce_status'])
except Exception as e:
    print('Error initializing reranker (likely no MongoDB running):', e)