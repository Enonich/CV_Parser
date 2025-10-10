#!/usr/bin/env python3
"""
Startup script for the CV Parser & Scoring Web Application
"""
import uvicorn
import os
import sys

def main():
    """Run the FastAPI web application."""
    
    # Check if required directories exist
    required_dirs = ["./static", "./static/cvs", "./static/jds", "./static/extracted_files"]
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            print(f"Created directory: {dir_path}")
    
    # Check if config file exists
    if not os.path.exists("config.yaml"):
        print("Error: config.yaml not found. Please ensure the configuration file exists.")
        sys.exit(1)
    
    print("Starting CV Parser & Scoring Web Application...")
    print("Access the application at: http://localhost:8000")
    print("API documentation at: http://localhost:8000/docs")
    print("Press Ctrl+C to stop the server")
    
    # Run the FastAPI application
    uvicorn.run(
        "workflow:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
