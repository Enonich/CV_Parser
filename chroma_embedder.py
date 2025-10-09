from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import json
import hashlib
import os
import numpy as np
from datetime import datetime, UTC
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CVEmbedder:
    """A class to handle embedding of CV data into a Chroma vector store. Aligned with CVVectorSearch."""

    def __init__(self, model="mxbai-embed-large", persist_directory="./chroma_db", collection_name="cv_sections",
                 mongo_uri=None):  # Optional for future hybrid
        """Initialize with embedding model and Chroma settings. Added cosine and health check."""
        self.embeddings = OllamaEmbeddings(model=model)
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        # Updated: Cosine distance for consistency with Search
        self.vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=self.embeddings,
            collection_name=collection_name,
            collection_metadata={"hnsw:space": "cosine"}
        )
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        self.sections = [
            "email", "summary", "work_experience", "education", "skills",
            "soft_skills", "certifications", "projects", "languages",
            "hobbies", "other", "years_of_experience"
        ]
        self.mongo_uri = mongo_uri  # For potential ID sync; unused here
        
        # Added: Ollama health check on init
        if not self.check_ollama_health():
            raise ValueError("Ollama embeddings unavailable - check server status")

    def check_ollama_health(self):
        """Health check for Ollama embeddings (matches CVVectorSearch)."""
        try:
            self.embeddings.embed_query("health check")
            logger.info("Ollama health check passed")
            return True
        except Exception as e:
            logger.error(f"Ollama unhealthy: {e}")
            return False

    def load_cv_json(self, cv_json_path):
        """Load structured CV data from JSON."""
        try:
            with open(cv_json_path, "r", encoding="utf-8") as f:
                return json.load(f)["CV_data"]["structured_data"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error loading CV JSON {cv_json_path}: {e}")
            return None

    def generate_cv_id(self, cv_struct, cv_json_path):
        """Updated: Align with Mongo - prefer email, fallback to phone, always hash."""
        email = cv_struct.get("email", "").strip()
        phone = cv_struct.get("phone", "").strip()
        
        if email:
            identifier = email.lower()
            logger.info(f"Generated CV ID from email")
        elif phone:
            identifier = phone  # No lower() for phone
            logger.info(f"Generated CV ID from phone")
        else:
            raise ValueError("Either email or phone required for CV ID")
        
        cv_id = hashlib.sha256(identifier.encode('utf-8')).hexdigest()
        return cv_id

    def check_cv_exists(self, cv_id):
        """Check if a CV ID already exists in the Chroma vector store."""
        try:
            result = self.vectorstore.get(where={"cv_id": cv_id})
            documents = result.get("documents", [])
            return len(documents) > 0
        except Exception as e:
            logger.error(f"Error checking CV existence for cv_id {cv_id}: {e}")
            return False

    def clear_existing_documents(self, cv_id):
        """Remove existing documents for a given CV ID in Chroma."""
        try:
            self.vectorstore.delete(where={"cv_id": cv_id})
            logger.info(f"Cleared existing documents for cv_id: {cv_id}")
        except Exception as e:
            logger.warning(f"Error clearing existing documents: {e}")

    def format_section(self, section_data):
        """Added: Flatten nested section to clean text (avoids JSON noise for better embedding)."""
        if isinstance(section_data, dict):
            return " | ".join([f"{k}: {v}" for k, v in section_data.items()])
        elif isinstance(section_data, list):
            return " | ".join(str(item) for item in section_data)
        return str(section_data)

    def prepare_documents(self, cv_struct, cv_id):
        """Convert CV sections into Document objects with chunking. Updated: Clean text formatting."""
        documents = []
        for section_key in self.sections:
            if section_key in cv_struct and cv_struct[section_key]:
                try:
                    # Updated: Use clean formatting instead of json.dumps
                    section_text = self.format_section(cv_struct[section_key])
                    if not section_text.strip():
                        logger.warning(f"Empty section text for {section_key}, skipping")
                        continue
                except Exception as e:
                    logger.warning(f"Error formatting section {section_key}: {e}")
                    continue

                chunks = self.splitter.split_text(section_text)
                for i, chunk in enumerate(chunks):
                    if not chunk.strip():
                        continue
                    doc = Document(
                        page_content=chunk,
                        metadata={
                            "section": section_key,
                            "chunk_id": i,
                            "cv_id": cv_id,
                            "embed_date": datetime.now(UTC).isoformat()  # Added: Timestamp
                        }
                    )
                    documents.append(doc)
        return documents

    def embed_documents_batch(self, documents):
        """Generate embeddings in batch. Updated: Return embeddings array for direct storage."""
        try:
            texts = [doc.page_content for doc in documents]
            embeddings_array = self.embeddings.embed_documents(texts)
            valid_embeddings = []
            valid_docs = []
            for doc, emb in zip(documents, embeddings_array):
                try:
                    emb_np = np.array(emb, dtype=np.float64)
                    if emb_np.ndim != 1:
                        logger.warning(f"Invalid embedding shape for {doc.metadata['section']} chunk {doc.metadata['chunk_id']}, skipping")
                        continue
                    valid_embeddings.append(emb_np.tolist())  # To list for LangChain
                    valid_docs.append(doc)
                except Exception as e:
                    logger.warning(f"Error processing embedding for chunk {doc.metadata['chunk_id']}: {e}")
                    continue
            return valid_docs, valid_embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings batch: {e}")
            return [], []

    def store_documents(self, documents, embeddings):
        """Fixed: Use add_texts with pre-computed embeddings for batch storage and dedup."""
        if not documents:
            logger.warning("No documents to store")
            return False

        inserted_count = 0
        skipped_count = 0
        non_dupe_texts = []
        non_dupe_embeddings = []
        non_dupe_metadatas = []
        non_dupe_ids = []

        for doc, emb in zip(documents, embeddings):
            doc_id = f"{doc.metadata['cv_id']}_{doc.metadata['section']}_{doc.metadata['chunk_id']}"
            # Fixed: Use get(ids=...) for exact ID check
            existing = self.vectorstore.get(ids=[doc_id]).get("documents", [])
            if existing:
                skipped_count += 1
                continue

            non_dupe_texts.append(doc.page_content)
            non_dupe_embeddings.append(emb)
            non_dupe_metadatas.append(doc.metadata)
            non_dupe_ids.append(doc_id)
            inserted_count += 1  # Pre-count for logging

        if non_dupe_texts:
            try:
                # Fixed: Use add_texts with embeddings (LangChain API)
                self.vectorstore.add_texts(
                    texts=non_dupe_texts,
                    embeddings=non_dupe_embeddings,
                    metadatas=non_dupe_metadatas,
                    ids=non_dupe_ids
                )
                logger.info(f"Batch inserted {len(non_dupe_texts)} embeddings")
            except Exception as e:
                logger.error(f"Batch insert failed: {e}")
                return False

        logger.info(f"Chroma insert complete. Inserted: {inserted_count}, Skipped (duplicates): {skipped_count}")
        return True

    def embed_cv(self, cv_json_path):
        """Full CV embedding pipeline. Updated: Use prepare + batch embed + batch store."""
        logger.info(f"Processing CV JSON: {cv_json_path}")
        cv_struct = self.load_cv_json(cv_json_path)
        if not cv_struct:
            return False

        cv_id = self.generate_cv_id(cv_struct, cv_json_path)
        logger.info(f"Processing CV with cv_id: {cv_id}")

        # Check if CV already exists
        if self.check_cv_exists(cv_id):
            logger.info(f"CV with cv_id {cv_id} already exists, skipping embedding")
            return True

        logger.info(f"CV with cv_id {cv_id} does not exist, proceeding with embedding")
        self.clear_existing_documents(cv_id)
        documents = self.prepare_documents(cv_struct, cv_id)

        valid_docs, valid_embeddings = self.embed_documents_batch(documents)
        if not valid_docs:
            logger.error("No valid embeddings generated")
            return False

        return self.store_documents(valid_docs, valid_embeddings)


# Example usage
if __name__ == "__main__":
    embedder = CVEmbedder()
    
    # List of CV JSON files to embed
    cv_files = [
        "./extracted_files/CV_Image.json",
        "./extracted_files/Power_BI_Developer.json",
        "./extracted_files/Data_Analyst3_CV.json",
        # Add more files as needed
    ]
    
    # Process each CV
    results = {}
    for cv_file in cv_files:
        print(f"\n📄 Processing: {cv_file}")
        success = embedder.embed_cv(cv_file)
        results[cv_file] = success
        
        if success:
            print(f"✅ {cv_file} - Successfully processed or already exists")
        else:
            print(f"❌ {cv_file} - Embedding failed")
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    successful = sum(1 for v in results.values() if v)
    print(f"Total: {len(cv_files)} | Success: {successful} | Failed: {len(cv_files) - successful}")



# ------------------------Processing Multiple CVs In One Directory------------------------
if __name__ == "__main__":
    import glob
    
    embedder = CVEmbedder()
    
    # Get all JSON files from directory
    cv_directory = "./extracted_files"
    cv_files = glob.glob(f"{cv_directory}/*.json")
    
    print(f"Found {len(cv_files)} JSON files to process\n")
    
    results = {}
    for cv_file in cv_files:
        print(f"📄 Processing: {cv_file}")
        try:
            success = embedder.embed_cv(cv_file)
            results[cv_file] = success
            status = "✅ Success" if success else "❌ Failed"
            print(f"{status}\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")
            results[cv_file] = False
    
    # Summary
    print("="*50)
    successful = sum(1 for v in results.values() if v)
    failed = len(cv_files) - successful
    print(f"Processed: {len(cv_files)} | Success: {successful} | Failed: {failed}")