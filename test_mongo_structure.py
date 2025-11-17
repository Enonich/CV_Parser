"""
Test script to verify MongoDB structure:
- Database = Company Name
- Collections = cvs_{job_name} and jd_{job_name}
"""
from pymongo import MongoClient
from backend.core.identifiers import sanitize_fragment, build_mongo_names

def test_mongodb_structure():
    # Connect to MongoDB
    client = MongoClient('mongodb://localhost:27017/')
    
    # Test case 1: Company "Google", Job "Software Engineer"
    company_name = "Google"
    job_title = "Software Engineer"
    
    db_name, cv_collection, jd_collection = build_mongo_names(company_name, job_title)
    
    print(f"\n{'='*60}")
    print(f"Testing: {company_name} - {job_title}")
    print(f"{'='*60}")
    print(f"Database name: {db_name}")
    print(f"CV Collection: {cv_collection}")
    print(f"JD Collection: {jd_collection}")
    
    # Access the database
    db = client[db_name]
    
    # Check what collections exist
    existing_collections = db.list_collection_names()
    print(f"\nExisting collections in '{db_name}': {existing_collections}")
    
    # Test case 2: Same company, different job
    job_title_2 = "Data Analyst"
    db_name_2, cv_collection_2, jd_collection_2 = build_mongo_names(company_name, job_title_2)
    
    print(f"\n{'='*60}")
    print(f"Testing: {company_name} - {job_title_2}")
    print(f"{'='*60}")
    print(f"Database name: {db_name_2}")
    print(f"CV Collection: {cv_collection_2}")
    print(f"JD Collection: {jd_collection_2}")
    print(f"\nNote: Database should be the SAME ('{db_name_2}')")
    print(f"Collections should be DIFFERENT:")
    print(f"  - {cv_collection} vs {cv_collection_2}")
    print(f"  - {jd_collection} vs {jd_collection_2}")
    
    # List all databases (companies)
    print(f"\n{'='*60}")
    print("All Companies (Databases):")
    print(f"{'='*60}")
    all_dbs = client.list_database_names()
    # Filter out system databases
    company_dbs = [db for db in all_dbs if db not in ['admin', 'local', 'config', 'CV', 'JD']]
    for db_name in company_dbs:
        db = client[db_name]
        collections = db.list_collection_names()
        # Extract job names from collection names
        jobs = set()
        for coll in collections:
            if coll.startswith("cvs_"):
                job_slug = coll[4:]  # Remove "cvs_" prefix
                jobs.add(job_slug)
            elif coll.startswith("jd_"):
                job_slug = coll[3:]  # Remove "jd_" prefix
                jobs.add(job_slug)
        
        print(f"\nCompany: {db_name}")
        print(f"  Jobs: {list(jobs)}")
        print(f"  Collections: {collections}")
        
        # Count documents in each collection
        for coll_name in collections:
            count = db[coll_name].count_documents({})
            print(f"    - {coll_name}: {count} documents")
    
    client.close()
    print(f"\n{'='*60}")
    print("Test complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    test_mongodb_structure()
