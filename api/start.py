#!/usr/bin/env python3
"""
Azure deployment startup script for EvidentFit API
"""
import os
import uvicorn
from main import api, HOST, PORT

if __name__ == "__main__":
    # Azure App Service uses PORT environment variable
    port = int(os.getenv("PORT", PORT))
    host = os.getenv("HOST", HOST)
    
    print(f"Starting EvidentFit API on {host}:{port}")
    print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    print(f"Allowed origins: {os.getenv('ALLOWED_ORIGINS', 'default')}")
    
    uvicorn.run(
        "main:api",
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
