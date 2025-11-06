"""
Main entry point for CV Parser application
Run with: python main.py
"""
import sys
import os
import uvicorn

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

if __name__ == "__main__":
    print("Starting CV Parser application...")
    print("API will be available at: http://localhost:8000")
    print("Web interface at: http://localhost:8000/static/login.html")
    print("Press Ctrl+C to stop the server\n")
    
    # Run the FastAPI application
    uvicorn.run(
        "backend.api.workflow:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
