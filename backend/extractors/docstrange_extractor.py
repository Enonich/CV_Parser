from docstrange import DocumentExtractor
import json

# ------------------------------------------------------------------
#  Structured Database Schema
# ------------------------------------------------------------------
resume_schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "summary": {"type": "string"},
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
        "skills": {"type": "array", "items": {"type": "string"}},
        "soft_skills": {"type": "array", "items": {"type": "string"}},
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
                    "technologies": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "languages": {
            "type": "array",
            "items": {"type": "string"},
            "default": []          # ensures [] if not present
        },
        "hobbies": {
            "type": "array",
            "items": {"type": "string"},
            "default": []          # ensures [] if not present
        },
        "other": {
            "type": "string",
            "default": ""          # ensures "" if not present
        }
    }
}


class CVExtractor:
    def __init__(self):
        self.extractor = DocumentExtractor()

    def extract(self, document_path):
        """
        Returns the resume dict **exactly as defined in the schema**.
        No extra keys, no manual field injection.
        """
        try:
            result = self.extractor.extract(document_path)
            structured_data = result.extract_data(json_schema=resume_schema)

            # If the extractor returns a JSON string (rare fallback), parse it
            if isinstance(structured_data, str):
                try:
                    structured_data = json.loads(structured_data)
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    return None

            return structured_data

        except FileNotFoundError:
            print(f"Error: Document not found at '{document_path}'.")
            return None
        except Exception as e:
            print(f"An error occurred: {e}")
            return None


# -------------------------- Example usage --------------------------
if __name__ == "__main__":
    document_path = './CVs/Power_BI_Developer.pdf'
    extractor = CVExtractor()
    data = extractor.extract(document_path)

    print("Returned structured data:")
    print(json.dumps(data, indent=2))