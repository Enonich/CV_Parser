"""Authentication module: user registration, login, JWT handling.
Modular so workflow.py stays clean.

Enhancements:
- Loads environment variables from a .env file (python-dotenv) if present.
- Optional automatic admin user seeding via ADMIN_EMAILS plus ADMIN_SEED_PASSWORD / ADMIN_SEED_PASSWORD_HASH.
"""
import os
import time
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from passlib.context import CryptContext
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from functools import wraps
try:  # dotenv is optional; fail gracefully if not installed
    from dotenv import load_dotenv
    load_dotenv()  # Load .env before reading environment variables
except Exception:
    pass

# Environment / settings (after dotenv load)
SECRET_KEY = os.getenv("AUTH_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
USER_DB_NAME = os.getenv("USER_DB_NAME", "Auth")
USER_COLLECTION = os.getenv("USER_COLLECTION", "users")
ADMIN_COLLECTION = os.getenv("ADMIN_COLLECTION", "admins")  # Separate collection for admins
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
ADMIN_SEED_PASSWORD = os.getenv("ADMIN_SEED_PASSWORD")  # Plain text (use only for initial seeding, then rotate)
ADMIN_SEED_PASSWORD_HASH = os.getenv("ADMIN_SEED_PASSWORD_HASH")  # Optional pre-hashed password (bcrypt)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme for docs compatibility (tokenUrl not used directly here)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

router = APIRouter(tags=["auth"])

# ---------- Pydantic Models ----------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    company: Optional[str] = None  # Single company association on self-register
    companies: Optional[list[str]] = None  # Admin can pass multiple

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class UserOut(BaseModel):
    email: EmailStr
    role: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None

# ---------- Utility Functions ----------

def get_mongo_collection():
    """Get the users collection."""
    client = MongoClient(MONGO_URI)
    db = client[USER_DB_NAME]
    coll = db[USER_COLLECTION]
    # Ensure unique index on email
    try:
        coll.create_index("email", unique=True)
    except Exception:
        pass
    return coll

def get_admin_collection():
    """Get the admins collection (separate from users)."""
    client = MongoClient(MONGO_URI)
    db = client[USER_DB_NAME]
    coll = db[ADMIN_COLLECTION]
    # Ensure unique index on email
    try:
        coll.create_index("email", unique=True)
    except Exception:
        pass
    return coll

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(UTC)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ---------- Optional Admin Seeding ----------
def _seed_admin_users():
    """Create admin users listed in ADMIN_EMAILS if they don't exist.
    Uses ADMIN_SEED_PASSWORD (plaintext hashed now) or ADMIN_SEED_PASSWORD_HASH (already bcrypt) if provided.
    If neither password variable is provided, seeding is skipped for security (avoids blank-password users).
    Admins are stored in a separate 'admins' collection.
    """
    if not ADMIN_EMAILS:
        return
    if not ADMIN_SEED_PASSWORD and not ADMIN_SEED_PASSWORD_HASH:
        # Intentionally skip seeding if no password specified
        return
    
    admin_coll = get_admin_collection()
    user_coll = get_mongo_collection()
    
    for email in ADMIN_EMAILS:
        # Check if admin already exists in admins collection
        existing_admin = admin_coll.find_one({"email": email})
        if existing_admin:
            continue  # Admin already exists
        
        # Remove from users collection if exists there
        user_coll.delete_one({"email": email})
        
        # Create admin in admins collection
        pwd_hash = ADMIN_SEED_PASSWORD_HASH or hash_password(ADMIN_SEED_PASSWORD)
        doc = {
            "email": email,
            "password_hash": pwd_hash,
            "role": "admin",
            "created_at": datetime.now(UTC).isoformat(),
            "last_login": None,
            "version": 1
        }
        try:
            admin_coll.insert_one(doc)
        except Exception:
            pass

# Perform seeding once at import time (safe idempotent operation)
try:
    _seed_admin_users()
except Exception:
    pass

# ---------- Core Auth Flow ----------
@router.post("/register", response_model=UserOut, status_code=201)
def register_user(payload: RegisterInput):
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    coll = get_mongo_collection()
    companies_list = []
    if payload.companies:
        companies_list = [c.strip() for c in payload.companies if c and c.strip()]
    elif payload.company:
        companies_list = [payload.company.strip()]
    doc = {
        "email": payload.email.lower().strip(),
        "password_hash": hash_password(payload.password),
        "role": "user",
        "allowed_companies": companies_list,  # raw names; sanitization used later
        "created_at": datetime.now(UTC).isoformat(),
        "last_login": None,
        "version": 1
    }
    try:
        coll.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    return UserOut(email=doc["email"], role=doc["role"], created_at=doc["created_at"], last_login=None)

@router.post("/login", response_model=Token)
def login(payload: LoginInput):
    email = payload.email.lower().strip()
    
    # First check admins collection
    admin_coll = get_admin_collection()
    admin = admin_coll.find_one({"email": email})
    
    if admin:
        # Verify admin password
        if not verify_password(payload.password, admin.get("password_hash", "")):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        # Update last_login
        admin_coll.update_one({"_id": admin["_id"]}, {"$set": {"last_login": datetime.now(UTC).isoformat()}})
        
        # Create token with admin role
        access_token = create_access_token({
            "sub": str(admin["_id"]),
            "email": admin["email"],
            "role": "admin",
            "allowed_companies": []  # Admins have access to all companies
        })
        return Token(access_token=access_token, expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    
    # If not admin, check users collection
    user_coll = get_mongo_collection()
    user = user_coll.find_one({"email": email})
    
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    # Update last_login
    user_coll.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.now(UTC).isoformat()}})
    
    # Create token for regular user
    access_token = create_access_token({
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": "user",
        "allowed_companies": user.get("allowed_companies", [])
    })
    return Token(access_token=access_token, expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60)

# ---------- Dependencies ----------

def get_current_user(token: str = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("email")
        role: str = payload.get("role", "user")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Check if admin (look in admins collection)
        if role == "admin":
            admin_coll = get_admin_collection()
            admin = admin_coll.find_one({"email": email})
            if not admin:
                raise HTTPException(status_code=401, detail="Admin not found")
            return {"email": email, "role": "admin", "allowed_companies": []}
        
        # Regular user (look in users collection)
        user_coll = get_mongo_collection()
        user = user_coll.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        allowed_companies = user.get("allowed_companies", [])
        return {"email": email, "role": "user", "allowed_companies": allowed_companies}
    except JWTError:
        raise HTTPException(status_code=401, detail="Token decode failed")

def require_admin(user = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

@router.get("/me")
def me(current = Depends(get_current_user)):
    """Get current user info. Checks both admins and users collections."""
    email = current["email"]
    role = current.get("role", "user")
    
    # Check admins collection first
    if role == "admin":
        admin_coll = get_admin_collection()
        admin = admin_coll.find_one({"email": email})
        if admin:
            return {
                "email": email,
                "role": "admin",
                "allowed_companies": [],  # Admins have access to all
                "created_at": admin.get("created_at"),
                "last_login": admin.get("last_login")
            }
    
    # Check users collection
    user_coll = get_mongo_collection()
    user = user_coll.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "email": email,
        "role": user.get("role", "user"),
        "allowed_companies": user.get("allowed_companies", []),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login")
    }

@router.get("/my-companies")
def my_companies(current = Depends(get_current_user)):
    coll = get_mongo_collection()
    user = coll.find_one({"email": current["email"]})
    return {"companies": user.get("allowed_companies", [])}

# Utility endpoint for token validity check
@router.get("/verify")
def verify_token(current = Depends(get_current_user)):
    return {"status": "ok", "email": current["email"], "role": current["role"]}

# ================= ADMIN ENDPOINTS ================= #
class AdminCreateUser(BaseModel):
    email: EmailStr
    password: str
    companies: list[str] = []
    role: str = "user"  # allow creation of another admin if current admin wants

class AdminAssignCompany(BaseModel):
    email: EmailStr
    company: str

class AdminRemoveCompany(BaseModel):
    email: EmailStr
    company: str

@router.get("/admin/users")
def list_users(admin = Depends(require_admin)):
    """List all users (excludes admins - they are in a separate collection)."""
    coll = get_mongo_collection()
    docs = list(coll.find({}, {"password_hash": 0}))
    for d in docs:
        d["_id"] = str(d.get("_id"))
    return {"users": docs}

@router.post("/admin/create-user")
def admin_create_user(payload: AdminCreateUser, admin = Depends(require_admin)):
    """Create a new user or admin. Admins go to admins collection, users to users collection."""
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    email = payload.email.lower().strip()
    role = payload.role if payload.role in {"user", "admin"} else "user"
    
    if role == "admin":
        # Create admin in admins collection
        admin_coll = get_admin_collection()
        doc = {
            "email": email,
            "password_hash": hash_password(payload.password),
            "role": "admin",
            "created_at": datetime.now(UTC).isoformat(),
            "last_login": None,
            "version": 1
        }
        try:
            admin_coll.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Email already exists")
    else:
        # Create user in users collection
        user_coll = get_mongo_collection()
        doc = {
            "email": email,
            "password_hash": hash_password(payload.password),
            "role": "user",
            "allowed_companies": [c.strip() for c in payload.companies if c.strip()],
            "created_at": datetime.now(UTC).isoformat(),
            "last_login": None,
            "version": 1
        }
        try:
            user_coll.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Email already exists")
    
    return {"status": "created", "email": email, "role": role}

@router.post("/admin/assign-company")
def admin_assign_company(payload: AdminAssignCompany, admin = Depends(require_admin)):
    coll = get_mongo_collection()
    res = coll.update_one({"email": payload.email.lower().strip()}, {"$addToSet": {"allowed_companies": payload.company.strip()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "assigned"}

@router.post("/admin/remove-company")
def admin_remove_company(payload: AdminRemoveCompany, admin = Depends(require_admin)):
    coll = get_mongo_collection()
    res = coll.update_one({"email": payload.email.lower().strip()}, {"$pull": {"allowed_companies": payload.company.strip()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "removed"}

@router.delete("/admin/user/{email}")
def admin_delete_user(email: str, admin = Depends(require_admin)):
    """Delete a user. Cannot delete admins from this endpoint."""
    email_l = email.lower().strip()
    
    # Prevent deletion of users in ADMIN_EMAILS
    if email_l in ADMIN_EMAILS:
        raise HTTPException(status_code=400, detail="Cannot delete admin users")
    
    # Only delete from users collection (not admins)
    coll = get_mongo_collection()
    res = coll.delete_one({"email": email_l})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted", "email": email_l}

# Export router & dependency for integration
auth_router = router
__all__ = ["auth_router", "get_current_user"]
