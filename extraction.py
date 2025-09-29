import os
import json
from docstrange_extractor import CVExtractor
from prof_years_extractor import ProfessionalExperienceCalculator

def clean_cv_data(cv_data):
    """
    Recursively clean extracted CV data:
    - Replace None/null with [] for list-like fields
    - Replace None/null with "" for text fields
    """
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
                cleaned[key] = clean_cv_data(value)
        return cleaned

    elif isinstance(cv_data, list):
        return [clean_cv_data(item) for item in cv_data]

    else:
        return cv_data

def extract_and_save_cv(cv_file_path, output_dir):
    """
    Extract CV data, calculate years of experience, and save to JSON.
    
    Args:
        cv_file_path (str): Path to the input CV file (e.g., PDF, DOCX)
        output_dir (str): Directory to save the output JSON file
    
    Returns:
        str: Path to the saved JSON file, or None if extraction fails
    """
    extractor = CVExtractor()
    try:
        content = extractor.extract(cv_file_path)
    except Exception as e:
        print(f"❌ Error extracting {cv_file_path}: {e}")
        return None

    # Clean data before processing
    cleaned_content = clean_cv_data(content)

    # Calculate years of experience
    output_dict = {"CV_data": cleaned_content}
    try:
        calculator = ProfessionalExperienceCalculator(cv_data_dict=output_dict)
        years_of_experience = calculator.get_total_years()
        output_dict["CV_data"]["structured_data"]["years_of_experience"] = years_of_experience
    except Exception as e:
        print(f"⚠️ Error calculating years of experience for {cv_file_path}: {e}")
        output_dict["CV_data"]["structured_data"]["years_of_experience"] = 0.0

    # Save to JSON
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(cv_file_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_dict, f, indent=2, ensure_ascii=False)

    print(f"✅ Extracted and cleaned CV saved to: {output_path}")
    return output_path

def batch_extract_cvs(input_dir, output_dir="extracted_files"):
    """
    Process multiple CV files in a directory and save extracted data as JSON.
    
    Args:
        input_dir (str): Directory containing CV files
        output_dir (str): Directory to save JSON outputs
    """
    if not os.path.isdir(input_dir):
        print(f"❌ Input directory not found: {input_dir}")
        return

    files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.pdf', '.docx', '.png', '.jpg', '.jpeg'))]
    if not files:
        print(f"⚠️ No CV files (.pdf or .docx) found in {input_dir}")
        return

    for file_name in files:
        cv_path = os.path.join(input_dir, file_name)
        extract_and_save_cv(cv_path, output_dir)

# Example usage
if __name__ == "__main__":
    extract_and_save_cv("./CVs/CV_Image.png", "./extracted_files/")