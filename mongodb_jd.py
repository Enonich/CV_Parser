import json
import logging
import hashlib
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
        """Generate a unique JD ID from job title (and optionally company name)"""
        identifier = job_title.lower().strip()
        if company_name:
            identifier += f"_{company_name.lower().strip()}"
        return hashlib.sha256(identifier.encode('utf-8')).hexdigest()

    def load_json_file(self, file_path):
        """Load and validate JSON file"""
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

            jd_data = data.get('structured_data', None)
            if not jd_data:
                logger.error("Missing 'structured_data' key in JSON.")
                return None

            return jd_data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading JSON: {e}")
            return None

    def insert_jd_data(self, data):
        """Insert single Job Description document"""
        try:
            job_title = data.get('job_title')
            if not job_title:
                logger.error("Missing job_title in data.")
                return False

            company_name = data.get('company_name')
            jd_id = self.generate_jd_id(job_title, company_name)

            if self.collection.find_one({'_id': jd_id}):
                logger.warning(f"JD already exists for job title: {job_title}")
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
        try:
            if not self.connect_to_database():
                return False
            data = self.load_json_file(file_path)
            if data is None:
                return False
            success = self.insert_jd_data(data)
            return success
        finally:
            self.close_connection()

    def check_jd_exists(self, jd_id=None):
        """Check if a JD already exists in the database based on JD ID."""
        try:
            if not self.connect_to_database():
                logger.error("Failed to connect to MongoDB")
                return None
            
            # Check if document exists
            existing_doc = self.collection.find_one({"jd_id": jd_id})
            
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
        finally:
            self.close_connection()

    def get_all_jds(self):
        """Get all JDs from MongoDB collection."""
        try:
            if not self.connect_to_database():
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
        finally:
            self.close_connection()


# Example usage
if __name__ == "__main__":
    document_path = './extracted_files/data_analyst_jd.json'
    jd_inserter = JDDataInserter()
    success = jd_inserter.process_jd_file(document_path)
    
    if success:
        print("✅ JD data successfully inserted into MongoDB")
    else:
        print("❌ Failed to insert JD data")
