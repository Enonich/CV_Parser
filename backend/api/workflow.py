import os
import sys
import json
import yaml
import hashlib
from datetime import datetime
from pymongo import MongoClient
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Dict, Optional, Any

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from backend.core.auth import auth_router, get_current_user
from backend.core.identifiers import sanitize_fragment, build_collection_names, build_mongo_names, build_persist_directories, compute_cv_id
from backend.extractors.cv_extractor import CVProcessor
from backend.extractors.jd_extractor import JDExtractor
from backend.database.mongodb import CVDataInserter
from backend.database.mongodb_jd import JDDataInserter
from backend.embedders.cv_chroma_embedder import CVEmbedder
from backend.embedders.jd_embedder import JDEmbedder
from backend.core.fetch_top_k import CVJDVectorSearch
from backend.core.reranker import CVJDReranker
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory context cache (very simple, non-persistent)
from threading import Lock
_context_lock = Lock()
_last_context: Dict[str, str] = {"company_name": "", "job_title": ""}

# Load configuration from root directory
config_path = os.path.join(os.path.dirname(__file__), '../../config.yaml')
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

# Initialize FastAPI app
app = FastAPI(title="CV Parsing Automation API")
app.include_router(auth_router, prefix="/auth")

# Mount static files from root
static_path = os.path.join(os.path.dirname(__file__), '../../static')
app.mount("/static", StaticFiles(directory=static_path), name="static")

# OAuth2 for optional authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Ensure directories exist in root
root_dir = os.path.join(os.path.dirname(__file__), '../..')
os.makedirs(os.path.join(root_dir, "static/cvs"), exist_ok=True)
os.makedirs(os.path.join(root_dir, "static/jds"), exist_ok=True)
os.makedirs(os.path.join(root_dir, "static/extracted_files"), exist_ok=True)

# Initialize modules with config
cv_processor = CVProcessor()
jd_extractor = JDExtractor()
"""Global inserters retained for backward compatibility (default DB)."""
cv_data_inserter = CVDataInserter(
    connection_string=config["mongodb"]["connection_string"],
    db_name=config["mongodb"]["cv_db_name"],
    collection_name=config["mongodb"]["cv_collection_name"]
)
jd_data_inserter = JDDataInserter(
    connection_string=config["mongodb"]["connection_string"],
    db_name=config["mongodb"]["jd_db_name"],
    collection_name=config["mongodb"]["jd_collection_name"]
)
cv_embedder = CVEmbedder(
    model=config["embedding"]["model"],
    persist_directory=config["chroma"]["cv_persist_dir"],
    collection_name=config["chroma"]["cv_collection_name"]
)
jd_embedder = JDEmbedder(
    model=config["embedding"]["model"],
    persist_directory=config["chroma"]["jd_persist_dir"],
    collection_name=config["chroma"]["jd_collection_name"]
)
cvjd_vector_search = CVJDVectorSearch(
    cv_persist_dir=config["chroma"]["cv_persist_dir"],
    jd_persist_dir=config["chroma"]["jd_persist_dir"],
    cv_collection_name=config["chroma"]["cv_collection_name"],
    jd_collection_name=config["chroma"]["jd_collection_name"],
    model=config["embedding"]["model"],
    top_k_per_section=config["search"]["top_k_per_section"]
)

# Search configuration with hybrid 3-weight system
enable_cross_encoder: bool = bool(config.get("search", {}).get("enable_cross_encoder", False))
cross_encoder_model: str = config.get("search", {}).get("cross_encoder_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
enable_bm25: bool = bool(config.get("search", {}).get("enable_bm25", False))

# Hybrid scoring weights
vector_weight: float = float(config.get("search", {}).get("vector_weight", 0.4))
bm25_weight: float = float(config.get("search", {}).get("bm25_weight", 0.3))
cross_encoder_weight: float = float(config.get("search", {}).get("cross_encoder_weight", 0.3))

# Validate and normalize weights to sum to 1.0
total_weight = vector_weight + bm25_weight + cross_encoder_weight
if total_weight > 0:
    vector_weight /= total_weight
    bm25_weight /= total_weight
    cross_encoder_weight /= total_weight
else:
    # Fallback to equal weights
    vector_weight = bm25_weight = cross_encoder_weight = 1.0 / 3.0

logger.info(f"Hybrid scoring weights: vector={vector_weight:.3f}, bm25={bm25_weight:.3f}, cross_encoder={cross_encoder_weight:.3f}")

# Optional cross-encoder reranker initialization
reranker: CVJDReranker | None = None
if enable_cross_encoder:
    try:
        reranker = CVJDReranker(
            mongo_uri=config["mongodb"]["connection_string"],
            mongo_db=config["mongodb"]["cv_db_name"],
            cv_collection=config["mongodb"]["cv_collection_name"],
            jd_collection=config["mongodb"]["jd_collection_name"],
            model_name=cross_encoder_model
        )
        logger.info("Cross-encoder reranker initialized")
    except Exception as e:
        logger.warning(f"Cross-encoder initialization failed, proceeding without it: {e}")
        reranker = None

class SearchRequest(BaseModel):
    company_name: str
    job_title: str
    top_k_cvs: Optional[int] = config["search"]["top_k_cvs"]
    show_details: Optional[bool] = False
    jd_id: Optional[str] = None

def _enforce_company_access(company_name: str, current_user: Dict[str, Any]):
    allowed = current_user.get("allowed_companies", [])
    if allowed and company_name:
        # Raw names stored; compare case-insensitive
        if company_name.lower().strip() not in {c.lower().strip() for c in allowed}:
            raise HTTPException(status_code=403, detail="Access to company denied")

@app.post("/upload-cv/")
async def upload_cv(
    request: Request,
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Upload and process a CV file."""
    try:
        # Validate file type
        if not file.filename.lower().endswith((".pdf", ".docx", ".png", ".jpg", ".jpeg")):
            raise HTTPException(status_code=400, detail="Only PDF, DOCX, PNG, JPG, or JPEG files allowed")

        # Save file temporarily
        cv_path = f"./static/cvs/{file.filename}"
        with open(cv_path, "wb") as f:
            f.write(await file.read())
        # Parse form data (company_name, job_title)
        form = await request.form()
        company_name = (form.get("company_name") or "").strip()
        job_title = (form.get("job_title") or "").strip()
        logger.info(
            f"Received CV upload: file={file.filename}, form_keys={list(form.keys())}, company_name='{company_name}', job_title='{job_title}'"
        )

        # Hard validation: company & job required BEFORE any DB interaction
        if not company_name or not job_title:
            raise HTTPException(status_code=400, detail="company_name and job_title are required before uploading a CV")

        _enforce_company_access(company_name, current_user)
        # Multi-tenant dynamic names (Mongo + Chroma)
        db_name_dyn, cv_collection_mongo, jd_collection_mongo = build_mongo_names(company_name, job_title)
        cv_collection_dyn, jd_collection_dyn = build_collection_names(company_name, job_title)  # Chroma collections
        cv_persist_dir_dyn, jd_persist_dir_dyn = build_persist_directories(
            config["chroma"]["cv_persist_dir"],
            config["chroma"]["jd_persist_dir"],
            company_name
        )
        os.makedirs(cv_persist_dir_dyn, exist_ok=True)
        os.makedirs(jd_persist_dir_dyn, exist_ok=True)
        # Persist latest context (used for fallback in search)
        with _context_lock:
            if company_name:
                _last_context["company_name"] = company_name
            if job_title:
                _last_context["job_title"] = job_title

        # Process CV
        json_path = cv_processor.extract_and_save_cv(cv_path, "./static/extracted_files")
        if not json_path:
            raise HTTPException(status_code=500, detail="Failed to extract CV data")

        # Load CV data to check if it already exists
        with open(json_path, 'r', encoding='utf-8') as f:
            cv_data = json.load(f)
        
        structured_data = cv_data.get("CV_data", {}).get("structured_data", {})
        # Inject job context for later filtering
        structured_data["company_name"] = company_name
        structured_data["job_title"] = job_title
        # Persist injection back to file for consistency
        cv_data["CV_data"]["structured_data"] = structured_data
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cv_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist company/job additions to CV JSON: {e}")
        email = structured_data.get("email", "").strip()
        phone = structured_data.get("phone", "").strip()
        
        # Check if CV already exists
        # Use dynamic Mongo inserter per company/job
        cv_inserter_dyn = CVDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=cv_collection_mongo
        )
        existing_cv = cv_inserter_dyn.check_cv_exists(email=email, phone=phone)

        # Base flags
        duplicate_within_job = False
        existing_other_job_same_company = False

        # Compute cv_id now for cross-scope probing
        try:
            cv_id_probe = cv_inserter_dyn.generate_cv_id(email=email, phone=phone)
        except Exception:
            cv_id_probe = None

        if existing_cv:
            duplicate_within_job = True
            logger.info(
                f"[CV DUPLICATE] Candidate already exists for company='{company_name}' job='{job_title}' cv_id='{existing_cv.get('_id')}'"
            )
        else:
            # Cross-scope detection: look in OTHER job collections under same company
            if cv_id_probe:
                try:
                    from pymongo import MongoClient as _ScopedClient
                    scoped_client = _ScopedClient(config["mongodb"]["connection_string"])
                    company_db = scoped_client[db_name_dyn]
                    other_collections = [c for c in company_db.list_collection_names() if c.startswith("cvs_") and c != cv_collection_mongo]
                    for coll in other_collections:
                        other_doc = company_db[coll].find_one({"_id": cv_id_probe})
                        if other_doc:
                            existing_other_job_same_company = True
                            logger.info(f"[CV CROSS-SCOPE] Candidate cv_id='{cv_id_probe}' already present in collection='{coll}' (same company, different job)")
                            break
                except Exception as e_scoped:
                    logger.warning(f"Cross-scope CV detection failed (non-blocking): {e_scoped}")

            # Insert only if not duplicate in THIS job
            insertion_error = False
            insertion_error_code: str | None = None
            insertion_error_detail: str | None = None
            cv_insert_success = cv_inserter_dyn.process_cv_file(json_path)
            if not cv_insert_success:
                # Re-check existence to distinguish true duplicate vs insertion failure
                recheck_cv = CVDataInserter(
                    connection_string=config["mongodb"]["connection_string"],
                    db_name=db_name_dyn,
                    collection_name=cv_collection_mongo
                ).check_cv_exists(email=email, phone=phone)
                if recheck_cv:
                    duplicate_within_job = True
                    logger.info("[CV DUPLICATE CONFIRMED AFTER FAILED INSERT] Document already existed; safe duplicate flag.")
                else:
                    insertion_error = True
                    # Derive reason heuristically
                    if not email and not phone:
                        insertion_error_code = "missing_identifier"
                        insertion_error_detail = "Neither email nor phone extracted from CV; cannot generate unique ID."
                    else:
                        insertion_error_code = "insert_failed"
                        insertion_error_detail = "Insertion failed for unknown reason (not a duplicate). Check logs for prior extraction or DB errors."
                    logger.warning(f"[CV INSERTION ERROR] Not a duplicate but insert failed. code={insertion_error_code} detail={insertion_error_detail}")
            else:
                # CV insertion successful - DO NOT embed automatically
                # Embeddings will be generated on-demand during search
                logger.info(f"[CV UPLOAD] Successfully stored CV in MongoDB without embedding. Will embed during search.")

        # Ensure MongoDB connection is closed after all operations
        try:
            cv_inserter_dyn.close_connection()
        except Exception as e:
            logger.warning(f"Error closing CV inserter connection: {e}")

        # Clean up temporary CV file
        os.remove(cv_path)

        # Check if there was an insertion error and return appropriate status
        insertion_error_flag = insertion_error if 'insertion_error' in locals() else False
        insertion_error_code_val = insertion_error_code if 'insertion_error_code' in locals() else None
        insertion_error_detail_val = insertion_error_detail if 'insertion_error_detail' in locals() else None
        
        if insertion_error_flag:
            # Return 500 error if insertion failed
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": insertion_error_detail_val or "Failed to save CV to database",
                    "error_code": insertion_error_code_val,
                    "cv_json_path": json_path,
                    "company_name": company_name,
                    "job_title": job_title
                }
            )

        return JSONResponse(content={
            "status": "success",
            "cv_json_path": json_path,
            "existing": duplicate_within_job,
            "duplicate_within_job": duplicate_within_job,
            "existing_other_job_same_company": existing_other_job_same_company,
            "insertion_error": False,
            "company_name": company_name,
            "job_title": job_title
        })

    except HTTPException as e:
        logger.error(f"CV upload HTTP error: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Error processing CV: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing CV: {str(e)}")

@app.post("/upload-jd/")
async def upload_jd(
    request: Request,
    file: UploadFile = File(None),
    jd_text: str = Form(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Upload and process a job description file or text."""
    try:
        # Validate input - must have either file or text
        if not file and not jd_text:
            raise HTTPException(status_code=400, detail="Either file or jd_text must be provided")
        
        if file and jd_text:
            raise HTTPException(status_code=400, detail="Provide either file or text, not both")

        # Parse form data (company_name, job_title)
        form = await request.form()
        company_name = (form.get("company_name") or "").strip()
        job_title = (form.get("job_title") or "").strip()
        
        if file:
            # File mode - validate and save
            if not file.filename.lower().endswith((".txt", ".pdf", ".docx")):
                raise HTTPException(status_code=400, detail="Only TXT, PDF, or DOCX files allowed")

            # Save file temporarily
            jd_path = f"./static/jds/{file.filename}"
            with open(jd_path, "wb") as f:
                f.write(await file.read())
            
            logger.info(f"[JD FILE] Received file: {file.filename}, company='{company_name}', job='{job_title}'")
        else:
            # Text mode - create temporary text file
            sanitized_job = sanitize_fragment(job_title)
            jd_filename = f"{sanitized_job}_jd.txt"
            jd_path = f"./static/jds/{jd_filename}"
            with open(jd_path, "w", encoding="utf-8") as f:
                f.write(jd_text)
            
            logger.info(f"[JD TEXT] Received text input ({len(jd_text)} chars), company='{company_name}', job='{job_title}'")

        _enforce_company_access(company_name, current_user)
        # Multi-tenant dynamic names (Mongo + Chroma)
        db_name_dyn, cv_collection_mongo, jd_collection_mongo = build_mongo_names(company_name, job_title)
        cv_collection_dyn, jd_collection_dyn = build_collection_names(company_name, job_title)
        cv_persist_dir_dyn, jd_persist_dir_dyn = build_persist_directories(
            config["chroma"]["cv_persist_dir"],
            config["chroma"]["jd_persist_dir"],
            company_name
        )
        os.makedirs(cv_persist_dir_dyn, exist_ok=True)
        os.makedirs(jd_persist_dir_dyn, exist_ok=True)
        # Persist latest context (used for fallback in search)
        with _context_lock:
            if company_name:
                _last_context["company_name"] = company_name
            if job_title:
                _last_context["job_title"] = job_title

        # Process JD
        filename_base = os.path.splitext(os.path.basename(jd_path))[0]
        json_path = f"./static/extracted_files/{filename_base}.json"
        jd_data = jd_extractor.extract(jd_path)
        if not jd_data:
            raise HTTPException(status_code=500, detail="Failed to extract JD data")

        # Wrap JD data with company/job context + sanitized variants for robust querying
        jd_wrapper = {
            "structured_data": jd_data.get("structured_data") if isinstance(jd_data, dict) and jd_data.get("structured_data") else jd_data,
            "company_name": company_name,
            "job_title": job_title,
            "company_name_sanitized": sanitize_fragment(company_name),
            "job_title_sanitized": sanitize_fragment(job_title)
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(jd_wrapper, f, indent=2)

        # Generate JD ID using same deterministic logic as JDDataInserter (sanitized job title)
        temp_inserter_for_id = JDDataInserter()
        jd_id = temp_inserter_for_id.generate_jd_id(job_title, company_name)

        # Check if JD already exists
        jd_inserter_dyn = JDDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=jd_collection_mongo
        )
        existing_jd = jd_inserter_dyn.check_jd_exists(jd_id=jd_id)

        if existing_jd:
            logger.info(f"JD already exists for company='{company_name}' job_title='{job_title}' (_id={jd_id})")
            # Ensure MongoDB connection is closed
            try:
                jd_inserter_dyn.close_connection()
            except Exception as e:
                logger.warning(f"Error closing JD inserter connection: {e}")
            os.remove(jd_path)
            return JSONResponse(content={
                "status": "success",
                "jd_json_path": json_path,
                "jd_id": jd_id,
                "message": "Job Description already exists in database",
                "existing": True
            })
        else:
            jd_insert_success = jd_inserter_dyn.process_jd_file(json_path)
            if not jd_insert_success:
                # Re-check to distinguish duplicate from actual failure
                recheck_jd = jd_inserter_dyn.check_jd_exists(jd_id=jd_id)
                
                # Ensure MongoDB connection is closed
                try:
                    jd_inserter_dyn.close_connection()
                except Exception as e:
                    logger.warning(f"Error closing JD inserter connection: {e}")
                
                os.remove(jd_path)
                
                if recheck_jd:
                    # It was actually a duplicate race condition
                    logger.warning("JD insertion failed - confirmed duplicate race condition")
                    return JSONResponse(content={
                        "status": "success",
                        "jd_json_path": json_path,
                        "jd_id": jd_id,
                        "message": "Job Description already exists in database",
                        "existing": True
                    })
                else:
                    # Actual insertion failure
                    logger.error(f"[JD INSERTION ERROR] Failed to insert JD for job='{job_title}' company='{company_name}'")
                    return JSONResponse(
                        status_code=500,
                        content={
                            "status": "error",
                            "message": "Failed to save Job Description to database",
                            "error_code": "jd_insert_failed",
                            "jd_json_path": json_path,
                            "company_name": company_name,
                            "job_title": job_title
                        }
                    )
            
            jd_embedder_dyn = JDEmbedder(
                model=config["embedding"]["model"],
                persist_directory=jd_persist_dir_dyn,
                collection_name=jd_collection_dyn
            )
            # DO NOT embed automatically - will embed during search
            logger.info(f"[JD UPLOAD] Successfully stored JD in MongoDB without embedding. Will embed during search.")

        # Ensure MongoDB connection is closed after all operations
        try:
            jd_inserter_dyn.close_connection()
        except Exception as e:
            logger.warning(f"Error closing JD inserter connection: {e}")

        # Clean up temporary JD file
        os.remove(jd_path)
        return JSONResponse(content={"status": "success", "jd_json_path": json_path, "jd_id": jd_id})

    except HTTPException as e:
        logger.error(f"JD upload HTTP error: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Error processing JD: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing JD: {str(e)}")

@app.get("/data-status/")
async def check_data_status(
    company_name: str,
    job_title: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Check if both CVs and JD exist for a given company and job title."""
    try:
        _enforce_company_access(company_name, current_user)
        
        # Get dynamic names
        db_name_dyn, cv_collection_mongo, jd_collection_mongo = build_mongo_names(company_name, job_title)
        
        # Check for CVs
        cv_inserter = CVDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=cv_collection_mongo
        )
        
        # Connect and count CVs
        if not cv_inserter.connect_to_database():
            raise HTTPException(status_code=500, detail="Failed to connect to CV database")
        
        cv_count = cv_inserter.collection.count_documents({})
        cv_inserter.close_connection()
        
        # Check for JD
        temp_inserter_for_id = JDDataInserter()
        jd_id = temp_inserter_for_id.generate_jd_id(job_title, company_name)
        
        jd_inserter = JDDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=jd_collection_mongo
        )
        jd_exists = jd_inserter.check_jd_exists(jd_id=jd_id) is not None
        
        # Ensure connection is closed
        try:
            jd_inserter.close_connection()
        except Exception as e:
            logger.warning(f"Error closing JD inserter connection in data-status: {e}")
        
        return JSONResponse(content={
            "cv_count": cv_count,
            "jd_exists": jd_exists,
            "can_search": cv_count > 0 and jd_exists,
            "company_name": company_name,
            "job_title": job_title
        })
        
    except Exception as e:
        logger.error(f"Error checking data status: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking data status: {str(e)}")

@app.post("/search-cvs/")
async def search_cvs(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Search and rank CVs against the stored job description.

    Manual body parsing is used to avoid 422 issues from Pydantic when optional fields are missing
    or malformed on the frontend. Provides clearer validation errors.
    """
    try:
        raw_body = await request.body()
        body_text = raw_body.decode("utf-8") if raw_body else "{}"
        logger.info(f"/search-cvs/ raw body length={len(body_text)} text={body_text}")
        diag_headers = {k: v for k, v in request.headers.items() if k.lower() in ["content-type", "user-agent", "accept", "x-company-name", "x-job-title"]}
        logger.info(f"/search-cvs/ headers: {diag_headers}")
        try:
            payload = json.loads(body_text or "{}")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

        company_name = (payload.get("company_name") or "").strip()
        job_title = (payload.get("job_title") or "").strip()
        jd_id_raw = (payload.get("jd_id") or "").strip()
        top_k_cvs = payload.get("top_k_cvs")
        show_details = bool(payload.get("show_details", False))
        logger.info(f"/search-cvs/ parsed keys: {list(payload.keys())}; company_name='{company_name}' job_title='{job_title}' jd_id='{jd_id_raw}' top_k_cvs={top_k_cvs}")

        # Fallback sources if missing
        if not company_name or not job_title:
            qp_company = (request.query_params.get("company_name") or "").strip()
            qp_job = (request.query_params.get("job_title") or "").strip()
            header_company = (request.headers.get("X-Company-Name") or "").strip()
            header_job = (request.headers.get("X-Job-Title") or "").strip()
            with _context_lock:
                cached_company = _last_context.get("company_name", "").strip()
                cached_job = _last_context.get("job_title", "").strip()
            if not company_name and qp_company:
                company_name = qp_company
            if not job_title and qp_job:
                job_title = qp_job
            if not company_name and header_company:
                company_name = header_company
            if not job_title and header_job:
                job_title = header_job
            if not company_name and cached_company:
                company_name = cached_company
            if not job_title and cached_job:
                job_title = cached_job
            logger.info(f"/search-cvs/ after fallbacks: company_name='{company_name}' job_title='{job_title}' (cached_company='{cached_company}' cached_job='{cached_job}')")

        errors: List[str] = []
        if not company_name:
            errors.append("company_name is required")
        if not job_title:
            errors.append("job_title is required")
        if top_k_cvs is None or not isinstance(top_k_cvs, int) or top_k_cvs <= 0:
            cfg_default = int(config["search"].get("top_k_cvs", 5))
            logger.info(f"Using fallback top_k_cvs={cfg_default} (provided={top_k_cvs})")
            top_k_cvs = cfg_default
        if errors:
            raise HTTPException(status_code=400, detail=errors)

        _enforce_company_access(company_name, current_user)
        
        # Get MongoDB collections info
        db_name_dyn, cv_collection_mongo, jd_collection_mongo = build_mongo_names(company_name, job_title)
        
        cv_collection_dyn, jd_collection_dyn = build_collection_names(company_name, job_title)
        cv_persist_dir_dyn, jd_persist_dir_dyn = build_persist_directories(
            config["chroma"]["cv_persist_dir"],
            config["chroma"]["jd_persist_dir"],
            company_name
        )
        logger.info(f"Dynamic collections resolved: CV='{cv_collection_dyn}' JD='{jd_collection_dyn}' persist_cv='{cv_persist_dir_dyn}' persist_jd='{jd_persist_dir_dyn}'")

        # ========== EMBEDDING ON DEMAND ==========
        # Before searching, ensure all CVs and the JD are embedded
        logger.info(f"[SEARCH] Starting on-demand embedding for company='{company_name}' job='{job_title}'")
        
        # Check if JD exists and embed it
        temp_inserter_for_id = JDDataInserter()
        jd_id = temp_inserter_for_id.generate_jd_id(job_title, company_name)
        
        jd_inserter = JDDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=jd_collection_mongo
        )
        jd_doc = jd_inserter.check_jd_exists(jd_id=jd_id)
        
        if not jd_doc:
            raise HTTPException(
                status_code=404, 
                detail=f"No job description found for {job_title}. Please upload a JD first."
            )
        
        # Embed JD if not already embedded
        os.makedirs(jd_persist_dir_dyn, exist_ok=True)
        jd_embedder_dyn = JDEmbedder(
            model=config["embedding"]["model"],
            persist_directory=jd_persist_dir_dyn,
            collection_name=jd_collection_dyn
        )
        
        # Check if JD is already embedded (check if collection exists and has documents)
        try:
            from langchain_chroma import Chroma
            from langchain_ollama import OllamaEmbeddings
            test_embeddings = OllamaEmbeddings(model=config["embedding"]["model"])
            test_vectorstore = Chroma(
                collection_name=jd_collection_dyn,
                embedding_function=test_embeddings,
                persist_directory=jd_persist_dir_dyn
            )
            jd_embedded_count = test_vectorstore._collection.count()
            logger.info(f"[SEARCH] JD embedding check: {jd_embedded_count} documents in vector store")
        except Exception as e:
            logger.warning(f"[SEARCH] Could not check JD embeddings: {e}")
            jd_embedded_count = 0
        
        if jd_embedded_count == 0:
            logger.info(f"[SEARCH] Embedding JD for job_title='{job_title}'...")
            # Recreate JD file from MongoDB document for embedding
            jd_temp_path = f"./static/extracted_files/temp_jd_{jd_id}.json"
            
            # Helper function to serialize datetime objects
            def serialize_datetime(obj):
                """Recursively convert datetime objects to ISO format strings."""
                if isinstance(obj, dict):
                    return {k: serialize_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_datetime(item) for item in obj]
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                else:
                    return obj
            
            # Serialize the JD document
            jd_doc_serialized = serialize_datetime(jd_doc)
            
            with open(jd_temp_path, "w", encoding="utf-8") as f:
                json.dump(jd_doc_serialized, f, indent=2)
            
            if not jd_embedder_dyn.embed_job_description_from_json(jd_temp_path):
                os.remove(jd_temp_path) if os.path.exists(jd_temp_path) else None
                raise HTTPException(status_code=500, detail="Failed to embed JD")
            
            os.remove(jd_temp_path) if os.path.exists(jd_temp_path) else None
            logger.info(f"[SEARCH] JD embedded successfully")
        else:
            logger.info(f"[SEARCH] JD already embedded ({jd_embedded_count} docs)")
        
        # Check if CVs exist and embed them
        cv_inserter = CVDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=cv_collection_mongo
        )
        
        # Connect to database to initialize collection
        if not cv_inserter.connect_to_database():
            raise HTTPException(status_code=500, detail="Failed to connect to CV database")
        
        cv_docs = list(cv_inserter.collection.find({}))
        cv_inserter.close_connection()
        
        if not cv_docs:
            raise HTTPException(
                status_code=404,
                detail=f"No CVs found for {job_title}. Please upload CVs first."
            )
        
        logger.info(f"[SEARCH] Found {len(cv_docs)} CVs in MongoDB")
        
        # Check if CVs are embedded
        os.makedirs(cv_persist_dir_dyn, exist_ok=True)
        unique_cv_ids_embedded = set()
        try:
            test_cv_vectorstore = Chroma(
                collection_name=cv_collection_dyn,
                embedding_function=test_embeddings,
                persist_directory=cv_persist_dir_dyn
            )
            cv_embedded_count = test_cv_vectorstore._collection.count()
            
            # Check unique CV IDs (this is what matters!)
            try:
                all_docs = test_cv_vectorstore.get()
                if all_docs and 'metadatas' in all_docs:
                    for meta in all_docs['metadatas']:
                        if meta and 'cv_id' in meta:
                            unique_cv_ids_embedded.add(meta['cv_id'])
                logger.info(f"[SEARCH] CV embedding check: {cv_embedded_count} documents, {len(unique_cv_ids_embedded)} unique CVs in vector store")
            except Exception as e:
                logger.warning(f"[SEARCH] Could not count unique CVs: {e}")
                
        except Exception as e:
            logger.warning(f"[SEARCH] Could not check CV embeddings: {e}")
            cv_embedded_count = 0
        
        # Get CV IDs from MongoDB to compare
        cv_ids_in_mongo = set(str(cv_doc['_id']) for cv_doc in cv_docs)
        missing_cv_ids = cv_ids_in_mongo - unique_cv_ids_embedded
        
        # If any CVs are missing, clear everything and re-embed all
        # This avoids ChromaDB persistence issues with partial embeddings
        if missing_cv_ids or len(unique_cv_ids_embedded) != len(cv_docs):
            if missing_cv_ids:
                logger.info(f"[SEARCH] Missing {len(missing_cv_ids)} CVs from vector store")
                logger.info(f"[SEARCH] Missing CV IDs: {list(missing_cv_ids)[:5]}...")  # Show first 5
            
            logger.warning(f"[SEARCH] Mismatch detected! ChromaDB has {len(unique_cv_ids_embedded)} CVs but MongoDB has {len(cv_docs)} CVs")
            logger.info(f"[SEARCH] Clearing ChromaDB collection and re-embedding all {len(cv_docs)} CVs to ensure consistency...")
            
            try:
                # Delete the entire collection to start fresh
                test_cv_vectorstore._client.delete_collection(cv_collection_dyn)
                logger.info(f"[SEARCH] ✓ Cleared collection '{cv_collection_dyn}'")
            except Exception as e:
                logger.warning(f"[SEARCH] Could not delete collection (may not exist): {e}")
            
            # Re-create embedder with fresh collection
            cv_embedder_dyn = CVEmbedder(
                model=config["embedding"]["model"],
                persist_directory=cv_persist_dir_dyn,
                collection_name=cv_collection_dyn
            )
            
            # Helper function to serialize datetime objects
            def serialize_datetime(obj):
                """Recursively convert datetime objects to ISO format strings."""
                if isinstance(obj, dict):
                    return {k: serialize_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_datetime(item) for item in obj]
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                else:
                    return obj
            
            # Embed each CV from MongoDB
            embedded_count = 0
            failed_cvs = []
            
            for idx, cv_doc in enumerate(cv_docs, 1):
                cv_id = cv_doc.get('_id', f'unknown_{idx}')
                try:
                    logger.info(f"[SEARCH] Embedding CV {idx}/{len(cv_docs)}: {cv_id}")
                    
                    # Serialize the CV document to handle datetime objects
                    cv_doc_serialized = serialize_datetime(cv_doc)
                    
                    # Create temp file from MongoDB document
                    cv_temp_path = f"./static/extracted_files/temp_cv_{cv_id}.json"
                    cv_wrapper = {"CV_data": {"structured_data": cv_doc_serialized}}
                    
                    with open(cv_temp_path, "w", encoding="utf-8") as f:
                        json.dump(cv_wrapper, f, indent=2)
                    
                    embed_result = cv_embedder_dyn.embed_cv(cv_temp_path)
                    
                    if embed_result:
                        embedded_count += 1
                        logger.info(f"[SEARCH] ✓ Successfully embedded CV {cv_id}")
                    else:
                        failed_cvs.append(cv_id)
                        logger.error(f"[SEARCH] ✗ Failed to embed CV {cv_id} - embed_cv returned False")
                    
                    # Clean up temp file
                    if os.path.exists(cv_temp_path):
                        os.remove(cv_temp_path)
                        
                except Exception as e:
                    failed_cvs.append(cv_id)
                    logger.error(f"[SEARCH] ✗ Exception embedding CV {cv_id}: {type(e).__name__}: {str(e)}")
                    # Clean up temp file in case of error
                    cv_temp_path = f"./static/extracted_files/temp_cv_{cv_id}.json"
                    if os.path.exists(cv_temp_path):
                        os.remove(cv_temp_path)
                    continue
            
            logger.info(f"[SEARCH] Embedding complete: {embedded_count}/{len(cv_docs)} CVs successfully embedded")
            
            if failed_cvs:
                logger.warning(f"[SEARCH] Failed CVs: {', '.join(str(cv) for cv in failed_cvs)}")
            
            if embedded_count == 0:
                raise HTTPException(status_code=500, detail="Failed to embed any CVs")
        else:
            logger.info(f"[SEARCH] CVs already embedded ({cv_embedded_count} docs)")
        
        # ========== NOW PROCEED WITH SEARCH ==========
        logger.info(f"[SEARCH] Starting vector search with embedded data")

        searcher = CVJDVectorSearch(
            cv_persist_dir=cv_persist_dir_dyn,
            jd_persist_dir=jd_persist_dir_dyn,
            cv_collection_name=cv_collection_dyn,
            jd_collection_name=jd_collection_dyn,
            model=config["embedding"]["model"],
            top_k_per_section=config["search"]["top_k_per_section"]
        )
        results = searcher.search_and_score_cvs(top_k_cvs=top_k_cvs)
        if not results:
            raise HTTPException(status_code=404, detail="No CVs found or no JD available for this context")

        jd_id_used: Optional[str] = None
        reranker_meta: Dict[str, Any] = {}
        if enable_cross_encoder and reranker:
            try:
                calibration_mode = payload.get("calibrate") if isinstance(payload.get("calibrate"), str) else None
                use_meta = True
                if jd_id_raw:
                    res_tuple = reranker.rerank_cvs_with_jd_id(
                        results,
                        company_name=company_name,
                        job_title=job_title,
                        jd_id=jd_id_raw,
                        calibrate=calibration_mode,
                        with_meta=use_meta
                    )
                    results, reranker_meta = res_tuple if isinstance(res_tuple, tuple) else (res_tuple, {})
                    jd_id_used = jd_id_raw
                    logger.info(f"Applied explicit jd_id reranking (jd_id='{jd_id_raw}') meta={reranker_meta}")
                    rerank_mode = "explicit_jd_id"
                else:
                    derived_jd_id = sanitize_fragment(job_title)
                    res_tuple = reranker.rerank_cvs_with_jd_id(
                        results,
                        company_name=company_name,
                        job_title=job_title,
                        jd_id=derived_jd_id,
                        calibrate=calibration_mode,
                        with_meta=use_meta
                    )
                    derived_results, derived_meta = res_tuple if isinstance(res_tuple, tuple) else (res_tuple, {})
                    if any(isinstance(r.get("cross_encoder_score"), (int, float)) for r in derived_results):
                        results = derived_results
                        reranker_meta = derived_meta
                        jd_id_used = derived_jd_id
                        logger.info(f"Applied derived sanitized jd_id reranking (jd_id='{derived_jd_id}') meta={reranker_meta}")
                        rerank_mode = "derived_jd_id"
                    else:
                        res_tuple2 = reranker.rerank_cvs_for_job(
                            results,
                            company_name=company_name,
                            job_title=job_title,
                            calibrate=calibration_mode,
                            with_meta=use_meta
                        )
                        results, reranker_meta = res_tuple2 if isinstance(res_tuple2, tuple) else (res_tuple2, {})
                        logger.info(f"Applied for_job reranking meta={reranker_meta}")
                        rerank_mode = "for_job"
            except Exception as e:
                logger.warning(f"Cross-encoder reranking failed: {e}")
                rerank_mode = "error"
        else:
            rerank_mode = "disabled"

        # ========================================
        # HYBRID 3-WEIGHT SCORING SYSTEM
        # Combines: vector_score + bm25_score + cross_encoder_score
        # ========================================
        
        # Normalize cross-encoder scores to [0, 1]
        ce_scores = [r.get("cross_encoder_score") for r in results if isinstance(r.get("cross_encoder_score"), (int, float))]
        if ce_scores:
            ce_min, ce_max = min(ce_scores), max(ce_scores)
            ce_span = ce_max - ce_min if ce_max != ce_min else 1.0
        
        # Normalize BM25 scores to [0, 1] (should already be normalized, but ensure)
        bm25_scores_list = [r.get("bm25_score") for r in results if isinstance(r.get("bm25_score"), (int, float))]
        if bm25_scores_list:
            bm25_min, bm25_max = min(bm25_scores_list), max(bm25_scores_list)
            bm25_span = bm25_max - bm25_min if bm25_max != bm25_min else 1.0
        
        # Compute hybrid combined score for each result
        for r in results:
            # Vector score (already normalized 0-1 from vector search)
            vector_score = r.get("total_score", 0.0)
            
            # BM25 score (normalized 0-1)
            bm25_raw = r.get("bm25_score")
            if isinstance(bm25_raw, (int, float)) and bm25_scores_list:
                bm25_norm = (bm25_raw - bm25_min) / bm25_span
            else:
                bm25_norm = 0.0
            
            # Cross-encoder score (normalized 0-1)
            ce_raw = r.get("cross_encoder_score")
            if isinstance(ce_raw, (int, float)) and ce_scores:
                ce_norm = (ce_raw - ce_min) / ce_span
            else:
                ce_norm = 0.0
            
            # Hybrid score with configurable weights
            # If BM25 disabled, redistribute its weight to vector and CE
            if enable_bm25 and bm25_norm > 0:
                r["combined_score"] = (
                    vector_weight * vector_score + 
                    bm25_weight * bm25_norm + 
                    cross_encoder_weight * ce_norm
                )
            else:
                # BM25 disabled or no scores: use 2-component blend
                total_w = vector_weight + cross_encoder_weight
                if total_w > 0:
                    r["combined_score"] = (
                        (vector_weight / total_w) * vector_score + 
                        (cross_encoder_weight / total_w) * ce_norm
                    )
                else:
                    r["combined_score"] = vector_score
            
            # Store individual normalized scores for debugging
            r["vector_score_normalized"] = vector_score
            r["bm25_score_normalized"] = bm25_norm
            r["ce_score_normalized"] = ce_norm
        
        # Sort by combined score
        results.sort(key=lambda x: x.get("combined_score", x.get("total_score", 0.0)), reverse=True)

        # Trim results to top_k_cvs after all scoring and sorting is complete
        results = results[:top_k_cvs]
        logger.info(f"Trimmed results to top {top_k_cvs} candidates")

        # Fetch actual identifiers (email/phone) from MongoDB for each CV
        # Use the multi-tenant database (company-specific) to get real identifiers
        cv_inserter_for_lookup = CVDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=cv_collection_mongo
        )
        if not cv_inserter_for_lookup.connect_to_database():
            logger.warning("Failed to connect to MongoDB for identifier lookup")
        
        response = []
        for result in results:
            cv_id = result["cv_id"]
            
            # Fetch the actual email/phone from MongoDB instead of using hash
            original_identifier = cv_id  # Default to hash if lookup fails
            candidate_name = "Unknown"
            try:
                if cv_inserter_for_lookup.collection is not None:
                    doc = cv_inserter_for_lookup.collection.find_one(
                        {"_id": cv_id}, 
                        {"email": 1, "phone": 1, "name": 1}
                    )
                    if doc:
                        original_identifier = doc.get("email") or doc.get("phone") or cv_id
                        candidate_name = doc.get("name", "Unknown")
                        logger.debug(f"Resolved cv_id {cv_id[:8]}... to {original_identifier}, name: {candidate_name}")
            except Exception as e:
                logger.warning(f"Failed to lookup identifier for cv_id {cv_id}: {e}")
            
            response.append({
                "cv_id": cv_id,
                "original_identifier": original_identifier,
                "name": candidate_name,
                "total_score": result["total_score"],
                "bm25_score": result.get("bm25_score"),
                "cross_encoder_score": result.get("cross_encoder_score"),
                "combined_score": result.get("combined_score"),
                "ce_status": result.get("ce_status"),
                "section_scores": result.get("cross_encoder_section_scores", result["section_scores"]),
                "section_details": result["section_details"] if show_details else {}
            })
        
        # Close the lookup connection
        try:
            cv_inserter_for_lookup.close_connection()
        except Exception as e:
            logger.warning(f"Error closing lookup connection: {e}")
        ce_present = any(isinstance(r.get("cross_encoder_score"), (int, float)) for r in results)
        bm25_present = any(isinstance(r.get("bm25_score"), (int, float)) for r in results)
        meta = {
            "rerank_mode": rerank_mode,
            "cross_encoder_enabled": enable_cross_encoder and reranker is not None,
            "cross_encoder_scores_present": ce_present,
            "bm25_enabled": enable_bm25,
            "bm25_scores_present": bm25_present,
            "scoring_weights": {
                "vector_weight": vector_weight,
                "bm25_weight": bm25_weight,
                "cross_encoder_weight": cross_encoder_weight
            },
            "jd_id_used": jd_id_used,
            "total_results": len(results),
            "reranker_meta": reranker_meta
        }
        # Ensure MongoDB connections are closed
        try:
            if 'jd_inserter' in locals():
                jd_inserter.close_connection()
            if 'cv_inserter' in locals():
                cv_inserter.close_connection()
        except Exception as e:
            logger.warning(f"Error closing search connections: {e}")

        return JSONResponse(content={
            "status": "success",
            "results": response,
            "company_name": company_name,
            "job_title": job_title,
            "jd_id_used": jd_id_used,
            "meta": meta
        })
    except HTTPException as e:
        # Cleanup connections on error
        try:
            if 'jd_inserter' in locals():
                jd_inserter.close_connection()
            if 'cv_inserter' in locals():
                cv_inserter.close_connection()
        except Exception:
            pass
        logger.warning(f"Search validation or processing error: {e.detail}")
        raise e
    except Exception as e:
        # Cleanup connections on error
        try:
            if 'jd_inserter' in locals():
                jd_inserter.close_connection()
            if 'cv_inserter' in locals():
                cv_inserter.close_connection()
        except Exception:
            pass
        logger.error(f"Unexpected error searching CVs: {e}")
        raise HTTPException(status_code=500, detail=f"Error searching CVs: {str(e)}")

@app.post("/echo")
async def echo_payload(request: Request):
    """Diagnostic endpoint: returns raw body, parsed JSON, selected headers."""
    raw = await request.body()
    body_text = raw.decode("utf-8") if raw else ""
    try:
        parsed = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        parsed = {"_error": "invalid JSON"}
    headers_subset = {k: v for k, v in request.headers.items() if k.lower() in ["content-type", "user-agent", "accept", "x-company-name", "x-job-title"]}
    return JSONResponse(content={
        "raw": body_text,
        "parsed": parsed,
        "headers": headers_subset,
        "last_context": _last_context
    })

@app.get("/")
async def root():
    """Serve the main web application."""
    return FileResponse('static/index.html')

@app.get("/cv/{company_name}/{job_title}/{cv_id}")
async def get_cv_details(
    company_name: str,
    job_title: str,
    cv_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get detailed CV information for viewing."""
    try:
        _enforce_company_access(company_name, current_user)
        
        db_name_dyn, cv_collection_mongo, _ = build_mongo_names(company_name, job_title)
        cv_inserter_dyn = CVDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=cv_collection_mongo
        )
        
        # Fetch CV by ID
        cv_data = cv_inserter_dyn.get_cv_by_id(cv_id)
        
        if not cv_data:
            raise HTTPException(status_code=404, detail=f"CV with ID '{cv_id}' not found")
        
        # Convert datetime objects to strings for JSON serialization
        def serialize_datetime(obj):
            """Recursively convert datetime objects to ISO format strings"""
            if isinstance(obj, dict):
                return {k: serialize_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_datetime(item) for item in obj]
            elif hasattr(obj, 'isoformat'):  # datetime, date, time objects
                return obj.isoformat()
            elif isinstance(obj, (bytes, bytearray)):
                return obj.decode('utf-8', errors='ignore')
            else:
                return obj
        
        cv_data = serialize_datetime(cv_data)
        
        # Ensure _id is string
        if '_id' in cv_data:
            cv_data['_id'] = str(cv_data['_id'])
        
        # Log email for debugging
        logger.info(f"Returning CV with email: {cv_data.get('email', 'NOT_FOUND')}")
        
        return JSONResponse(content=cv_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving CV details: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving CV: {str(e)}")

@app.get("/existing-cvs/")
async def get_existing_cvs(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get list of existing CVs filtered by company & job (multi-tenant).

    Query params (optional): company_name, job_title
    Fallback to last cached context if missing.
    """
    try:
        qp_company = (request.query_params.get("company_name") or "").strip()
        qp_job = (request.query_params.get("job_title") or "").strip()
        with _context_lock:
            company_name = qp_company or _last_context.get("company_name", "")
            job_title = qp_job or _last_context.get("job_title", "")
        if not company_name or not job_title:
            raise HTTPException(status_code=400, detail="company_name and job_title required (query or prior context)")
        _enforce_company_access(company_name, current_user)

        db_name_dyn, cv_collection_mongo, _ = build_mongo_names(company_name, job_title)
        cv_inserter_dyn = CVDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=cv_collection_mongo
        )
        existing_cvs = cv_inserter_dyn.get_all_cvs()
        response = []
        for cv in existing_cvs:
            response.append({
                "cv_id": cv.get("_id"),
                "email": cv.get("email"),
                "name": cv.get("name", "Unknown"),
                "status": "existing"
            })
        return JSONResponse(content={"status": "success", "cvs": response, "company_name": company_name, "job_title": job_title})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving existing CVs: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving existing CVs: {str(e)}")

@app.get("/existing-jds/")
async def get_existing_jd(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Return existing JD documents summary for company & job (multi-tenant).

    Logic: because each company/job has a dedicated collection jd_<job_slug>, we simply list all documents
    from that collection. If none found, return 404.
    Response includes jd_ids list and per-doc minimal metadata.
    """
    try:
        qp_company = (request.query_params.get("company_name") or "").strip()
        qp_job = (request.query_params.get("job_title") or "").strip()
        if not qp_company or not qp_job:
            raise HTTPException(status_code=400, detail="company_name and job_title query parameters required")
        _enforce_company_access(qp_company, current_user)
        db_name_dyn, _, jd_collection_mongo = build_mongo_names(qp_company, qp_job)
        jd_inserter_dyn = JDDataInserter(
            connection_string=config["mongodb"]["connection_string"],
            db_name=db_name_dyn,
            collection_name=jd_collection_mongo
        )
        # Directly connect and list all JDs
        if not jd_inserter_dyn.connect_to_database():
            raise HTTPException(status_code=500, detail="Failed to connect to JD database")
        try:
            cursor = jd_inserter_dyn.collection.find({})
            docs = list(cursor)
        finally:
            jd_inserter_dyn.close_connection()
        if not docs:
            raise HTTPException(status_code=404, detail="No Job Description documents found for provided context")
        jd_summaries = []
        for d in docs:
            jd_id = d.get('_id')
            # Build aggregate text length similar to reranker logic
            agg_parts = []
            for fld in ["description","full_text","responsibilities"]:
                v = d.get(fld)
                if isinstance(v, str) and v.strip():
                    agg_parts.append(v.strip())
            text_length = sum(len(p) for p in agg_parts)
            jd_summaries.append({
                "jd_id": jd_id,
                "job_title": d.get("job_title"),
                "company_name": d.get("company_name"),
                "text_length": text_length,
                "fields_present_count": len([k for k,v in d.items() if v])
            })
        return JSONResponse(content={
            "status": "success",
            "company_name": qp_company,
            "job_title": qp_job,
            "jd_ids": [s["jd_id"] for s in jd_summaries],
            "documents": jd_summaries
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing existing JDs: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving existing JDs: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "API is running"}

@app.get("/companies/")
async def list_companies():
    """List existing company databases (original names) used for multi-tenancy.

    Filters out internal/system databases. Assumes company DBs were created via build_mongo_names.
    """
    try:
        client = MongoClient(config["mongodb"]["connection_string"])
        db_names = client.list_database_names()
        # System / default DBs to ignore
        ignore = {"admin", "local", "config"}
        # Also ignore the legacy static db names from config to avoid confusion
        legacy = {config["mongodb"]["cv_db_name"], config["mongodb"]["jd_db_name"]}
        
        # Filter and desanitize names
        company_dbs = [n for n in db_names if n not in ignore and n not in legacy]
        
        # Convert sanitized names back to a more readable format (Title Case, underscores to spaces)
        # This is an approximation but improves UX.
        desanitized_companies = [name.replace("_", " ").title() for name in company_dbs]
        desanitized_companies.sort()
        
        return JSONResponse(content={"status": "success", "companies": desanitized_companies})
    except Exception as e:
        logger.error(f"Error listing companies: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing companies: {str(e)}")

@app.get("/jobs/")
async def list_jobs(company_name: str):
    """List existing job identifiers (from CV or JD collections) for a given company.

    Collections pattern: cvs_<job_slug>, jd_<job_slug>
    Returns unique job slugs (reconstructed to display with spaces).
    """
    try:
        if not company_name.strip():
            raise HTTPException(status_code=400, detail="company_name is required")
        
        # Sanitize the company name to get the correct database name
        sanitized_company_name = sanitize_fragment(company_name)
        
        client = MongoClient(config["mongodb"]["connection_string"])
        db = client[sanitized_company_name]
        collection_names = db.list_collection_names()
        job_slugs = set()
        for coll in collection_names:
            if coll.startswith("cvs_"):
                job_slugs.add(coll[len("cvs_"):])
            elif coll.startswith("jd_"):
                job_slugs.add(coll[len("jd_"):])
        # Convert slug back to display form (replace underscores with space, title case)
        jobs = [slug.replace("_", " ").title() for slug in sorted(job_slugs)]
        return JSONResponse(content={"status": "success", "company_name": company_name, "jobs": jobs})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing jobs for company '{company_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Error listing jobs: {str(e)}")

# ==================== ADMIN ENDPOINTS ====================

@app.post("/admin/bulk-delete-cvs")
async def bulk_delete_cvs(
    request: Dict[str, str],
    current_user: dict = Depends(get_current_user)
):
    """Admin: Delete all CVs for a specific job at a company."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    company_name = request.get("company_name")
    job_title = request.get("job_title")
    
    if not company_name or not job_title:
        raise HTTPException(status_code=400, detail="company_name and job_title required")
    
    try:
        # Build collection and DB names
        _, cv_persist_dir = build_persist_directories(company_name, job_title)
        cv_mongo_db, cv_mongo_coll, _ = build_mongo_names(company_name, job_title)
        
        # Delete from MongoDB
        client = MongoClient(config["mongodb"]["connection_string"])
        db = client[cv_mongo_db]
        result = db[cv_mongo_coll].delete_many({})
        deleted_count = result.deleted_count
        
        # Delete ChromaDB collection
        import chromadb
        chroma_client = chromadb.PersistentClient(path=cv_persist_dir)
        cv_coll_name, _ = build_collection_names(company_name, job_title)
        try:
            chroma_client.delete_collection(cv_coll_name)
        except Exception as e:
            logger.warning(f"ChromaDB collection deletion warning: {e}")
        
        logger.info(f"Admin deleted {deleted_count} CVs for {job_title} at {company_name}")
        return {"status": "success", "deleted_count": deleted_count, "message": f"Deleted {deleted_count} CVs"}
    
    except Exception as e:
        logger.error(f"Bulk delete CVs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/bulk-delete-jds")
async def bulk_delete_jds(
    request: Dict[str, Optional[str]],
    current_user: dict = Depends(get_current_user)
):
    """Admin: Delete JDs for a company. If job_title specified, deletes that job only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    company_name = request.get("company_name")
    job_title = request.get("job_title")
    
    if not company_name:
        raise HTTPException(status_code=400, detail="company_name required")
    
    try:
        deleted_count = 0
        sanitized_company = sanitize_fragment(company_name)
        client = MongoClient(config["mongodb"]["connection_string"])
        db = client[sanitized_company]
        
        if job_title:
            # Delete specific job
            _, _, jd_mongo_coll = build_mongo_names(company_name, job_title)
            result = db[jd_mongo_coll].delete_many({})
            deleted_count = result.deleted_count
            
            # Delete JD ChromaDB
            jd_persist_dir, _ = build_persist_directories(company_name, job_title)
            import chromadb
            chroma_client = chromadb.PersistentClient(path=jd_persist_dir)
            _, jd_coll_name = build_collection_names(company_name, job_title)
            try:
                chroma_client.delete_collection(jd_coll_name)
            except Exception as e:
                logger.warning(f"JD ChromaDB deletion warning: {e}")
        else:
            # Delete all JDs for company
            collections = db.list_collection_names()
            for coll in collections:
                if coll.startswith("jd_"):
                    result = db[coll].delete_many({})
                    deleted_count += result.deleted_count
            
            # Note: ChromaDB cleanup for all jobs would require iterating job titles
            # For simplicity, we only delete MongoDB here
        
        logger.info(f"Admin deleted {deleted_count} JDs for {company_name}")
        return {"status": "success", "deleted_count": deleted_count}
    
    except Exception as e:
        logger.error(f"Bulk delete JDs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/delete-company/{company_name}")
async def delete_company(
    company_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Delete entire company database and all ChromaDB data."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        sanitized_company = sanitize_fragment(company_name)
        
        # Delete MongoDB database
        client = MongoClient(config["mongodb"]["connection_string"])
        client.drop_database(sanitized_company)
        
        # Delete ChromaDB directories
        import shutil
        base_cv_dir = config["chroma"]["cv_persist_dir"]
        base_jd_dir = config["chroma"]["jd_persist_dir"]
        
        company_cv_dir = os.path.join(base_cv_dir, sanitized_company)
        company_jd_dir = os.path.join(base_jd_dir, sanitized_company)
        
        if os.path.exists(company_cv_dir):
            shutil.rmtree(company_cv_dir)
        if os.path.exists(company_jd_dir):
            shutil.rmtree(company_jd_dir)
        
        logger.info(f"Admin deleted company: {company_name}")
        return {"status": "success", "message": f"Company '{company_name}' deleted"}
    
    except Exception as e:
        logger.error(f"Delete company error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/reindex")
async def reindex_embeddings(
    request: Dict[str, str],
    current_user: dict = Depends(get_current_user)
):
    """Admin: Rebuild embeddings for a company."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    company_name = request.get("company_name")
    reindex_type = request.get("reindex_type", "both")  # cvs, jds, or both
    
    if not company_name:
        raise HTTPException(status_code=400, detail="company_name required")
    
    try:
        sanitized_company = sanitize_fragment(company_name)
        client = MongoClient(config["mongodb"]["connection_string"])
        db = client[sanitized_company]
        collections = db.list_collection_names()
        
        reindexed = {"cvs": 0, "jds": 0}
        
        for coll_name in collections:
            if reindex_type in ["cvs", "both"] and coll_name.startswith("cvs_"):
                # Extract job from collection name
                job_slug = coll_name[4:]
                job_title = job_slug.replace("_", " ").title()
                
                # Get all CVs
                cvs = list(db[coll_name].find({}))
                if cvs:
                    # Rebuild embeddings
                    jd_persist_dir, cv_persist_dir = build_persist_directories(company_name, job_title)
                    embedder = CVEmbedder(
                        model=config["embedding"]["model"],
                        persist_directory=cv_persist_dir,
                        collection_name=f"cv_{sanitize_fragment(company_name)}_{sanitize_fragment(job_title)}"
                    )
                    
                    for cv in cvs:
                        try:
                            embedder.embed_cv(cv)
                            reindexed["cvs"] += 1
                        except Exception as e:
                            logger.warning(f"Failed to reindex CV: {e}")
            
            if reindex_type in ["jds", "both"] and coll_name.startswith("jd_"):
                job_slug = coll_name[3:]
                job_title = job_slug.replace("_", " ").title()
                
                jds = list(db[coll_name].find({}))
                if jds:
                    jd_persist_dir, _ = build_persist_directories(company_name, job_title)
                    embedder = JDEmbedder(
                        model=config["embedding"]["model"],
                        persist_directory=jd_persist_dir,
                        collection_name=f"jd_{sanitize_fragment(company_name)}_{sanitize_fragment(job_title)}"
                    )
                    
                    for jd in jds:
                        try:
                            embedder.embed_jd(jd)
                            reindexed["jds"] += 1
                        except Exception as e:
                            logger.warning(f"Failed to reindex JD: {e}")
        
        message = f"Reindexed {reindexed['cvs']} CVs and {reindexed['jds']} JDs"
        logger.info(f"Admin reindex: {message}")
        return {"status": "success", "message": message, "details": reindexed}
    
    except Exception as e:
        logger.error(f"Reindex error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/health-check")
async def health_check_admin(current_user: dict = Depends(get_current_user)):
    """Admin: Check system health."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    checks = {}
    
    # Check MongoDB connection
    try:
        client = MongoClient(config["mongodb"]["connection_string"], serverSelectionTimeoutMS=5000)
        client.server_info()
        checks["mongodb"] = {"status": "ok", "message": "Connected"}
    except Exception as e:
        checks["mongodb"] = {"status": "error", "message": str(e)}
    
    # Check ChromaDB directories
    try:
        cv_dir = config["chroma"]["cv_persist_dir"]
        jd_dir = config["chroma"]["jd_persist_dir"]
        cv_exists = os.path.exists(cv_dir)
        jd_exists = os.path.exists(jd_dir)
        
        if cv_exists and jd_exists:
            checks["chromadb"] = {"status": "ok", "message": "Directories accessible"}
        else:
            checks["chromadb"] = {"status": "warning", "message": "Some directories missing"}
    except Exception as e:
        checks["chromadb"] = {"status": "error", "message": str(e)}
    
    # Check disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free // (2**30)
        if free_gb > 10:
            checks["disk_space"] = {"status": "ok", "message": f"{free_gb}GB free"}
        else:
            checks["disk_space"] = {"status": "warning", "message": f"Only {free_gb}GB free"}
    except Exception as e:
        checks["disk_space"] = {"status": "error", "message": str(e)}
    
    overall_status = "healthy" if all(c["status"] == "ok" for c in checks.values()) else "degraded"
    
    return {"overall_status": overall_status, "checks": checks}

@app.get("/admin/export/{company_name}")
async def export_company_data(
    company_name: str,
    format: str = "json",
    current_user: dict = Depends(get_current_user)
):
    """Admin: Export company data."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        sanitized_company = sanitize_fragment(company_name)
        client = MongoClient(config["mongodb"]["connection_string"])
        db = client[sanitized_company]
        
        export_data = {"company": company_name, "collections": {}}
        
        for coll_name in db.list_collection_names():
            docs = list(db[coll_name].find({}))
            # Convert ObjectId to string for JSON serialization
            for doc in docs:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])
            export_data["collections"][coll_name] = docs
        
        if format == "json":
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
                json.dump(export_data, f, indent=2)
                temp_path = f.name
            return FileResponse(temp_path, filename=f"{company_name}_export.json", media_type="application/json")
        
        elif format == "csv":
            # Simple CSV export - flatten collections
            import csv
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Collection", "Document ID", "Data"])
                for coll_name, docs in export_data["collections"].items():
                    for doc in docs:
                        writer.writerow([coll_name, doc.get("_id", ""), json.dumps(doc)])
                temp_path = f.name
            return FileResponse(temp_path, filename=f"{company_name}_export.csv", media_type="text/csv")
        
        else:
            raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/logs")
async def get_logs(
    action_type: Optional[str] = None,
    company: Optional[str] = None,
    hours: int = 24,
    current_user: dict = Depends(get_current_user)
):
    """Admin: Get system activity logs."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # This is a placeholder - you'd implement actual logging to database
    # For now, return mock data
    from datetime import datetime, timedelta
    
    logs = [
        {
            "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
            "action_type": "upload_cv",
            "message": "CV uploaded for Software Engineer at Google",
            "user": "user@example.com",
            "company": "Google"
        },
        {
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
            "action_type": "search",
            "message": "Search performed for Data Analyst",
            "user": "recruiter@company.com",
            "company": "Microsoft"
        }
    ]
    
    # Filter logs
    if action_type:
        logs = [l for l in logs if l["action_type"] == action_type]
    if company:
        logs = [l for l in logs if l.get("company") == company]
    
    stats = {
        "uploads": sum(1 for l in logs if l["action_type"] in ["upload_cv", "upload_jd"]),
        "searches": sum(1 for l in logs if l["action_type"] == "search"),
        "active_users": len(set(l.get("user") for l in logs if l.get("user"))),
        "errors": sum(1 for l in logs if l["action_type"] == "error")
    }
    
    return {"logs": logs, "stats": stats}

@app.get("/admin/logs/export")
async def export_logs(current_user: dict = Depends(get_current_user)):
    """Admin: Export logs as CSV."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    import csv
    import tempfile
    from datetime import datetime
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Action", "Message", "User", "Company"])
        writer.writerow([datetime.now().isoformat(), "upload_cv", "Sample log entry", "user@test.com", "Test Co"])
        temp_path = f.name
    
    return FileResponse(temp_path, filename="system_logs.csv", media_type="text/csv")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    cvjd_vector_search.close()