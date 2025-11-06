"""
Migrate admin users from users collection to admins collection.
Run this once after updating auth.py to use separate collections.
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
USER_DB_NAME = os.getenv("USER_DB_NAME", "Auth")
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}

def migrate_admins():
    """Move admin users from users to admins collection."""
    client = MongoClient(MONGO_URI)
    db = client[USER_DB_NAME]
    
    users_coll = db["users"]
    admins_coll = db["admins"]
    
    print("=== Admin Migration ===\n")
    print(f"ADMIN_EMAILS from .env: {ADMIN_EMAILS}\n")
    
    # Find all users with admin role or in ADMIN_EMAILS
    admin_users = list(users_coll.find({"$or": [
        {"role": "admin"},
        {"email": {"$in": list(ADMIN_EMAILS)}}
    ]}))
    
    if not admin_users:
        print("✓ No admin users found in users collection")
        print("✓ Migration not needed\n")
        return
    
    print(f"Found {len(admin_users)} admin user(s) to migrate:\n")
    
    migrated = 0
    for user in admin_users:
        email = user.get("email")
        print(f"Migrating: {email}")
        
        # Check if already exists in admins collection
        existing = admins_coll.find_one({"email": email})
        if existing:
            print(f"  ⚠ Already exists in admins collection, skipping")
            # Delete from users collection
            users_coll.delete_one({"_id": user["_id"]})
            print(f"  ✓ Removed from users collection")
            continue
        
        # Copy to admins collection (without allowed_companies field)
        admin_doc = {
            "email": user.get("email"),
            "password_hash": user.get("password_hash"),
            "role": "admin",
            "created_at": user.get("created_at"),
            "last_login": user.get("last_login"),
            "version": user.get("version", 1)
        }
        
        try:
            admins_coll.insert_one(admin_doc)
            print(f"  ✓ Added to admins collection")
            
            # Remove from users collection
            users_coll.delete_one({"_id": user["_id"]})
            print(f"  ✓ Removed from users collection")
            
            migrated += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print(f"\n=== Migration Complete ===")
    print(f"Migrated {migrated} admin(s)")
    
    # Show final counts
    users_count = users_coll.count_documents({})
    admins_count = admins_coll.count_documents({})
    print(f"\nFinal counts:")
    print(f"  Users collection: {users_count}")
    print(f"  Admins collection: {admins_count}")

if __name__ == "__main__":
    migrate_admins()
