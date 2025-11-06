import json
import os
import numpy as np
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from rapidfuzz import fuzz
import hashlib
import requests
from dotenv import load_dotenv  # ✅ Load environment variables

# ✅ Load environment variables from .env file
load_dotenv()

os.environ["USE_TF"] = "0"

# ✅ Use HF_Token (your chosen env var)
HF_API_KEY = os.environ.get("HF_Token")

if not HF_API_KEY:
    raise ValueError(
        "❌ Hugging Face API token not found!\n"
        "Make sure your .env file contains: HF_Token=hf_your_token_here"
    )

print(f"✅ API Key loaded: {HF_API_KEY[:10]}... (length: {len(HF_API_KEY)})")

HF_RERANK_MODEL = "BAAI/bge-reranker-large"


# --- Helper functions ---
def normalize(text):
    return str(text).lower().strip() if text else ""


def fuzzy_match(target, candidate_list, threshold=80):
    if not target or not candidate_list:
        return False
    target_norm = normalize(target)
    for candidate in candidate_list:
        candidate_norm = normalize(candidate)
        if fuzz.token_set_ratio(target_norm, candidate_norm) >= threshold:
            return True
    return False


location_synonyms = {
    "us": ["usa", "united states", "america"],
    "uk": ["united kingdom", "england"],
    "remote": ["remote", "anywhere"]
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


def cross_encode_cloud(pairs):
    """Use Hugging Face Inference API reranker instead of local CrossEncoder."""
    url = f"https://api-inference.huggingface.co/models/{HF_RERANK_MODEL}"
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }
    results = []

    for job_text, doc_text in pairs:
        payload = {
            "inputs": {
                "source_sentence": job_text,
                "sentences": [doc_text]
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)

            if response.status_code == 503:
                print(f"⚠️ Model is loading, retrying in 10s...")
                import time
                time.sleep(10)
                response = requests.post(url, headers=headers, json=payload, timeout=60)

            response.raise_for_status()
            result = response.json()

            # ✅ Extract score properly
            if isinstance(result, list) and len(result) > 0 and "score" in result[0]:
                score = result[0]["score"]
            else:
                score = 0.0

            results.append(float(score))

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Error during API request: {e}")
            results.append(0.0)
            continue

    return results


# --- Main scoring function ---
def score_cv_against_job(cv_json_path, job_description_path, min_experience_years=2):
    weights = {
        "hard_filters": 0.25,
        "semantic_similarity": 0.45,
        "experience_alignment": 0.15,
        "education_alignment": 0.15
    }

    # ✅ Hugging Face embeddings (local)
    embeddings = OllamaEmbeddings(model="mxbai-embed-large")

    # Load job description
    try:
        with open(job_description_path, 'r', encoding='utf-8') as f:
            job_text = f.read().strip()
    except FileNotFoundError:
        print(f"❌ Job description file not found: {job_description_path}")
        return 0.0

    # Defaults (replace with LLM parsing if needed)
    job_req = {
        "required_skills": [],
        "required_certifications": [],
        "location_eligibility": "",
        "min_years_experience": min_experience_years,
        "required_education": ""
    }

    required_skills = set(normalize(s) for s in job_req.get("required_skills", []) if s)
    required_certifications = set(normalize(c) for c in job_req.get("required_certifications", []) if c)
    location_req = job_req.get("location_eligibility", "")
    min_years = job_req.get("min_years_experience", min_experience_years) or min_experience_years
    required_education = job_req.get("required_education", "")

    # Load CV
    try:
        with open(cv_json_path, 'r', encoding='utf-8') as f:
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
    print(f"DEBUG - Email: {email}")
    print(f"DEBUG - cv_id: {cv_id}")

    # --- Hard Score ---
    hard_score = 0.0
    total_weight = 0.0

    if required_skills:
        skill_matches = sum(1 for s in required_skills if fuzzy_match(s, candidate_skills))
        skill_fraction = skill_matches / len(required_skills)
        hard_score += skill_fraction * 0.5
        total_weight += 0.5

    if required_certifications:
        cert_matches = sum(1 for c in required_certifications if fuzzy_match(c, candidate_certifications))
        cert_fraction = cert_matches / len(required_certifications)
        hard_score += cert_fraction * 0.3
        total_weight += 0.3

    if location_req:
        hard_score += 0.2 if location_match(location_req, candidate_location) else 0.0
        total_weight += 0.2

    hard_score = (hard_score / total_weight * 100) if total_weight > 0 else 0.0

    # --- Semantic Similarity with Cloud Reranker ---
    try:
        vectorstore = Chroma(
            persist_directory="./chroma_db",
            embedding_function=embeddings,
            collection_name="cv_sections"
        )
        retrieved = vectorstore.get(where={"cv_id": cv_id})
        documents = retrieved.get("documents", [])
        metadatas = retrieved.get("metadatas", [])
        if not documents:
            print(f"⚠️ No embeddings found for CV: {cv_json_path}")
            return 0.0
    except Exception as e:
        print(f"⚠️ Error accessing Chroma: {e}")
        return 0.0

    section_scores = []
    for doc_text, metadata in zip(documents, metadatas):
        try:
            score = cross_encode_cloud([(job_text, doc_text)])[0]
            weight = 1.5 if metadata.get("section") in ["work_experience", "skills", "summary"] else 1.0
            section_scores.append(score * weight)
        except Exception as e:
            print(f"⚠️ Error computing cloud cross-encoder score: {e}")
            continue

    semantic_score = np.mean(section_scores) * 100 if section_scores else 0.0

    # --- Experience Alignment ---
    experience_score = min(years_of_experience / min_years, 1.0) * 100 if min_years > 0 else 100.0

    # --- Education Alignment ---
    education_score = fuzzy_education_match(required_education, candidate_education)

    # --- Hybrid Score ---
    hybrid_score = (
        hard_score * weights["hard_filters"] +
        semantic_score * weights["semantic_similarity"] +
        experience_score * weights["experience_alignment"] +
        education_score * weights["education_alignment"]
    )

    return round(hybrid_score, 2)


# --- Example usage ---
if __name__ == "__main__":
    cv_json_path = "./extracted_files/CV_Image.json"
    job_description_path = "./job_description.txt"
    score = score_cv_against_job(cv_json_path, job_description_path, min_experience_years=3)
    print(f"CV Hybrid Score: {score}/100")
