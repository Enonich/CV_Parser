import os
import json
import yaml
import hashlib
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Dict, Optional
from cv_extractor import CVProcessor
from jd_extractor import JDExtractor
from mongodb import CVDataInserter
from mongodb_jd import JDDataInserter
from cv_chroma_embedder import CVEmbedder
from jd_embedder import JDEmbedder
from fetch_top_k import CVJDVectorSearch
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Initialize FastAPI app
app = FastAPI(title="CV Parsing Automation API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# OAuth2 for optional authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Ensure directories exist
os.makedirs("./static/cvs", exist_ok=True)
os.makedirs("./static/jds", exist_ok=True)
os.makedirs("./static/extracted_files", exist_ok=True)

# Initialize modules with config
cv_processor = CVProcessor()
jd_extractor = JDExtractor()
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

class SearchRequest(BaseModel):
    top_k_cvs: Optional[int] = config["search"]["top_k_cvs"]
    show_details: Optional[bool] = False

@app.post("/upload-cv/")
async def upload_cv(file: UploadFile = File(...), token: Optional[str] = Depends(oauth2_scheme)):
    """Upload and process a CV file."""
    try:
        # Validate file type
        if not file.filename.lower().endswith((".pdf", ".docx", ".png", ".jpg", ".jpeg")):
            raise HTTPException(status_code=400, detail="Only PDF, DOCX, PNG, JPG, or JPEG files allowed")

        # Save file temporarily
        cv_path = f"./static/cvs/{file.filename}"
        with open(cv_path, "wb") as f:
            f.write(await file.read())

        # Process CV
        json_path = cv_processor.extract_and_save_cv(cv_path, "./static/extracted_files")
        if not json_path:
            raise HTTPException(status_code=500, detail="Failed to extract CV data")

        # Load CV data to check if it already exists
        with open(json_path, 'r', encoding='utf-8') as f:
            cv_data = json.load(f)
        
        structured_data = cv_data.get("CV_data", {}).get("structured_data", {})
        email = structured_data.get("email", "").strip()
        phone = structured_data.get("phone", "").strip()
        
        # Check if CV already exists
        existing_cv = cv_data_inserter.check_cv_exists(email=email, phone=phone)
        
        if existing_cv:
            # CV already exists, return success without re-inserting
            logger.info(f"CV already exists in database: {email or phone}")
            return JSONResponse(content={
                "status": "success", 
                "cv_json_path": json_path,
                "message": "CV already exists in database",
                "existing": True
            })
        else:
            # Insert into MongoDB (new CV)
            cv_insert_success = cv_data_inserter.process_cv_file(json_path)
            if not cv_insert_success:
                # Check if it failed due to duplicate (this is expected)
                logger.warning("CV insertion failed - likely due to duplicate")
                return JSONResponse(content={
                    "status": "success", 
                    "cv_json_path": json_path,
                    "message": "CV already exists in database",
                    "existing": True
                })

            # Generate embeddings
            if not cv_embedder.embed_cv(json_path):
                raise HTTPException(status_code=500, detail="Failed to embed CV")

        # Clean up temporary CV file
        os.remove(cv_path)

        return JSONResponse(content={"status": "success", "cv_json_path": json_path})

    except Exception as e:
        logger.error(f"Error processing CV: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing CV: {str(e)}")

@app.post("/upload-jd/")
async def upload_jd(file: UploadFile = File(...), token: Optional[str] = Depends(oauth2_scheme)):
    """Upload and process a job description file."""
    try:
        # Validate file type
        if not file.filename.lower().endswith((".txt", ".pdf", ".docx")):
            raise HTTPException(status_code=400, detail="Only TXT, PDF, or DOCX files allowed")

        # Save file temporarily
        jd_path = f"./static/jds/{file.filename}"
        with open(jd_path, "wb") as f:
            f.write(await file.read())

        # Process JD
        json_path = f"./static/extracted_files/{os.path.splitext(file.filename)[0]}.json"
        jd_data = jd_extractor.extract(jd_path)
        if not jd_data:
            raise HTTPException(status_code=500, detail="Failed to extract JD data")

        # Save extracted JD to JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(jd_data, f, indent=2)

        # Generate JD ID from filename for checking existence
        jd_filename = os.path.splitext(file.filename)[0]
        jd_id = hashlib.sha256(jd_filename.encode('utf-8')).hexdigest()
        
        # Check if JD already exists
        existing_jd = jd_data_inserter.check_jd_exists(jd_id=jd_id)
        
        if existing_jd:
            # JD already exists, return success without re-inserting
            logger.info(f"JD already exists in database: {jd_filename}")
            return JSONResponse(content={
                "status": "success", 
                "jd_json_path": json_path,
                "message": "Job Description already exists in database",
                "existing": True
            })
        else:
            # Insert into MongoDB (new JD)
            jd_insert_success = jd_data_inserter.process_jd_file(json_path)
            if not jd_insert_success:
                # Check if it failed due to duplicate (this is expected)
                logger.warning("JD insertion failed - likely due to duplicate")
                return JSONResponse(content={
                    "status": "success", 
                    "jd_json_path": json_path,
                    "message": "Job Description already exists in database",
                    "existing": True
                })

            # Generate embeddings
            if not jd_embedder.embed_job_description(jd_path):
                raise HTTPException(status_code=500, detail="Failed to embed JD")

        # Clean up temporary JD file
        os.remove(jd_path)

        return JSONResponse(content={"status": "success", "jd_json_path": json_path})

    except Exception as e:
        logger.error(f"Error processing JD: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing JD: {str(e)}")

@app.post("/search-cvs/", response_model=List[Dict])
async def search_cvs(request: SearchRequest, token: Optional[str] = Depends(oauth2_scheme)):
    """Search and rank CVs against the stored job description."""
    try:
        results = cvjd_vector_search.search_and_score_cvs(top_k_cvs=request.top_k_cvs)
        if not results:
            raise HTTPException(status_code=404, detail="No CVs found or no JD available")

        # Format results for response with original identifier
        response = []
        for result in results:
            cv_id = result["cv_id"]
            original_identifier = cvjd_vector_search.get_email_from_cv_id(cv_id)
            
            response.append({
                "cv_id": cv_id,
                "original_identifier": original_identifier,
                "total_score": result["total_score"],
                "section_scores": result["section_scores"],
                "section_details": result["section_details"] if request.show_details else {}
            })

        return JSONResponse(content={"status": "success", "results": response})

    except Exception as e:
        logger.error(f"Error searching CVs: {e}")
        raise HTTPException(status_code=500, detail=f"Error searching CVs: {str(e)}")

@app.get("/")
async def root():
    """Serve the main web application."""
    return FileResponse('static/index.html')

@app.get("/existing-cvs/")
async def get_existing_cvs(token: Optional[str] = Depends(oauth2_scheme)):
    """Get list of existing CVs from MongoDB."""
    try:
        # Get all CVs from MongoDB
        existing_cvs = cv_data_inserter.get_all_cvs()
        
        # Format the response
        response = []
        for cv in existing_cvs:
            response.append({
                "cv_id": cv.get("cv_id"),
                "email": cv.get("email"),
                "name": cv.get("name", "Unknown"),
                "upload_date": cv.get("upload_date"),
                "status": "existing"
            })
        
        return JSONResponse(content={"status": "success", "cvs": response})
        
    except Exception as e:
        logger.error(f"Error retrieving existing CVs: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving existing CVs: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "API is running"}

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    cvjd_vector_search.close()