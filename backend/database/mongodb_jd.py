import json
import logging
from pathlib import Path
from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure, 
    ServerSelectionTimeoutError,
    DuplicateKeyError,
    PyMongoError
)
from datetime import datetime, UTC

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class JDDataInserter:
    def __init__(self, connection_string='mongodb://localhost:27017/', 
                 db_name='JD', collection_name='JD_collection'):
        self.connection_string = connection_string
        self.db_name = db_name
        self.collection_name = collection_name
        self.client = None
        self.db = None
        self.collection = None
    
    def connect_to_database(self):
        """Establish connection to MongoDB database"""
        try:
            logger.info("Connecting to MongoDB...")
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=0
            )
            self.client.admin.command('ping')
            logger.info("Connection established.")

            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            return True

        except (ServerSelectionTimeoutError, ConnectionFailure):
            logger.error("MongoDB connection failed.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False

    def generate_jd_id(self, job_title, company_name=None):
        """Return deterministic ID equal to sanitized job title (ignores company).

        This meets requirement: JD id should be the name of the job they're recruiting for.
        Uses lowercase trimmed form with spaces converted to underscores.
        """
        if not job_title:
            raise ValueError("job_title required for JD ID")
        base = job_title.lower().strip()
        # Basic sanitization similar to identifiers.sanitize_fragment (avoid import loop)
        import re
        base = re.sub(r"[^a-z0-9]+", "_", base)
        base = re.sub(r"_+", "_", base).strip("_")
        return base or "unknown_job"

    def load_json_file(self, file_path):
        """Load and validate JSON file
        
        IMPORTANT: The job_title from the wrapper (form input) always takes precedence
        over any job_title in the structured_data (document content). This ensures
        the JD ID matches what the user entered in the form, not what's in the document.
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None

            if file_path.stat().st_size == 0:
                logger.error(f"File is empty: {file_path}")
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            jd_struct = data.get('structured_data')
            if not jd_struct:
                logger.error("Missing 'structured_data' key in JSON.")
                return None
            
            # CRITICAL: Top-level job_title (from form) ALWAYS overrides structured_data job_title
            # This ensures JD ID is based on what user entered, not document content
            company_name = data.get('company_name')
            job_title_from_form = data.get('job_title')  # This is what user typed in the form
            job_title_from_doc = jd_struct.get('job_title')  # This is from document content
            
            # Preserve sanitized variants if provided (added upstream during upload)
            company_name_sanitized = data.get('company_name_sanitized')
            job_title_sanitized = data.get('job_title_sanitized')
            
            # Apply company context
            if company_name:
                jd_struct['company_name'] = company_name
            if company_name_sanitized:
                jd_struct['company_name_sanitized'] = company_name_sanitized
            if job_title_sanitized:
                jd_struct['job_title_sanitized'] = job_title_sanitized
            
            # ALWAYS use form job_title if available, otherwise fall back to document
            if job_title_from_form:
                jd_struct['job_title'] = job_title_from_form
                logger.info(f"Using job_title from form: '{job_title_from_form}' (document had: '{job_title_from_doc}')")
            elif job_title_from_doc:
                jd_struct['job_title'] = job_title_from_doc
                logger.warning(f"No form job_title found, using document job_title: '{job_title_from_doc}'")
            else:
                logger.error("No job_title found in either form data or document content")
                return None
            
            return jd_struct
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading JSON: {e}")
            return None

    def insert_jd_data(self, data):
        """Insert single Job Description document"""
        try:
            # Ensure we have an active connection
            if self.client is None or self.collection is None:
                logger.error("No active database connection for insert_jd_data")
                return False
            
            job_title = data.get('job_title')
            if not job_title:
                logger.error("Missing job_title in data.")
                return False

            company_name = data.get('company_name')
            jd_id = self.generate_jd_id(job_title, company_name)

            existing = self.collection.find_one({'_id': jd_id})
            if existing:
                logger.warning(f"JD already exists for job title: {job_title} (_id={jd_id})")
                return False
            
            data['_id'] = jd_id
            data['inserted_at'] = datetime.now(UTC)
            data['version'] = '1.0'

            self.collection.insert_one(data)
            logger.info(f"JD inserted successfully (job title: {job_title})")
            return True

        except DuplicateKeyError:
            logger.warning("Duplicate JD detected.")
            return False
        except PyMongoError as e:
            logger.error(f"MongoDB insert failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False

    def close_connection(self):
        """Close MongoDB connection"""
        try:
            if self.client:
                self.client.close()
        except Exception as e:
            logger.error(f"Error closing connection: {e}")

    def process_jd_file(self, file_path):
        """Complete process for a single JD file"""
        logger.info("Starting JD file processing...")
        # Track if we need to close the connection (only if we opened it here)
        opened_connection = False
        try:
            # Only connect if not already connected
            if self.client is None:
                if not self.connect_to_database():
                    return False
                opened_connection = True
            
            data = self.load_json_file(file_path)
            if data is None:
                return False
            success = self.insert_jd_data(data)
            return success
        finally:
            # Only close if we opened the connection in this method
            if opened_connection:
                self.close_connection()

    def check_jd_exists(self, jd_id=None):
        """Check if a JD already exists in the database based on JD ID.
        
        Note: This method does NOT close the connection to allow subsequent operations
        on the same instance. The caller is responsible for connection management.
        """
        try:
            # Ensure connection is established
            if self.client is None and not self.connect_to_database():
                logger.error("Failed to connect to MongoDB")
                return None
            
            # Check if document exists
            # Documents use _id as jd_id
            existing_doc = self.collection.find_one({"_id": jd_id})
            
            if existing_doc:
                existing_doc['_id'] = str(existing_doc['_id'])
                logger.info(f"JD with ID {jd_id} already exists in database")
                return existing_doc
            else:
                logger.info(f"JD with ID {jd_id} not found in database")
                return None
                
        except Exception as e:
            logger.error(f"Error checking JD existence: {e}")
            return None

    def get_all_jds(self):
        """Get all JDs from MongoDB collection.
        
        Note: This method does NOT close the connection. The caller is responsible
        for connection management (typically via process_jd_file or explicit close).
        """
        try:
            # Ensure connection is established
            if self.client is None and not self.connect_to_database():
                logger.error("Failed to connect to MongoDB")
                return []
            
            # Get all documents from the collection
            cursor = self.collection.find({})
            jds = []
            
            for document in cursor:
                # Convert ObjectId to string for JSON serialization
                document['_id'] = str(document['_id'])
                jds.append(document)
            
            logger.info(f"Retrieved {len(jds)} JDs from MongoDB")
            return jds
            
        except Exception as e:
            logger.error(f"Error retrieving JDs from MongoDB: {e}")
            return []


# Example usage
if __name__ == "__main__":
    document_path = './extracted_files/data_analyst_jd.json'
    jd_inserter = JDDataInserter()
    success = jd_inserter.process_jd_file(document_path)
    
    if success:
        print("✅ JD data successfully inserted into MongoDB")
    else:
        print("❌ Failed to insert JD data")
