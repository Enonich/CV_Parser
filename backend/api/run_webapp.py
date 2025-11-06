#!/usr/bin/env python3
"""
Startup script for the CV Parser & Scoring Web Application
"""
import uvicorn
import os
import sys

def main():
    """Run the FastAPI web application."""
    
    # Get root directory (two levels up from this file)
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    
    # Check if required directories exist
    required_dirs = [
        os.path.join(root_dir, "static"),
        os.path.join(root_dir, "static/cvs"),
        os.path.join(root_dir, "static/jds"),
        os.path.join(root_dir, "static/extracted_files")
    ]
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            print(f"Created directory: {dir_path}")
    
    # Check if config file exists
    config_path = os.path.join(root_dir, "config.yaml")
    if not os.path.exists(config_path):
        print("Error: config.yaml not found. Please ensure the configuration file exists.")
        sys.exit(1)
    
    print("Starting CV Parser & Scoring Web Application...")
    print("Access the application at: http://localhost:8000")
    print("API documentation at: http://localhost:8000/docs")
    print("Press Ctrl+C to stop the server")
    
    # Run the FastAPI application
    uvicorn.run(
        "backend.api.workflow:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
