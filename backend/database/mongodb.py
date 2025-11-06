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

class CVDataInserter:
    def __init__(self, connection_string='mongodb://localhost:27017/', 
                 db_name='CV', collection_name='CV_Data'):
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
        except ServerSelectionTimeoutError:
            logger.error("MongoDB server not available.")
            return False
        except ConnectionFailure:
            logger.error("Failed to connect to MongoDB.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False

    def generate_cv_id(self, email=None, phone=None):
        """Generate a unique CV ID by hashing the email or phone number"""
        if email:
            identifier = email.lower().strip()
        elif phone:
            identifier = phone.strip()
        else:
            raise ValueError("Either email or phone is required to generate cv_id")
        
        return hashlib.sha256(identifier.encode('utf-8')).hexdigest()

    def load_json_file(self, file_path):
        """Load and validate JSON file"""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None

            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.error(f"File is empty: {file_path}")
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            cv_data = data['CV_data']['structured_data']
            return cv_data
        except KeyError as e:
            logger.error(f"Expected structure not found: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading JSON: {e}")
            return None

    def insert_cv_data(self, data):
        """Insert single CV using hashed email or phone as _id"""
        try:
            email = data.get('email', '').strip() if data.get('email') else None
            phone = data.get('phone', '').strip() if data.get('phone') else None
            
            if not email and not phone:
                logger.error("Either email or phone field is required")
                return False
            
            cv_id = self.generate_cv_id(email=email, phone=phone)
            identifier_used = email if email else phone
            identifier_type = "email" if email else "phone"
            
            existing_cv = self.collection.find_one({'_id': cv_id})
            if existing_cv:
                logger.warning(f"CV already exists for {identifier_type}: {identifier_used}")
                return False
            
            data['_id'] = cv_id
            data['inserted_at'] = datetime.now(UTC)
            data['version'] = '1.0'

            result = self.collection.insert_one(data)
            logger.info(f"CV inserted successfully (using {identifier_type}: {identifier_used})")
            return True
            
        except DuplicateKeyError:
            logger.warning(f"Duplicate CV detected")
            return False
        except PyMongoError as e:
            logger.error(f"MongoDB insert failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False

    def insert_many_cvs(self, data_list):
        """Insert multiple CVs"""
        logger.info(f"Batch inserting {len(data_list)} CV documents...")
        inserted_count = 0
        skipped_count = 0
        
        try:
            for d in data_list:
                email = d.get('email', '').strip() if d.get('email') else None
                phone = d.get('phone', '').strip() if d.get('phone') else None
                
                if not email and not phone:
                    skipped_count += 1
                    continue
                
                cv_id = self.generate_cv_id(email=email, phone=phone)
                identifier_used = email if email else phone
                identifier_type = "email" if email else "phone"
                
                existing_cv = self.collection.find_one({'_id': cv_id})
                if existing_cv:
                    skipped_count += 1
                    continue
                
                d['_id'] = cv_id
                d['inserted_at'] = datetime.now(UTC)
                d['version'] = '1.0'
                
                try:
                    self.collection.insert_one(d)
                    inserted_count += 1
                except DuplicateKeyError:
                    skipped_count += 1
            
            logger.info(f"Batch insert completed. Inserted: {inserted_count}, Skipped: {skipped_count}")
            return True
            
        except Exception as e:
            logger.error(f"Unexpected batch insert error: {e}")
            return False

    def close_connection(self):
        """Close MongoDB connection"""
        try:
            if self.client:
                self.client.close()
        except Exception as e:
            logger.error(f"Error closing connection: {e}")

    def process_cv_file(self, file_path):
        """Complete process for a single CV file"""
        logger.info("Starting CV file processing...")
        try:
            if not self.connect_to_database():
                return False
            data = self.load_json_file(file_path)
            if data is None:
                return False
            success = self.insert_cv_data(data)
            return success
        finally:
            self.close_connection()

    def get_all_cvs(self):
        """Get all CVs from MongoDB collection."""
        try:
            if not self.connect_to_database():
                logger.error("Failed to connect to MongoDB")
                return []
            
            # Get all documents from the collection
            cursor = self.collection.find({})
            cvs = []
            
            for document in cursor:
                # Convert ObjectId to string for JSON serialization
                document['_id'] = str(document['_id'])
                cvs.append(document)
            
            logger.info(f"Retrieved {len(cvs)} CVs from MongoDB")
            return cvs
            
        except Exception as e:
            logger.error(f"Error retrieving CVs from MongoDB: {e}")
            return []
        finally:
            self.close_connection()

    def get_cv_by_id(self, cv_id):
        """Get a specific CV by its ID."""
        try:
            if not self.connect_to_database():
                logger.error("Failed to connect to MongoDB")
                return None
            
            # Find document by _id
            document = self.collection.find_one({"_id": cv_id})
            
            if document:
                # Convert ObjectId to string for JSON serialization
                document['_id'] = str(document['_id'])
                logger.info(f"Retrieved CV with ID: {cv_id}")
                return document
            else:
                logger.warning(f"CV with ID {cv_id} not found")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving CV by ID: {e}")
            return None
        finally:
            self.close_connection()

    def check_cv_exists(self, email=None, phone=None):
        """Check if a CV already exists in the database based on email or phone."""
        try:
            if not self.connect_to_database():
                logger.error("Failed to connect to MongoDB")
                return None
            
            # Generate the CV ID to check
            cv_id = self.generate_cv_id(email=email, phone=phone)
            
            # Check if document exists using _id (primary key)
            existing_doc = self.collection.find_one({"_id": cv_id})
            
            if existing_doc:
                existing_doc['_id'] = str(existing_doc['_id'])
                logger.info(f"CV with ID {cv_id} already exists in database")
                return existing_doc
            else:
                logger.info(f"CV with ID {cv_id} not found in database")
                return None
                
        except Exception as e:
            logger.error(f"Error checking CV existence: {e}")
            return None
        finally:
            self.close_connection()

            
# Example usage:
if __name__ == "__main__":
    document_path = './extracted_files/data_analyst_jd.json'
    mongo_inserter = CVDataInserter(db_name='JD', collection_name="JD_collection")
    success = mongo_inserter.process_cv_file(document_path)
    
    if success:
        print("✅ CV data successfully inserted into MongoDB")
    else:
        print("❌ Failed to insert CV data")