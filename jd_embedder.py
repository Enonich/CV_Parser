import json
import hashlib
import logging
import numpy as np
from datetime import datetime, UTC
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from jd_extractor import JDExtractor  # ✅ Import your JDExtractor class

logger = logging.getLogger(__name__)

class JDEmbedder:
    """Embeds structured Job Description data extracted via JDExtractor for section-wise comparison with CVs."""

    def __init__(self, model="mxbai-embed-large", persist_directory="./chroma_db", collection_name="job_descriptions"):
        self.embeddings = OllamaEmbeddings(model=model)
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=self.embeddings,
            collection_name=collection_name,
            collection_metadata={"hnsw:space": "cosine"}
        )
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

        # JD sections that we want to embed
        self.sections = [
            "job_title", "required_skills", "preferred_skills",
            "required_qualifications", "education_requirements",
            "experience_requirements", "technical_skills", "soft_skills",
            "certifications", "responsibilities"
        ]

        # Initialize JD extractor
        self.extractor = JDExtractor()

    # ---------- Helper Methods ----------

    def generate_jd_id(self, jd_struct, jd_path):
        """Generate a unique ID for each JD (based on title or file path)."""
        title = jd_struct.get("job_title", "")
        identifier = title if title else jd_path
        return hashlib.sha256(identifier.encode("utf-8")).hexdigest()

    def format_section(self, section_data):
        """Flatten nested data for embedding."""
        if isinstance(section_data, dict):
            return " | ".join([f"{k}: {v}" for k, v in section_data.items()])
        elif isinstance(section_data, list):
            return " | ".join(str(item) for item in section_data)
        return str(section_data)

    def prepare_documents(self, jd_struct, jd_id):
        """Convert JD sections into Document objects."""
        documents = []
        for section_key in self.sections:
            if section_key in jd_struct and jd_struct[section_key]:
                section_text = self.format_section(jd_struct[section_key])
                if not section_text.strip():
                    continue
                chunks = self.splitter.split_text(section_text)
                for i, chunk in enumerate(chunks):
                    documents.append(Document(
                        page_content=chunk,
                        metadata={
                            "section": section_key,
                            "chunk_id": i,
                            "jd_id": jd_id,
                            "embed_date": datetime.now(UTC).isoformat()
                        }
                    ))
        return documents

    # ---------- Core Embedding Logic ----------

    def embed_job_description(self, jd_file_path):
        """
        Extracts and embeds a job description file using JDExtractor.
        Automatically handles extraction, structuring, and embedding.
        """
        logger.info(f"Extracting job description from: {jd_file_path}")

        # Step 1: Extract structured JD
        jd_struct = self.extractor.extract(jd_file_path)
        if not jd_struct:
            logger.error("JD extraction failed — no structured data returned.")
            return False

        # Step 2: Generate unique JD ID
        jd_struct = jd_struct["structured_data"]
        
        jd_id = self.generate_jd_id(jd_struct, jd_file_path)
        logger.info(f"Generated JD ID: {jd_id}")

        # Step 3: Prepare documents for embedding
        documents = self.prepare_documents(jd_struct, jd_id)
        if not documents:
            logger.warning("No valid JD sections found for embedding.")
            return False

        # Step 4: Embed and store
        texts = [doc.page_content for doc in documents]
        embeddings = self.embeddings.embed_documents(texts)

        try:
            self.vectorstore.add_texts(
                texts=texts,
                embeddings=embeddings,
                metadatas=[doc.metadata for doc in documents],
                ids=[f"{jd_id}_{d.metadata['section']}_{d.metadata['chunk_id']}" for d in documents]
            )
            logger.info(f"✅ JD '{jd_id}' successfully embedded and stored.")
            return True
        except Exception as e:
            logger.error(f"Failed to store JD embeddings: {e}")
            return False


# ---------- Example Usage ----------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    embedder = JDEmbedder()
    success = embedder.embed_job_description("./job_description.txt")

    if success:
        print("✅ Job description extracted, embedded, and stored in Chroma.")
    else:
        print("❌ JD embedding failed.")
