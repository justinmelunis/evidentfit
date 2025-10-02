#!/usr/bin/env python3
"""
Run Banking Initialization

Simple script to initialize all banking caches using Azure Key Vault.
Run this after deploying new research or when setting up the system.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv('azure-openai.env')
load_dotenv()

def setup_environment_from_keyvault():
    """Set up environment variables from Azure Key Vault"""
    try:
        from keyvault_client import KeyVaultClient
        
        print("Retrieving secrets from Azure Key Vault...")
        kv_client = KeyVaultClient()
        
        # Get the required secrets and set as environment variables
        secrets_mapping = {
            'FOUNDATION_ENDPOINT': 'foundation-endpoint',
            'FOUNDATION_KEY': 'foundation-key',
            'SEARCH_ENDPOINT': 'search-endpoint',
            'SEARCH_QUERY_KEY': 'search-query-key'
        }
        
        for env_var, secret_name in secrets_mapping.items():
            try:
                secret_value = kv_client.get_secret(secret_name)
                if secret_value:
                    os.environ[env_var] = secret_value
                    print(f"SUCCESS: Retrieved {env_var}")
                else:
                    print(f"WARNING: {secret_name} is empty")
            except Exception as e:
                print(f"ERROR: Failed to get {secret_name}: {e}")
                return False
        
        # Set additional required variables
        os.environ['FOUNDATION_CHAT_MODEL'] = 'gpt-4o-mini'
        os.environ['FOUNDATION_EMBED_MODEL'] = 'text-embedding-3-small'
        os.environ['SEARCH_INDEX'] = 'evidentfit-index'
        os.environ['INDEX_VERSION'] = 'v1-2025-09-25'
        
        return True
        
    except Exception as e:
        print(f"ERROR: Key Vault access failed: {e}")
        print("Make sure you're logged in with 'az login' and have Key Vault access")
        return False

# Set up environment from Key Vault
if not setup_environment_from_keyvault():
    sys.exit(1)

# Check that all required variables are now set
required_vars = ['SEARCH_ENDPOINT', 'SEARCH_QUERY_KEY', 'FOUNDATION_ENDPOINT', 'FOUNDATION_KEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"ERROR: Still missing environment variables after Key Vault retrieval: {missing_vars}")
    sys.exit(1)

print("SUCCESS: All environment variables configured from Key Vault")

# Import and run banking initialization
try:
    from initialize_banking import main
    main()
except Exception as e:
    print(f"ERROR: Banking initialization failed: {e}")
    sys.exit(1)
