#!/usr/bin/env python3
"""
Run Banking Initialization

Simple script to initialize all banking caches.
Run this after deploying new research or when setting up the system.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv('azure-openai.env')
load_dotenv()

# Check required environment variables
required_vars = ['SEARCH_ENDPOINT', 'SEARCH_QUERY_KEY', 'FOUNDATION_ENDPOINT', 'FOUNDATION_KEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"❌ Missing required environment variables: {missing_vars}")
    print("Please ensure azure-openai.env is configured properly.")
    sys.exit(1)

print("✅ Environment variables loaded")

# Import and run banking initialization
try:
    from initialize_banking import main
    main()
except Exception as e:
    print(f"❌ Banking initialization failed: {e}")
    sys.exit(1)
