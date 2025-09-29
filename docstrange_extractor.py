

from docstrange import DocumentExtractor
import json

# CV Data Schema
resume_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "summary": {"type": "string"},
            "years_of_experience": {"type": "number"},
            "work_experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "location": {"type": "string"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                        "responsibilities": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["company", "title"]
                }
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "degree": {"type": "string"},
                        "field_of_study": {"type": "string"},
                        "institution": {"type": "string"},
                        "location": {"type": "string"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"}
                    },
                    "required": ["degree", "institution"]
                }
            },
            "skills": {
                "type": "array",
                "items": {"type": "string"}
            },
            "soft_skills": {
                "type": "array",
                "items": {"type": "string"}
            },
            "certifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "issuing_organization": {"type": "string"},
                        "date": {"type": "string"}
                    },
                    "required": ["name"]
                }
            },
            "projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "technologies": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["name"]
                }
            },
            "languages": {"type": "string"},
            "hobbies": {"type": "string"},
            "other": {"type": "string"}
        }
    }

class CVExtractor:
    def __init__(self):
        self.extractor = DocumentExtractor()

    def extract(self, document_path):
        """
        Extract structured resume data from a document using the default resume_schema.
        Returns the structured data as a Python dict, or None if extraction fails.
        """
        try:
            result = self.extractor.extract(document_path)
            structured_data = result.extract_data(json_schema=resume_schema)
            return structured_data
        except FileNotFoundError:
            print(f"Error: Document not found at '{document_path}'. Please provide a valid file path.")
            return None
        except Exception as e:
            print(f"An error occurred during extraction: {e}")
            return None

# Example usage:
if __name__ == "__main__":
    # Define your schema (now inside main)
    
    document_path = './CV_Image.png'
    extractor = CVExtractor()
    data = extractor.extract(document_path)
    print("Returned structured data:")
    print(json.dumps(data, indent=2))
