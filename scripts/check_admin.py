"""Quick script to check if admin user exists and test password"""
import os
import sys
from pymongo import MongoClient
from passlib.context import CryptContext

# Load from auth module which has dotenv
sys.path.insert(0, os.path.dirname(__file__))
from auth import get_mongo_collection, ADMIN_EMAILS, ADMIN_SEED_PASSWORD, verify_password

print("=== Admin Credentials from .env ===")
print(f"ADMIN_EMAILS: {ADMIN_EMAILS}")
print(f"ADMIN_SEED_PASSWORD: {ADMIN_SEED_PASSWORD}")
print()

print("=== Checking MongoDB ===")
coll = get_mongo_collection()

for email in ADMIN_EMAILS:
    print(f"\nLooking for user: {email}")
    user = coll.find_one({"email": email})
    
    if user:
        print(f"✓ User FOUND!")
        print(f"  Role: {user.get('role')}")
        print(f"  Created: {user.get('created_at')}")
        print(f"  Has password hash: {bool(user.get('password_hash'))}")
        
        # Test password verification
        if ADMIN_SEED_PASSWORD:
            pwd_hash = user.get('password_hash', '')
            is_valid = verify_password(ADMIN_SEED_PASSWORD, pwd_hash)
            print(f"  Password verification: {'✓ VALID' if is_valid else '✗ INVALID'}")
    else:
        print(f"✗ User NOT FOUND")
        print(f"  The _seed_admin_users() function may not have run")

print("\n=== All users in database ===")
all_users = list(coll.find({}, {"email": 1, "role": 1, "_id": 0}))
for u in all_users:
    print(f"  - {u.get('email')} (role: {u.get('role')})")

if not all_users:
    print("  No users found in database")
