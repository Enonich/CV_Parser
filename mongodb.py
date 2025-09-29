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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CVDataInserter:
    def __init__(self, connection_string='mongodb://localhost:27017/', 
                 db_name='CV', collection_name='CV_Data'):
        """
        Initialize the CV Data Inserter
        
        Args:
            connection_string (str): MongoDB connection string
            db_name (str): Database name
            collection_name (str): Collection name
        """
        self.connection_string = connection_string
        self.db_name = db_name
        self.collection_name = collection_name
        self.client = None
        self.db = None
        self.collection = None
    
    def connect_to_database(self):
        """Establish connection to MongoDB database"""
        try:
            # Set connection timeout and server selection timeout
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=10000,         # 10 second connection timeout
                socketTimeoutMS=0               # No socket timeout
            )
            
            # Test the connection
            self.client.admin.command('ping')
            
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            
            logger.info(f"Successfully connected to MongoDB database: {self.db_name}")
            return True
            
        except ServerSelectionTimeoutError:
            logger.error("MongoDB server not available. Please check if MongoDB is running.")
            return False
        except ConnectionFailure:
            logger.error("Failed to connect to MongoDB. Check connection string and network.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to database: {e}")
            return False
    
    def load_json_file(self, file_path):
        """
        Load and validate JSON file
        
        Args:
            file_path (str): Path to the JSON file
            
        Returns:
            dict: Loaded JSON data or None if error
        """
        try:
            file_path = Path(file_path)
            
            # Check if file exists
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None
            
            # Check file size (optional safety check)
            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.error(f"File is empty: {file_path}")
                return None
            
            if file_size > 50 * 1024 * 1024:  # 50MB limit
                logger.warning(f"Large file detected ({file_size} bytes): {file_path}")
            
            # Load JSON with proper encoding
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Basic validation
            if not isinstance(data, dict):
                logger.error("JSON data should be a dictionary/object")
                return None
            
            logger.info(f"Successfully loaded JSON file: {file_path}")
            return data
            
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
        except PermissionError:
            logger.error(f"Permission denied accessing file: {file_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format in {file_path}: {e}")
        except UnicodeDecodeError as e:
            logger.error(f"Encoding error reading {file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading file {file_path}: {e}")
        
        return None
    
    def insert_cv_data(self, data):
        """
        Insert CV data into MongoDB collection
        
        Args:
            data (dict): CV data to insert
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Add metadata
            from datetime import datetime
            data['inserted_at'] = datetime.utcnow()
            data['version'] = '1.0'
            
            # Insert document
            result = self.collection.insert_one(data)
            
            if result.inserted_id:
                logger.info(f"Successfully inserted CV data with ID: {result.inserted_id}")
                return True
            else:
                logger.error("Failed to insert document - no ID returned")
                return False
                
        except DuplicateKeyError:
            logger.error("Document with duplicate key already exists")
        except PyMongoError as e:
            logger.error(f"MongoDB operation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during insertion: {e}")
        
        return False
    
    def close_connection(self):
        """Close MongoDB connection"""
        try:
            if self.client:
                self.client.close()
                logger.info("MongoDB connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
    
    def process_cv_file(self, file_path):
        """
        Complete process to load and insert CV data
        
        Args:
            file_path (str): Path to CV JSON file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Connect to database
            if not self.connect_to_database():
                return False
            
            # Load JSON data
            data = self.load_json_file(file_path)
            if data is None:
                return False
            
            # Insert data
            success = self.insert_cv_data(data)
            
            return success
            
        finally:
            # Always close connection
            self.close_connection()


def main():
    """Main function to demonstrate usage"""
    try:
        # Initialize inserter
        inserter = CVDataInserter()
        
        # Process the CV file
        file_path = 'extracted_files/Power_BI_Developer.json'
        success = inserter.process_cv_file(file_path)
        
        if success:
            print("✅ CV data successfully processed and inserted!")
        else:
            print("❌ Failed to process CV data. Check logs for details.")
            
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")


if __name__ == "__main__":
    main()


# Alternative simple function for direct use
def insert_cv_json_simple(file_path, connection_string='mongodb://localhost:27017/',
                         db_name='CV', collection_name='CV_Data'):
    """
    Simplified function to insert CV JSON data with error handling
    
    Args:
        file_path (str): Path to JSON file
        connection_string (str): MongoDB connection string
        db_name (str): Database name
        collection_name (str): Collection name
    
    Returns:
        bool: Success status
    """
    client = None
    try:
        # Connect to MongoDB
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test connection
        
        # Load JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Insert data
        db = client[db_name]
        collection = db[collection_name]
        result = collection.insert_one(data)
        
        print(f"✅ Document inserted with ID: {result.inserted_id}")
        return True
        
    except FileNotFoundError:
        print(f"❌ Error: File '{file_path}' not found")
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON format - {e}")
    except ServerSelectionTimeoutError:
        print("❌ Error: Cannot connect to MongoDB. Is it running?")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if client:
            client.close()
    
    return False


# Example usage:
# insert_cv_json_simple('extracted_files/Data_Analyst3_CV.json')
