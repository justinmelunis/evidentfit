#!/usr/bin/env python3
"""
Test script to debug search API responses
"""
import os
import sys
sys.path.append('.')

# Set up environment from Key Vault
from keyvault_client import KeyVaultClient

def setup_env():
    """Set up environment variables from Azure Key Vault"""
    try:
        kv_client = KeyVaultClient()
        
        # Get the required secrets and set as environment variables
        secrets_mapping = {
            'SEARCH_ENDPOINT': 'search-endpoint',
            'SEARCH_QUERY_KEY': 'search-query-key'
        }
        
        for env_var, secret_name in secrets_mapping.items():
            try:
                secret_value = kv_client.get_secret(secret_name)
                if secret_value:
                    os.environ[env_var] = secret_value
                    print(f"Set {env_var}")
                else:
                    print(f"WARNING: {secret_name} is empty")
            except Exception as e:
                print(f"ERROR: Failed to get {secret_name}: {e}")
                return False
        
        # Set additional required variables
        os.environ['SEARCH_INDEX'] = 'evidentfit-index'
        
        return True
        
    except Exception as e:
        print(f"ERROR: Key Vault access failed: {e}")
        return False

if __name__ == "__main__":
    print("Setting up environment...")
    if not setup_env():
        sys.exit(1)
    
    print("Testing search...")
    from clients.search_read import search_docs
    
    try:
        results = search_docs('creatine strength', top=2)
        print(f"SUCCESS: Retrieved {len(results)} documents")
        if results:
            print(f"First result: {results[0].get('title', 'No title')}")
    except Exception as e:
        print(f"ERROR: {e}")
