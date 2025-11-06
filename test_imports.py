"""
Test script to verify all backend imports work correctly
Run this before starting the server to check for import errors
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing backend imports...")
print("-" * 50)

try:
    print("✓ Importing backend.core.auth...")
    from backend.core.auth import auth_router, get_current_user
    
    print("✓ Importing backend.core.identifiers...")
    from backend.core.identifiers import sanitize_fragment, build_collection_names
    
    print("✓ Importing backend.extractors.cv_extractor...")
    from backend.extractors.cv_extractor import CVProcessor
    
    print("✓ Importing backend.extractors.jd_extractor...")
    from backend.extractors.jd_extractor import JDExtractor
    
    print("✓ Importing backend.database.mongodb...")
    from backend.database.mongodb import CVDataInserter
    
    print("✓ Importing backend.database.mongodb_jd...")
    from backend.database.mongodb_jd import JDDataInserter
    
    print("✓ Importing backend.embedders.cv_chroma_embedder...")
    from backend.embedders.cv_chroma_embedder import CVEmbedder
    
    print("✓ Importing backend.embedders.jd_embedder...")
    from backend.embedders.jd_embedder import JDEmbedder
    
    print("✓ Importing backend.core.fetch_top_k...")
    from backend.core.fetch_top_k import CVJDVectorSearch
    
    print("✓ Importing backend.core.reranker...")
    from backend.core.reranker import CVJDReranker
    
    print("-" * 50)
    print("✅ All imports successful!")
    print("\nYou can now run: python main.py")
    
except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    print("\nPlease fix the import error above before running the server.")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Unexpected Error: {e}")
    sys.exit(1)
