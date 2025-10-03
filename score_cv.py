import json
import os
import numpy as np
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain.prompts import PromptTemplate
from rapidfuzz import fuzz
import hashlib

from jd_extractor import JDExtractor  # assuming this is defined

class CVJobScorer:
    def __init__(self, min_experience_years=2, persist_directory="./chroma_db"):
        self.min_experience_years = min_experience_years
        self.embeddings = OllamaEmbeddings(model="mxbai-embed-large")
        self.llm = ChatOllama(model="llama3.2:latest", format="json")
        self.vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=self.embeddings,
            collection_name="cv_sections"
        )
        self.extractor = JDExtractor()

        # scoring weights
        self.weights = {
            "hard_filters": 0.25,
            "semantic_similarity": 0.45,
            "experience_alignment": 0.15,
            "education_alignment": 0.15
        }

        # location synonyms
        self.location_synonyms = {
            "us": ["usa", "united states", "america"],
            "uk": ["united kingdom", "england"],
            "remote": ["remote", "anywhere"],
            "gh": ["ghana"]
        }

    # --- Utility Functions ---
    @staticmethod
    def normalize(text):
        return text.lower().strip()

    @staticmethod
    def fuzzy_match(target, candidate_list, threshold=80):
        target_norm = CVJobScorer.normalize(target)
        for candidate in candidate_list:
            candidate_norm = CVJobScorer.normalize(candidate)
            if fuzz.token_set_ratio(target_norm, candidate_norm) >= threshold:
                return True
        return False

    def location_match(self, required, candidate):
        req_norm = self.normalize(required)
        cand_norm = self.normalize(candidate)
        for synonym in self.location_synonyms.get(req_norm, [req_norm]):
            if synonym in cand_norm:
                return True
        return False

    @staticmethod
    def fuzzy_education_match(required_edu, candidate_edu_list):
        if not required_edu:
            return 100.0

        if isinstance(required_edu, dict):
            degree = required_edu.get("degree", "")
            field = required_edu.get("field", "") or required_edu.get("field_of_study", "")
            required_str = f"{degree} in {field}".strip()
        else:
            required_str = str(required_edu)

        required_norm = CVJobScorer.normalize(required_str)
        max_ratio = 0

        for edu in candidate_edu_list:
            if isinstance(edu, dict):
                degree = edu.get("degree", "")
                field = edu.get("field_of_study", "")
                candidate_str = f"{degree} in {field}".strip()
            else:
                candidate_str = str(edu)
            ratio = fuzz.token_set_ratio(required_norm, CVJobScorer.normalize(candidate_str))
            max_ratio = max(max_ratio, ratio)

        return max_ratio

    @staticmethod
    def hash_email(email):
        return hashlib.md5(email.lower().strip().encode()).hexdigest()

    # --- Main Scoring Function ---
    def score(self, cv_json_path, job_description_path):
        # --- Extract Job Data ---
        job_req_structured = self.extractor.extract(job_description_path)
        if job_req_structured is None:
            print(f"❌ Failed to extract structured data from {job_description_path}")
            return 0.0

        try:
            with open(job_description_path, 'r', encoding='utf-8') as f:
                job_text = f.read().strip()
        except FileNotFoundError:
            print(f"❌ Job description not found: {job_description_path}")
            return 0.0

        required_skills = set(self.normalize(s) for s in job_req_structured.get("required_skills", []) +
                              job_req_structured.get("technical_skills", []))

        min_years_str = job_req_structured.get("experience_requirements", {}).get(
            "years_of_experience", f"{self.min_experience_years} years")
        try:
            min_years = float(
                min(s for s in min_years_str.split() if s.isdigit())
                if any(s.isdigit() for s in min_years_str.split())
                else self.min_experience_years
            )
        except:
            min_years = self.min_experience_years

        required_certifications = set(self.normalize(c) for c in job_req_structured.get("certifications", []))
        location_req = ""  # left empty, can be extended
        required_education_list = job_req_structured.get("education_requirements", [])
        required_education = required_education_list[0] if required_education_list else ""

        # --- Load CV ---
        try:
            with open(cv_json_path, 'r', encoding='utf-8') as f:
                cv_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"❌ Error loading CV JSON {cv_json_path}: {e}")
            return 0.0

        structured_data = cv_data.get("CV_data", {}).get("structured_data", {})
        years_of_experience = structured_data.get("years_of_experience", 0.0)
        candidate_skills = [self.normalize(s) for s in structured_data.get("skills", []) +
                            structured_data.get("soft_skills", [])]
        candidate_certifications = [self.normalize(c.get("name", "")) for c in structured_data.get("certifications", []) if isinstance(c, dict)]
        candidate_location = structured_data.get("location", "").lower()
        candidate_education = structured_data.get("education", [])

        email = structured_data.get("email", "")
        cv_id = self.hash_email(email) if email else os.path.splitext(os.path.basename(cv_json_path))[0]

        print(f"DEBUG - cv_id: {cv_id}")

        # --- Hard Score ---
        hard_score = 0.0
        skill_matches = sum(1 for s in required_skills if self.fuzzy_match(s, candidate_skills))
        skill_fraction = skill_matches / len(required_skills) if required_skills else 1.0
        hard_score += skill_fraction * 0.5

        cert_matches = sum(1 for c in required_certifications if self.fuzzy_match(c, candidate_certifications))
        cert_fraction = cert_matches / len(required_certifications) if required_certifications else 1.0
        hard_score += cert_fraction * 0.3

        if location_req:
            hard_score += 0.2 if self.location_match(location_req, candidate_location) else 0.0
        hard_score *= 100

        # --- Semantic Similarity ---
        try:
            retrieved = self.vectorstore.get(where={"cv_id": cv_id})
            documents = retrieved.get("documents", [])
            metadatas = retrieved.get("metadatas", [])
            if not documents:
                print(f"⚠️ No embeddings found for CV: {cv_json_path}")
                return 0.0
        except Exception as e:
            print(f"⚠️ Error accessing Chroma: {e}")
            return 0.0

        try:
            job_vector = self.embeddings.embed_query(job_text)
        except Exception as e:
            print(f"⚠️ Error embedding job description: {e}")
            return 0.0

        section_scores = []
        for doc_text, metadata in zip(documents, metadatas):
            try:
                doc_vector = self.embeddings.embed_query(doc_text)
                similarity = np.dot(job_vector, doc_vector) / (np.linalg.norm(job_vector) * np.linalg.norm(doc_vector))
                weight = 1.5 if metadata.get("section") in ["work_experience", "skills", "summary"] else 1.0
                section_scores.append(similarity * weight)
            except:
                continue

        if section_scores:
            mean_score = np.mean(section_scores) * 100
            max_score = max(section_scores) * 100
            semantic_score = 0.7 * mean_score + 0.3 * max_score
        else:
            semantic_score = 0.0

        # --- Experience Alignment ---
        experience_score = min(years_of_experience / min_years, 1.0) * 100 if min_years > 0 else 100.0

        # --- Education Alignment ---
        education_score = self.fuzzy_education_match(required_education, candidate_education)

        # --- Hybrid Score ---
        hybrid_score = (
            hard_score * self.weights["hard_filters"] +
            semantic_score * self.weights["semantic_similarity"] +
            experience_score * self.weights["experience_alignment"] +
            education_score * self.weights["education_alignment"]
        )

        return round(hybrid_score, 2)


# --- Example usage ---
if __name__ == "__main__":
    scorer = CVJobScorer(min_experience_years=3)
    cv_json_path = "./extracted_files/CV_Image.json"
    job_description_path = "./job_description.txt"
    score = scorer.score(cv_json_path, job_description_path)
    print(f"CV Hybrid Score: {score}/100")
