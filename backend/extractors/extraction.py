import os
from backend.extractors.docstrange_extractor import CVExtractor

def extract_and_save_cv(cv_file_path):
    # Extract content using CVExtractor
    extractor = CVExtractor(cv_file_path)
    content = extractor.extract_content()

    # Prepare output directory and filename
    output_dir = os.path.join(os.path.dirname(__file__), 'extracted_files')
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(cv_file_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}.txt")

    # Write extracted content to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

# Example usage:
extract_and_save_cv('./CVs/Data_Analyst3_CV.pdf')