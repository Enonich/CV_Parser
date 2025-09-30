from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import json
import hashlib
import os

# --- Load structured CV JSON ---
cv_json_path = "./extracted_files/CV_Image.json"
with open(cv_json_path, "r", encoding="utf-8") as f:
    cv_struct = json.load(f)["CV_data"]["structured_data"]

# --- Define sections to embed ---
sections = [
    "email", "summary", "work_experience", "education", "skills",
    "soft_skills", "certifications", "projects", "languages",
    "hobbies", "other", "years_of_experience"
]

# --- Initialize embeddings ---
embeddings = OllamaEmbeddings(model="mxbai-embed-large")

# --- Generate cv_id from email (hashed for privacy) ---
email = cv_struct.get("email", "").lower().strip()
if not email:
    # fallback to filename if email missing
    cv_id = os.path.splitext(os.path.basename(cv_json_path))[0]
else:
    cv_id = hashlib.md5(email.encode()).hexdigest()

print(f"Embedding CV with cv_id: {cv_id}")

# --- Prepare documents ---
documents = []
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

for section_key in sections:
    if section_key in cv_struct and cv_struct[section_key]:
        # Convert section to string
        section_text = json.dumps(cv_struct[section_key])
        # Split into chunks if necessary
        chunks = splitter.split_text(section_text)
        for i, chunk in enumerate(chunks):
            doc = Document(
                page_content=chunk,
                metadata={
                    "section": section_key,
                    "chunk_id": i,
                    "cv_id": cv_id  # <-- use hashed email here
                }
            )
            documents.append(doc)

# --- Store in Chroma ---
vectorstore = Chroma.from_documents(
    documents=documents,
    embedding=embeddings,
    persist_directory="./chroma_db",
    collection_name="cv_sections"
)
vectorstore.persist()

# # --- Example retrieval ---
# query = "data science experience"
# results = vectorstore.similarity_search(query, k=3, filter={"section": "work_experience"})
# for doc in results:
#     print(f"Section: {doc.metadata['section']}\nContent: {doc.page_content[:200]}...\n")
