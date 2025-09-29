from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import json

# Load your structured CV data (from JSON)
with open("./extracted_files/CV_Image.json", "r") as f:
    cv_data = json.load(f)["CV_data"]["structured_data"]

# Define sections to embed (adapt to your keys)
sections = ["email", "summary", "work_experience", "education", "skills", "soft_skills", "certifications", "projects", "languages", "hobbies", "other", "years_of_experience"]

# Initialize Ollama embeddings (mxbai-embed-large)
embeddings = OllamaEmbeddings(model="mxbai-embed-large")

# Prepare documents: chunk each section into texts with metadata
documents = []
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)  # Adjust for section size

for section_key in sections:
    if section_key in cv_data and cv_data[section_key]:
        # Convert section to string (handle lists/dicts as needed)
        section_text = json.dumps(cv_data[section_key])
        # Split into chunks if large
        chunks = splitter.split_text(section_text)
        for i, chunk in enumerate(chunks):
            doc = Document(
                page_content=chunk,
                metadata={
                    "section": section_key,
                    "chunk_id": i,
                    "cv_id": "your_cv_identifier"  # e.g., from filename
                }
            )
            documents.append(doc)

# Store in Chroma (persists to disk at ./chroma_db)
vectorstore = Chroma.from_documents(
    documents=documents,
    embedding=embeddings,
    persist_directory="./chroma_db",  # Saves embeddings locally
    collection_name="cv_sections"
)
vectorstore.persist()  # Save to disk

# Example Query: Retrieve similar sections
query = "data science experience"
results = vectorstore.similarity_search(query, k=3, filter={"section": "work_experience"})
for doc in results:
    print(f"Section: {doc.metadata['section']}\nContent: {doc.page_content[:200]}...\n")