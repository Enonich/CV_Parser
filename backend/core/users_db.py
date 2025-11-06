"""User repository abstraction (currently thin wrapper around Mongo).
Separated for potential future swap to another store.
"""
import os
from datetime import datetime, UTC
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
USER_DB_NAME = os.getenv("USER_DB_NAME", "Auth")
USER_COLLECTION = os.getenv("USER_COLLECTION", "users")

class UserRepository:
    def __init__(self, uri: str = MONGO_URI, db_name: str = USER_DB_NAME, collection: str = USER_COLLECTION):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.coll = self.db[collection]
        try:
            self.coll.create_index("email", unique=True)
        except Exception:
            pass

    def create_user(self, email: str, password_hash: str, role: str = "user") -> Dict[str, Any]:
        doc = {
            "email": email.lower().strip(),
            "password_hash": password_hash,
            "role": role,
            "created_at": datetime.now(UTC).isoformat(),
            "last_login": None,
            "version": 1
        }
        try:
            self.coll.insert_one(doc)
        except DuplicateKeyError:
            raise ValueError("Email already exists")
        return doc

    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.coll.find_one({"email": email.lower().strip()})

    def update_last_login(self, email: str):
        self.coll.update_one({"email": email.lower().strip()}, {"$set": {"last_login": datetime.now(UTC).isoformat()}})

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass
