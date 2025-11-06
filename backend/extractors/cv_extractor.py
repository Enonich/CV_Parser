import os
import json
from backend.extractors.docstrange_extractor import CVExtractor
from backend.extractors.prof_years_extractor import ProfessionalExperienceCalculator


class CVProcessor:
    """A class to handle CV data extraction, cleaning, and processing."""

    @staticmethod
    def clean_cv_data(cv_data):
        """Recursively clean extracted CV data."""
        if isinstance(cv_data, dict):
            cleaned = {}
            for key, value in cv_data.items():
                if value is None:
                    if key in ["work_experience", "education", "skills", "soft_skills",
                               "certifications", "projects", "languages", "hobbies"]:
                        cleaned[key] = []
                    else:
                        cleaned[key] = ""
                else:
                    cleaned[key] = CVProcessor.clean_cv_data(value)
            return cleaned
        elif isinstance(cv_data, list):
            return [CVProcessor.clean_cv_data(item) for item in cv_data]
        return cv_data

    @staticmethod
    def fix_work_experience_structure(data):
        """
        CRITICAL FIX: Convert FLAT job objects → PROPER ARRAY
        Handles: {"company": "...", "start_date": "..."} → [{"company": "...", ...}]
        Updates `data` in place and returns the fixed list.
        """
        work_exp = data.get("work_experience", [])

        # CASE 1: Already a list → ensure it's stored correctly
        if isinstance(work_exp, list):
            data["work_experience"] = work_exp
            return work_exp

        # CASE 2: Flat job fields at top level
        job_fields = {"company", "title", "start_date", "end_date", "location", "responsibilities"}
        top_keys = set(data.keys())
        common_fields = top_keys & job_fields

        if len(common_fields) >= 2:
            # Extract and remove flat job fields
            single_job = {}
            for field in common_fields:
                single_job[field] = data.pop(field)
            # Add responsibilities if missing
            if "responsibilities" not in single_job:
                single_job["responsibilities"] = []
            data["work_experience"] = [single_job]
            print("FIXED: Converted flat job → array!")
            return [single_job]

        # CASE 3: No job data → ensure empty array
        data["work_experience"] = []
        return []

    def extract_and_save_cv(self, cv_file_path, output_dir):
         """Extract CV data with AUTO-FIX for flat job structure."""
         print(f"\nPROCESSING: {os.path.basename(cv_file_path)}")
        
         extractor = CVExtractor()
         try:
             content = extractor.extract(cv_file_path)
         except Exception as e:
             print(f"Error extracting {cv_file_path}: {e}")
             return None
        
         # Step 1: Clean data
         cleaned_content = self.clean_cv_data(content)
        
         # Step 2: FIX FLAT WORK EXPERIENCE (if needed)
         work_exp = self.fix_work_experience_structure(cleaned_content)
        
         # DEBUG: Show what we have
         print(f"\nWORK EXPERIENCE FOUND!")
         for i, job in enumerate(work_exp):
             start = job.get('start_date', 'NO_START')
             end = job.get('end_date', 'NO_END')
             print(f"   Job {i+1}: '{start}' → '{end}'")
        
         # DO NOT WRAP AGAIN — content is already structured!
         # If extractor returns {"structured_data": {...}}, extract it:
         if "structured_data" in cleaned_content:
             final_data = cleaned_content["structured_data"]
         else:
             final_data = cleaned_content
        
         # Ensure work_experience is always a list
         if "work_experience" not in final_data:
             final_data["work_experience"] = []
        
         # Build correct output structure
         output_dict = {
             "CV_data": {
                 "structured_data": final_data
             }
         }
        
         # Calculate years
         try:
             calculator = ProfessionalExperienceCalculator(cv_data_dict=output_dict)
             years_of_experience = calculator.get_total_years()
             final_data["years_of_experience"] = years_of_experience
             print(f"\nFINAL RESULT: {years_of_experience} years")
         except Exception as e:
             print(f"CALCULATION ERROR: {e}")
             final_data["years_of_experience"] = 0.0
        
         # Save
         os.makedirs(output_dir, exist_ok=True)
         base_name = os.path.splitext(os.path.basename(cv_file_path))[0]
         output_path = os.path.join(output_dir, f"{base_name}.json")
        
         with open(output_path, 'w', encoding='utf-8') as f:
             json.dump(output_dict, f, indent=2, ensure_ascii=False)
        
         print(f"SAVED: {output_path}")
         return output_path

    def batch_extract_cvs(self, input_dir, output_dir="extracted_files"):
        """Process multiple CV files."""
        if not os.path.isdir(input_dir):
            print(f"Input directory not found: {input_dir}")
            return

        files = [f for f in os.listdir(input_dir)
                 if f.lower().endswith(('.pdf', '.docx', '.png', '.jpg', '.jpeg'))]
        if not files:
            print(f"No CV files found in {input_dir}")
            return

        print(f"BATCH PROCESSING {len(files)} CV FILES...")
        successful = 0
        total_years = 0

        for i, file_name in enumerate(files, 1):
            cv_path = os.path.join(input_dir, file_name)
            result = self.extract_and_save_cv(cv_path, output_dir)
            if result:
                successful += 1
                with open(result, 'r') as f:
                    data = json.load(f)
                    years = data["CV_data"]["structured_data"].get("years_of_experience", 0)
                    total_years += years

        avg_years = total_years / successful if successful > 0 else 0
        print(f"\nBATCH COMPLETE! {successful}/{len(files)} | Avg: {avg_years:.1f} years")


# Example usage
if __name__ == "__main__":
    processor = CVProcessor()
    processor.extract_and_save_cv("./CVs/CV_Image.png", "./extracted_files/")