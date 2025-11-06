"""
Check if admin exists in admins collection
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
USER_DB_NAME = os.getenv("USER_DB_NAME", "Auth")

client = MongoClient(MONGO_URI)
db = client[USER_DB_NAME]

print("=== Checking Collections ===\n")

# Check users collection
users_coll = db["users"]
users = list(users_coll.find({}, {"password_hash": 0}))
print(f"Users collection ({len(users)} users):")
for user in users:
    print(f"  - {user['email']} (role: {user.get('role', 'N/A')})")

print()

# Check admins collection
admins_coll = db["admins"]
admins = list(admins_coll.find({}, {"password_hash": 0}))
print(f"Admins collection ({len(admins)} admins):")
for admin in admins:
    print(f"  - {admin['email']} (role: {admin.get('role', 'N/A')})")

if not admins:
    print("  ⚠ No admins found! Run the server to seed admin from .env")
