#!/usr/bin/env python3
"""
Azure App Service startup script for EvidentFit API
This file is required by Azure App Service for Python apps
"""
import os
import sys
import subprocess

# Azure App Service looks for this file
if __name__ == "__main__":
    # Set up the environment
    os.environ.setdefault("HOST", "0.0.0.0")
    os.environ.setdefault("PORT", "8000")
    
    # Start the application
    subprocess.run([
        sys.executable, 
        "-m", "uvicorn", 
        "main:api", 
        "--host", "0.0.0.0", 
        "--port", "8000"
    ])
