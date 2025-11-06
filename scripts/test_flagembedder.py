import os
import json
import numpy as np
from rapidfuzz import fuzz
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from dotenv import load_dotenv
from FlagEmbedding import FlagReranker
import hashlib
from sklearn.metrics.pairwise import cosine_similarity

# ✅ Load environment variables
load_dotenv()
HF_TOKEN = os.getenv("HF_Token")

if not HF_TOKEN:
    raise ValueError("❌ Hugging Face API token missing. Add HF_Token=your_key to .env")

# Initialize FlagReranker
reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=True)

# --- Helpers ---
def normalize(text):
    return str(text).lower().strip() if text else ""

def fuzzy_match(target, candidate_list, threshold=80):
    if not target or not candidate_list:
        return False
    target_norm = normalize(target)
    for candidate in candidate_list:
        if fuzz.token_set_ratio(target_norm, normalize(candidate)) >= threshold:
            return True
    return False

location_synonyms = {
    "us": ["usa", "united states", "america"],
    "uk": ["united kingdom", "england"],
    "remote": ["remote", "anywhere"],
}

def location_match(required, candidate):
    if not required or not candidate:
        return False
    req_norm = normalize(required)
    cand_norm = normalize(candidate)
    for synonym in location_synonyms.get(req_norm, [req_norm]):
        if synonym in cand_norm:
            return True
    return False

def fuzzy_education_match(required_edu, candidate_edu_list):
    if not required_edu or not candidate_edu_list:
        return 100.0
    if isinstance(required_edu, dict):
        degree = required_edu.get("degree", "")
        field = required_edu.get("field", "") or required_edu.get("field_of_study", "")
        required_str = f"{degree} in {field}".strip()
    else:
        required_str = str(required_edu)
    required_norm = normalize(required_str)
    max_ratio = 0
    for edu in candidate_edu_list:
        if isinstance(edu, dict):
            degree = edu.get("degree", "")
            field = edu.get("field_of_study", "")
            candidate_str = f"{degree} in {field}".strip()
        else:
            candidate_str = str(edu)
        ratio = fuzz.token_set_ratio(required_norm, normalize(candidate_str))
        max_ratio = max(max_ratio, ratio)
    return max_ratio

def hash_email(email):
    return hashlib.md5(email.lower().strip().encode()).hexdigest() if email else None

# --- FlagReranker scoring ---
def flag_rerank_score(query, passage, normalize_score=True):
    try:
        score = reranker.compute_score([query, passage])
        if normalize_score:
            import math
            score = 1 / (1 + math.exp(-score)) * 100  # sigmoid to 0–100
        return float(score)
    except Exception as e:
        print(f"⚠️ FlagReranker error: {e}")
        return 0.0

# --- NEW: Compute embedding similarity ---
def compute_embedding_similarity(cv_embeddings, job_embedding):
    """
    Compute cosine similarity between CV embeddings and job description embedding
    Returns a score from 0-100
    """
    if not cv_embeddings or job_embedding is None:
        return 0.0
    
    # Convert to numpy arrays
    cv_embeddings_array = np.array(cv_embeddings)
    job_embedding_array = np.array(job_embedding).reshape(1, -1)
    
    # Compute cosine similarity for each CV embedding chunk
    similarities = []
    for cv_emb in cv_embeddings_array:
        cv_emb_reshaped = cv_emb.reshape(1, -1)
        sim = cosine_similarity(cv_emb_reshaped, job_embedding_array)[0][0]
        similarities.append(sim)
    
    # Return average similarity as percentage
    avg_similarity = np.mean(similarities) if similarities else 0.0
    # Convert from [-1, 1] to [0, 100]
    return ((avg_similarity + 1) / 2) * 100

# --- NEW: Section-weighted embedding similarity ---
def compute_weighted_embedding_similarity(cv_embeddings_dict, job_embedding):
    """
    Compute weighted cosine similarity based on CV sections
    cv_embeddings_dict: {section_name: [embeddings]}
    """
    if not cv_embeddings_dict or job_embedding is None:
        return 0.0
    
    # Section weights
    section_weights = {
        "work_experience": 2.0,
        "skills": 1.8,
        "summary": 1.5,
        "projects": 1.3,
        "education": 1.0,
        "certifications": 1.0,
        "soft_skills": 0.8,
        "languages": 0.5,
        "hobbies": 0.3,
        "other": 0.5
    }
    
    job_embedding_array = np.array(job_embedding).reshape(1, -1)
    
    weighted_scores = []
    total_weight = 0.0
    
    for section, embeddings in cv_embeddings_dict.items():
        weight = section_weights.get(section, 1.0)
        
        # Compute average similarity for this section
        section_similarities = []
        for emb in embeddings:
            emb_array = np.array(emb).reshape(1, -1)
            sim = cosine_similarity(emb_array, job_embedding_array)[0][0]
            section_similarities.append(sim)
        
        if section_similarities:
            avg_section_sim = np.mean(section_similarities)
            weighted_scores.append(avg_section_sim * weight)
            total_weight += weight
    
    if total_weight == 0:
        return 0.0
    
    # Weighted average similarity
    weighted_avg = sum(weighted_scores) / total_weight
    # Convert from [-1, 1] to [0, 100]
    return ((weighted_avg + 1) / 2) * 100

# --- Main scoring function ---
def score_cv_against_job(cv_json_path, job_description_path, min_experience_years=2):
    weights = {
        "hard_filters": 0.15,
        "embedding_similarity": 0.35,      # NEW: Direct embedding comparison
        "semantic_reranking": 0.25,        # FlagReranker score
        "experience_alignment": 0.15,
        "education_alignment": 0.10,
    }

    # ✅ Ollama embeddings (local)
    embeddings = OllamaEmbeddings(model="mxbai-embed-large")

    # Load job description
    try:
        with open(job_description_path, "r", encoding="utf-8") as f:
            job_text = f.read().strip()
    except FileNotFoundError:
        print(f"❌ Job description file not found: {job_description_path}")
        return 0.0

    print(f"\n{'=' * 80}")
    print("GENERATING JOB DESCRIPTION EMBEDDING...")
    print('=' * 80)
    
    # Generate embedding for job description
    job_embedding = embeddings.embed_query(job_text)
    job_embedding_array = np.array(job_embedding)
    print(f"✓ Job embedding created (dimension: {len(job_embedding_array)})")

    job_req = {
        "required_skills": [],
        "required_certifications": [],
        "location_eligibility": "",
        "min_years_experience": min_experience_years,
        "required_education": "",
    }

    required_skills = set(normalize(s) for s in job_req.get("required_skills", []) if s)
    required_certifications = set(normalize(c) for c in job_req.get("required_certifications", []) if c)
    location_req = job_req.get("location_eligibility", "")
    min_years = job_req.get("min_years_experience", min_experience_years) or min_experience_years
    required_education = job_req.get("required_education", "")

    # Load CV JSON
    try:
        with open(cv_json_path, "r", encoding="utf-8") as f:
            cv_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading CV JSON {cv_json_path}: {e}")
        return 0.0

    structured_data = cv_data.get("CV_data", {}).get("structured_data", {})
    years_of_experience = float(structured_data.get("years_of_experience", 0.0) or 0.0)
    candidate_skills = [normalize(s) for s in structured_data.get("skills", []) + structured_data.get("soft_skills", []) if s]
    candidate_certifications = [normalize(c.get("name", "")) for c in structured_data.get("certifications", []) if isinstance(c, dict) and c.get("name")]
    candidate_location = normalize(structured_data.get("location", ""))
    candidate_education = structured_data.get("education", [])

    email = normalize(structured_data.get("email", ""))
    cv_id = hash_email(email) or os.path.splitext(os.path.basename(cv_json_path))[0]
    print(f"✓ Processing CV with cv_id: {cv_id}")

    # --- Hard Score ---
    print(f"\n{'─' * 80}")
    print("COMPUTING HARD FILTERS SCORE...")
    print('─' * 80)
    
    hard_score, total_weight = 0.0, 0.0
    if required_skills:
        skill_matches = sum(1 for s in required_skills if fuzzy_match(s, candidate_skills))
        hard_score += (skill_matches / len(required_skills)) * 0.5
        total_weight += 0.5
        print(f"  Skills match: {skill_matches}/{len(required_skills)}")
    if required_certifications:
        cert_matches = sum(1 for c in required_certifications if fuzzy_match(c, candidate_certifications))
        hard_score += (cert_matches / len(required_certifications)) * 0.3
        total_weight += 0.3
        print(f"  Certifications match: {cert_matches}/{len(required_certifications)}")
    if location_req:
        loc_match = location_match(location_req, candidate_location)
        hard_score += 0.2 if loc_match else 0.0
        total_weight += 0.2
        print(f"  Location match: {loc_match}")
    hard_score = (hard_score / total_weight * 100) if total_weight > 0 else 0.0
    print(f"✓ Hard filters score: {hard_score:.2f}/100")

    # --- Retrieve CV embeddings from Chroma ---
    print(f"\n{'─' * 80}")
    print("RETRIEVING CV EMBEDDINGS FROM CHROMA...")
    print('─' * 80)
    
    try:
        vectorstore = Chroma(
            persist_directory="./chroma_db",
            embedding_function=embeddings,
            collection_name="cv_sections",
        )
        retrieved = vectorstore.get(where={"cv_id": cv_id}, include=["embeddings", "metadatas", "documents"])
        
        cv_embeddings = retrieved.get("embeddings", [])
        metadatas = retrieved.get("metadatas", [])
        documents = retrieved.get("documents", [])
        
        if not cv_embeddings:
            print(f"⚠️ No embeddings found for CV: {cv_json_path}")
            return 0.0
        
        print(f"✓ Retrieved {len(cv_embeddings)} embedding chunks from CV")
        
        # Organize embeddings by section
        embeddings_by_section = {}
        for emb, meta in zip(cv_embeddings, metadatas):
            section = meta.get("section", "other")
            if section not in embeddings_by_section:
                embeddings_by_section[section] = []
            embeddings_by_section[section].append(emb)
        
        print(f"✓ Sections found: {list(embeddings_by_section.keys())}")
        
    except Exception as e:
        print(f"⚠️ Error accessing Chroma: {e}")
        return 0.0

    # --- NEW: Embedding Similarity Score ---
    print(f"\n{'─' * 80}")
    print("COMPUTING EMBEDDING SIMILARITY...")
    print('─' * 80)
    
    embedding_similarity_score = compute_weighted_embedding_similarity(
        embeddings_by_section, 
        job_embedding
    )
    print(f"✓ Embedding similarity score: {embedding_similarity_score:.2f}/100")
    
    # Show section-wise similarities
    print("\n  Section-wise similarities:")
    for section, section_embeddings in embeddings_by_section.items():
        section_sim = compute_embedding_similarity(section_embeddings, job_embedding)
        print(f"    {section}: {section_sim:.2f}/100")

    # --- Semantic Similarity with FlagReranker ---
    print(f"\n{'─' * 80}")
    print("COMPUTING SEMANTIC RERANKING SCORE...")
    print('─' * 80)
    
    section_scores = []
    for doc_text, metadata in zip(documents, metadatas):
        score = flag_rerank_score(job_text, doc_text, normalize_score=True)
        weight = 1.5 if metadata.get("section") in ["work_experience", "skills", "summary"] else 1.0
        section_scores.append(score * weight)
    semantic_score = np.mean(section_scores) if section_scores else 0.0
    print(f"✓ Semantic reranking score: {semantic_score:.2f}/100")

    # --- Experience Alignment ---
    print(f"\n{'─' * 80}")
    print("COMPUTING EXPERIENCE ALIGNMENT...")
    print('─' * 80)
    
    experience_score = min(years_of_experience / min_years, 1.0) * 100 if min_years > 0 else 100.0
    print(f"  Candidate experience: {years_of_experience} years")
    print(f"  Required experience: {min_years} years")
    print(f"✓ Experience score: {experience_score:.2f}/100")

    # --- Education Alignment ---
    print(f"\n{'─' * 80}")
    print("COMPUTING EDUCATION ALIGNMENT...")
    print('─' * 80)
    
    education_score = fuzzy_education_match(required_education, candidate_education)
    print(f"✓ Education score: {education_score:.2f}/100")

    # --- Hybrid Score ---
    print(f"\n{'=' * 80}")
    print("FINAL HYBRID SCORE CALCULATION")
    print('=' * 80)
    
    hybrid_score = (
        hard_score * weights["hard_filters"]
        + embedding_similarity_score * weights["embedding_similarity"]
        + semantic_score * weights["semantic_reranking"]
        + experience_score * weights["experience_alignment"]
        + education_score * weights["education_alignment"]
    )
    
    print(f"\nScore Breakdown:")
    print(f"  Hard Filters       ({weights['hard_filters']*100:.0f}%): {hard_score:.2f} → {hard_score * weights['hard_filters']:.2f}")
    print(f"  Embedding Similarity ({weights['embedding_similarity']*100:.0f}%): {embedding_similarity_score:.2f} → {embedding_similarity_score * weights['embedding_similarity']:.2f}")
    print(f"  Semantic Reranking ({weights['semantic_reranking']*100:.0f}%): {semantic_score:.2f} → {semantic_score * weights['semantic_reranking']:.2f}")
    print(f"  Experience         ({weights['experience_alignment']*100:.0f}%): {experience_score:.2f} → {experience_score * weights['experience_alignment']:.2f}")
    print(f"  Education          ({weights['education_alignment']*100:.0f}%): {education_score:.2f} → {education_score * weights['education_alignment']:.2f}")
    print(f"\n{'=' * 80}")
    print(f"FINAL HYBRID SCORE: {hybrid_score:.2f}/100")
    print('=' * 80)
    
    return round(hybrid_score, 2)

# --- Example usage ---
if __name__ == "__main__":
    cv_json_path = "./extracted_files/CV_Image.json"
    job_description_path = "./job_description.txt"
    score = score_cv_against_job(cv_json_path, job_description_path, min_experience_years=3)
    print(f"\n🎯 Final CV Score: {score}/100")