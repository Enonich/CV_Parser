"""
Test script for HR Explainability Agent integration

This script verifies that all agent components are properly integrated:
1. Backend imports work
2. Agent classes can be instantiated
3. Endpoints are registered
4. Configuration is correct

Run this before starting the server to catch integration issues.

Usage:
    python test_agent_integration.py
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def test_imports():
    """Test that all required imports work."""
    print("Testing imports...")
    
    try:
        from backend.core.agent import CVScoringContext, CVExplainabilityAgent
        print("✅ Agent classes imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import agent classes: {e}")
        return False
    
    try:
        from langchain_ollama import OllamaEmbeddings, ChatOllama
        from langchain_chroma import Chroma
        from langchain.chains import RetrievalQA
        print("✅ LangChain dependencies imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import LangChain dependencies: {e}")
        print("   Run: pip install langchain langchain-ollama langchain-chroma")
        return False
    
    try:
        import yaml
        from pymongo import MongoClient
        print("✅ Core dependencies imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import core dependencies: {e}")
        return False
    
    return True

def test_config():
    """Test that config.yaml has required settings."""
    print("\nTesting configuration...")
    
    try:
        import yaml
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Check LLM config
        if 'llm_model' not in config:
            print("⚠️  Warning: 'llm_model' not in config.yaml")
            print("   Add: llm_model: 'llama3.2:latest'")
        else:
            print(f"✅ LLM model configured: {config['llm_model']}")
        
        if 'ollama_url' not in config:
            print("⚠️  Warning: 'ollama_url' not in config.yaml")
            print("   Add: ollama_url: 'http://localhost:11434'")
        else:
            print(f"✅ Ollama URL configured: {config['ollama_url']}")
        
        # Check embedding config
        if 'embedding' in config and 'model' in config['embedding']:
            print(f"✅ Embedding model configured: {config['embedding']['model']}")
        else:
            print("❌ Embedding model not configured")
            return False
        
        # Check ChromaDB config
        if 'chroma' in config:
            print(f"✅ ChromaDB configured")
        else:
            print("❌ ChromaDB config missing")
            return False
        
        return True
        
    except FileNotFoundError:
        print("❌ config.yaml not found")
        return False
    except Exception as e:
        print(f"❌ Error reading config: {e}")
        return False

def test_ollama():
    """Test that Ollama is running and models are available."""
    print("\nTesting Ollama connection...")
    
    try:
        import requests
        
        # Check if Ollama is running
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama is running")
            
            # Check for required models
            models = response.json().get('models', [])
            model_names = [m.get('name', '') for m in models]
            
            # Check LLM model
            llm_found = any('llama' in name.lower() for name in model_names)
            if llm_found:
                print("✅ LLM model found (llama variant)")
            else:
                print("⚠️  Warning: No llama model found")
                print("   Run: ollama pull llama3.2:latest")
            
            # Check embedding model
            embed_found = any('mxbai' in name.lower() or 'embed' in name.lower() for name in model_names)
            if embed_found:
                print("✅ Embedding model found")
            else:
                print("⚠️  Warning: Embedding model not found")
                print("   Run: ollama pull mxbai-embed-large")
            
            return True
        else:
            print("❌ Ollama responded with error")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama (is it running?)")
        print("   Start Ollama or check if port 11434 is correct")
        return False
    except Exception as e:
        print(f"❌ Error connecting to Ollama: {e}")
        return False

def test_mongodb():
    """Test that MongoDB is accessible."""
    print("\nTesting MongoDB connection...")
    
    try:
        from pymongo import MongoClient
        import yaml
        
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        connection_string = config.get('mongodb', {}).get('connection_string', 'mongodb://localhost:27017/')
        
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.server_info()  # Will raise exception if cannot connect
        
        print("✅ MongoDB is accessible")
        
        # Check if databases exist
        db_names = client.list_database_names()
        cv_db = config.get('mongodb', {}).get('cv_db_name', 'CV')
        jd_db = config.get('mongodb', {}).get('jd_db_name', 'JobDescriptions')
        
        if cv_db in db_names:
            print(f"✅ CV database exists: {cv_db}")
        else:
            print(f"⚠️  CV database not found: {cv_db} (will be created on first use)")
        
        if jd_db in db_names:
            print(f"✅ JD database exists: {jd_db}")
        else:
            print(f"⚠️  JD database not found: {jd_db} (will be created on first use)")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Cannot connect to MongoDB: {e}")
        print("   Make sure MongoDB is running on port 27017")
        return False

def test_endpoints():
    """Test that agent endpoints are registered (by checking workflow.py)."""
    print("\nTesting endpoint registration...")
    
    try:
        with open('backend/api/workflow.py', 'r') as f:
            content = f.read()
        
        endpoints = [
            '@app.post("/agent/session")',
            '@app.post("/agent/ask")',
            '@app.delete("/agent/session/{session_id}")',
            'from backend.core.agent import'
        ]
        
        all_found = True
        for endpoint in endpoints:
            if endpoint in content:
                print(f"✅ Found: {endpoint}")
            else:
                print(f"❌ Missing: {endpoint}")
                all_found = False
        
        return all_found
        
    except FileNotFoundError:
        print("❌ workflow.py not found")
        return False

def test_frontend():
    """Test that frontend files have agent integration."""
    print("\nTesting frontend integration...")
    
    try:
        # Check index.html
        with open('static/index.html', 'r') as f:
            html_content = f.read()
        
        if 'agent-modal' in html_content:
            print("✅ Agent modal found in index.html")
        else:
            print("❌ Agent modal missing in index.html")
            return False
        
        # Check app.js
        with open('static/app.js', 'r') as f:
            js_content = f.read()
        
        if 'openAgentChat' in js_content and 'agent/session' in js_content:
            print("✅ Agent functions found in app.js")
        else:
            print("❌ Agent functions missing in app.js")
            return False
        
        # Check styles.css
        with open('static/styles.css', 'r') as f:
            css_content = f.read()
        
        if 'agent-chat-messages' in css_content or 'Agent Chat' in css_content:
            print("✅ Agent styles found in styles.css")
        else:
            print("⚠️  Agent styles might be missing in styles.css")
        
        return True
        
    except FileNotFoundError as e:
        print(f"❌ Frontend file not found: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("HR EXPLAINABILITY AGENT - INTEGRATION TEST")
    print("=" * 60)
    
    results = {
        "Imports": test_imports(),
        "Configuration": test_config(),
        "Ollama": test_ollama(),
        "MongoDB": test_mongodb(),
        "Endpoints": test_endpoints(),
        "Frontend": test_frontend()
    }
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20s}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED - Ready to start the application!")
        print("\nStart the server with:")
        print("  python main.py")
        print("\nThen open: http://localhost:8000/static/login.html")
    else:
        print("⚠️  SOME TESTS FAILED - Please fix issues above")
        print("\nCommon fixes:")
        print("  • Install dependencies: pip install -r requirements.txt")
        print("  • Start Ollama: ollama serve")
        print("  • Pull models: ollama pull llama3.2:latest")
        print("  • Start MongoDB: Check MongoDB service")
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
