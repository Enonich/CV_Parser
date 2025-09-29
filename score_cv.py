import json
import os
import numpy as np
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain.prompts import PromptTemplate
from rapidfuzz import fuzz
import hashlib



# --- Helper functions ---
def normalize(text):
    return text.lower().strip()

def fuzzy_match(target, candidate_list, threshold=80):
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
    req_norm = normalize(required)
    cand_norm = normalize(candidate)
    for synonym in location_synonyms.get(req_norm, [req_norm]):
        if synonym in cand_norm:
            return True
    return False

def fuzzy_education_match(required_edu, candidate_edu_list):
    """
    Compare required education (string or dict) against candidate education list (dicts).
    Returns best fuzzy match score (0-100).
    """
    if not required_edu:
        return 100.0  # no requirement = full score

    # Convert required_edu into string if it's a dict
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
    return hashlib.md5(email.lower().strip().encode()).hexdigest()

# --- Main scoring function ---
def score_cv_against_job(cv_json_path, job_description_path, min_experience_years=2):
    weights = {
        "hard_filters": 0.30,
        "semantic_similarity": 0.40,
        "experience_alignment": 0.15,
        "education_alignment": 0.15
    }

    embeddings = OllamaEmbeddings(model="mxbai-embed-large")

    # Load job description
    try:
        with open(job_description_path, 'r', encoding='utf-8') as f:
            job_text = f.read().strip()
    except FileNotFoundError:
        print(f"❌ Job description file not found: {job_description_path}")
        return 0.0

    # Parse job requirements using LLM
    llm = ChatOllama(model="llama3.2:latest", format="json")
    prompt_template = PromptTemplate.from_template("""
        Extract the following from the job description as JSON:
        - required_skills: list of required skills
        - required_certifications: list of required certifications
        - location_eligibility: required location or "remote"
        - min_years_experience: minimum years of experience
        - required_education: required degree and field

        Job Description:
        {job_text}

        Output only JSON.
    """)
    chain = prompt_template | llm
    response = chain.invoke({"job_text": job_text})
    try:
        job_req = json.loads(response.content)
    except json.JSONDecodeError:
        print("⚠️ Error parsing LLM response; using defaults.")
        job_req = {
            "required_skills": [],
            "required_certifications": [],
            "location_eligibility": "",
            "min_years_experience": min_experience_years,
            "required_education": ""
        }

    required_skills = set(normalize(s) for s in job_req.get("required_skills", []))
    required_certifications = set(normalize(c) for c in job_req.get("required_certifications", []))
    location_req = job_req.get("location_eligibility", "").lower()
    min_years = job_req.get("min_years_experience", min_experience_years)
    required_education = job_req.get("required_education", "")

    # Load CV
    try:
        with open(cv_json_path, 'r', encoding='utf-8') as f:
            cv_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading CV JSON {cv_json_path}: {e}")
        return 0.0

    structured_data = cv_data.get("CV_data", {}).get("structured_data", {})
    years_of_experience = structured_data.get("years_of_experience", 0.0)
    candidate_skills = [normalize(s) for s in structured_data.get("skills", []) + structured_data.get("soft_skills", [])]
    candidate_certifications = [normalize(c.get("name","")) for c in structured_data.get("certifications", []) if isinstance(c, dict)]
    candidate_location = structured_data.get("location", "").lower()
    candidate_education = structured_data.get("education", [])

    # --- Generate cv_id from hashed email ---
    email = structured_data.get("email", "")
    if email:
        cv_id = hash_email(email)
    else:
        cv_id = os.path.splitext(os.path.basename(cv_json_path))[0]

    # --- Hard Score ---
    hard_score = 0.0
    skill_matches = sum(1 for s in required_skills if fuzzy_match(s, candidate_skills))
    skill_fraction = skill_matches / len(required_skills) if required_skills else 1.0
    hard_score += skill_fraction * 0.5

    cert_matches = sum(1 for c in required_certifications if fuzzy_match(c, candidate_certifications))
    cert_fraction = cert_matches / len(required_certifications) if required_certifications else 1.0
    hard_score += cert_fraction * 0.3

    if location_req:
        hard_score += 0.2 if location_match(location_req, candidate_location) else 0.0

    hard_score = hard_score * 100

    # --- Semantic Similarity ---
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

    try:
        job_vector = embeddings.embed_query(job_text)
    except Exception as e:
        print(f"⚠️ Error embedding job description: {e}")
        return 0.0

    section_scores = []
    for doc_text, metadata in zip(documents, metadatas):
        try:
            doc_vector = embeddings.embed_query(doc_text)
            similarity = np.dot(job_vector, doc_vector) / (np.linalg.norm(job_vector) * np.linalg.norm(doc_vector))
            weight = 1.5 if metadata.get("section") in ["work_experience", "skills", "summary"] else 1.0
            section_scores.append(similarity * weight)
        except:
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
