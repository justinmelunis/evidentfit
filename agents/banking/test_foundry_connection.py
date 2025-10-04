#!/usr/bin/env python3
"""
Test Foundry chat connection
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv('banking_init.env')

# Try to use Key Vault for credentials (same as API)
try:
    sys.path.append('../../api')
    from keyvault_client import KeyVaultClient
    
    # Initialize Key Vault client
    kv_client = KeyVaultClient()
    
    # Get credentials from Key Vault
    foundation_endpoint = kv_client.get_secret("foundation-endpoint")
    foundation_key = kv_client.get_secret("foundation-key")
    
    if foundation_endpoint and foundation_key:
        os.environ["FOUNDATION_ENDPOINT"] = foundation_endpoint
        os.environ["FOUNDATION_KEY"] = foundation_key
        print("SUCCESS: Using Key Vault credentials for Foundry")
    else:
        print("WARNING: Key Vault credentials not available, using local env file")
        
except Exception as e:
    print(f"WARNING: Key Vault not available ({e}), using local env file")

# Add the API clients to the path
sys.path.append('../../api/clients')

from foundry_chat import chat

def test_connection():
    """Test basic Foundry chat connection"""
    try:
        messages = [
            {"role": "user", "content": "Say 'Connection successful' if you can read this."}
        ]
        
        response = chat(messages, max_tokens=50)
        print(f"SUCCESS: Connection successful! Response: {response}")
        return True
        
    except Exception as e:
        print(f"ERROR: Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()
