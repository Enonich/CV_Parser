from docstrange import DocumentExtractor
import json
import re

# ------------------------------------------------------------------
#  Multi-Page JSON Parser
# ------------------------------------------------------------------

def merge_cv_json_objects(json_objects):
    """
    Merge multiple JSON objects from different pages into a single complete CV.
    
    Strategy:
    - Take non-null scalar fields from the first object that has them
    - Merge arrays (work_experience, education, skills, etc.)
    - Remove duplicates from simple string arrays
    """
    merged = {
        "name": None,
        "email": None,
        "phone": None,
        "summary": None,
        "work_experience": [],
        "education": [],
        "skills": [],
        "soft_skills": [],
        "certifications": [],
        "projects": [],
        "languages": [],
        "hobbies": [],
        "other": ""
    }
    
    for obj in json_objects:
        # Merge scalar fields (take first non-null value)
        for field in ["name", "email", "phone", "summary", "other"]:
            if merged[field] is None and obj.get(field):
                merged[field] = obj[field]
        
        # Merge array fields (concatenate)
        for field in ["work_experience", "education", "certifications", "projects"]:
            if obj.get(field):
                merged[field].extend(obj[field])
        
        # Merge simple string arrays (deduplicate)
        for field in ["skills", "soft_skills", "languages", "hobbies"]:
            if obj.get(field):
                if isinstance(obj[field], list):
                    merged[field].extend(obj[field])
                elif isinstance(obj[field], str) and obj[field].strip():
                    # Handle case where it's a string instead of array
                    merged[field].append(obj[field])
    
    # Deduplicate simple arrays
    merged["skills"] = list(set(merged["skills"]))
    merged["soft_skills"] = list(set(merged["soft_skills"]))
    merged["languages"] = list(set(merged["languages"]))
    merged["hobbies"] = list(set(merged["hobbies"]))
    
    # Convert None to empty string for optional scalar fields
    if merged["other"] is None:
        merged["other"] = ""
    
    return merged


def parse_multi_object_json(raw_text):
    """
    Parse output that may contain multiple JSON objects separated by page breaks.
    Returns a single merged JSON object.
    
    Handles the case where docstrange returns multiple JSON objects (one per page)
    separated by page break markers like:
    {...}<!-- Page Break - Batch 2 -->{...}<!-- Page Break - Batch 3 -->{...}
    """
    # Split by page break markers
    page_break_patterns = [
        r'<!-- Page Break.*?-->',
        r'\n\n\n+',  # Multiple newlines
    ]
    
    # Combine patterns into one regex
    split_pattern = '|'.join(f'(?:{p})' for p in page_break_patterns)
    chunks = re.split(split_pattern, raw_text, flags=re.IGNORECASE)
    
    json_objects = []
    
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        
        # Find JSON object in chunk
        json_start = chunk.find('{')
        if json_start == -1:
            continue
        
        json_string = chunk[json_start:]
        
        # Try to find the end of the JSON object
        try:
            # Use json.JSONDecoder to find where the JSON ends
            decoder = json.JSONDecoder()
            obj, end_idx = decoder.raw_decode(json_string)
            json_objects.append(obj)
        except json.JSONDecodeError as e:
            print(f"Warning: Could not parse JSON chunk: {e}")
            continue
    
    if not json_objects:
        raise ValueError("No valid JSON objects found in the output")
    
    # If only one object, return it directly
    if len(json_objects) == 1:
        return json_objects[0]
    
    # Otherwise, merge multiple objects
    print(f"Found {len(json_objects)} JSON objects across pages. Merging...")
    return merge_cv_json_objects(json_objects)


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
        Handles multi-page CVs that return multiple JSON objects.
        """
        try:
            result = self.extractor.extract(document_path)
            structured_data = result.extract_data(json_schema=resume_schema)

            # Handle different output formats from docstrange
            text_to_parse = None
            
            if isinstance(structured_data, dict):
                # Check if it's a wrapped response with raw_content
                if 'document' in structured_data and 'raw_content' in structured_data['document']:
                    text_to_parse = structured_data['document']['raw_content']
                else:
                    # It's already a proper dict, return it
                    return structured_data
            elif isinstance(structured_data, str):
                text_to_parse = structured_data
            else:
                # Unknown format, convert to string for parsing attempt
                text_to_parse = json.dumps(structured_data)
            
            # If we have text to parse, try multi-object JSON parser
            if text_to_parse:
                try:
                    # First try standard JSON parsing
                    parsed_data = json.loads(text_to_parse)
                    return parsed_data
                except json.JSONDecodeError:
                    # If standard parsing fails, use multi-object parser
                    print("Standard JSON parsing failed, attempting multi-page parser...")
                    try:
                        parsed_data = parse_multi_object_json(text_to_parse)
                        return parsed_data
                    except Exception as e:
                        print(f"Multi-page JSON parsing error: {e}")
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