#!/usr/bin/env python3
"""Test script to verify .env loading and admin user creation"""
from dotenv import load_dotenv
import os

load_dotenv()

print("=== Environment Variables ===")
print(f"ADMIN_EMAILS: {os.getenv('ADMIN_EMAILS')}")
print(f"ADMIN_SEED_PASSWORD: {os.getenv('ADMIN_SEED_PASSWORD')}")
print(f"AUTH_SECRET (first 20 chars): {os.getenv('AUTH_SECRET', '')[:20]}...")
print()

# Test MongoDB connection and check if admin user exists
try:
    from pymongo import MongoClient
    MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    USER_DB_NAME = os.getenv("USER_DB_NAME", "Auth")
    USER_COLLECTION = os.getenv("USER_COLLECTION", "users")
    
    print("=== MongoDB Connection ===")
    print(f"Connecting to: {MONGO_URI}")
    print(f"Database: {USER_DB_NAME}")
    print(f"Collection: {USER_COLLECTION}")
    
    client = MongoClient(MONGO_URI)
    db = client[USER_DB_NAME]
    coll = db[USER_COLLECTION]
    
    admin_email = os.getenv('ADMIN_EMAILS', '').strip()
    if admin_email:
        user = coll.find_one({"email": admin_email.lower()})
        print()
        print(f"=== Checking for admin user: {admin_email} ===")
        if user:
            print("✓ Admin user EXISTS in database")
            print(f"  - Email: {user.get('email')}")
            print(f"  - Role: {user.get('role')}")
            print(f"  - Password hash exists: {bool(user.get('password_hash'))}")
            print(f"  - Created at: {user.get('created_at')}")
            
            # Test password verification
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            password = os.getenv('ADMIN_SEED_PASSWORD')
            if password and user.get('password_hash'):
                is_valid = pwd_context.verify(password, user['password_hash'])
                print(f"  - Password verification: {'✓ VALID' if is_valid else '✗ INVALID'}")
        else:
            print("✗ Admin user NOT FOUND in database")
            print("  Run the server once to seed the admin user")
    
    client.close()
    
except Exception as e:
    print(f"Error: {e}")
