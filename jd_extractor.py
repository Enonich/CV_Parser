from docstrange import DocumentExtractor
import json

# Job Description Schema for CV Comparison
job_description_schema = {
    "type": "object",
    "properties": {
        "job_title": {"type": "string"},
        "required_skills": {
            "type": "array",
            "items": {"type": "string"}
        },
        "required_qualifications": {
            "type": "array",
            "items": {"type": "string"}
        },
        "preferred_skills": {
            "type": "array",
            "items": {"type": "string"}
        },
        "education_requirements": {
            "type": "array", 
            "items": {"type": "string"}
        },
        "experience_requirements": {
            "type": "object",
            "properties": {
                "years_of_experience": {"type": "string"},
                "specific_experience": {"type": "string"}
            }
        },
        "technical_skills": {
            "type": "array",
            "items": {"type": "string"}
        },
        "soft_skills": {
            "type": "array",
            "items": {"type": "string"}
        },
        "certifications": {
            "type": "array",
            "items": {"type": "string"}
        },
        "responsibilities": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}

class JDExtractor:
    def __init__(self):
        self.extractor = DocumentExtractor()

    def extract(self, document_path):
        """
        Extract structured job description data for CV comparison.
        Returns the structured data as a Python dict, or None if extraction fails.
        """
        try:
            result = self.extractor.extract(document_path)
            structured_data = result.extract_data(json_schema=job_description_schema)
            return structured_data
        except FileNotFoundError:
            print(f"Error: Document not found at '{document_path}'. Please provide a valid file path.")
            return None
        except Exception as e:
            print(f"An error occurred during extraction: {e}")
            return None

# Example usage:
if __name__ == "__main__":
    document_path = './job_description.txt'
    extractor = JDExtractor()
    data = extractor.extract(document_path)
    print("Returned structured job description data for CV comparison:")
    print(json.dumps(data, indent=2))