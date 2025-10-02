#!/usr/bin/env python3
"""
Script to check and fix the search endpoint URL in Azure Key Vault
"""
import os
from keyvault_client import KeyVaultClient

def main():
    try:
        kv_client = KeyVaultClient()
        
        # Get the current search endpoint
        current_endpoint = kv_client.get_secret('search-endpoint')
        print(f"Current search endpoint: '{current_endpoint}'")
        print(f"Length: {len(current_endpoint)} characters")
        
        # Check if it's truncated
        if current_endpoint and not current_endpoint.endswith('.net'):
            print("ERROR: Search endpoint is truncated!")
            
            # Fix the endpoint
            if current_endpoint.endswith('.ne'):
                fixed_endpoint = current_endpoint + 't'
                print(f"Proposed fix: '{fixed_endpoint}'")
                
                # Try to update the Key Vault secret
                try:
                    print("Attempting to fix the search endpoint in Key Vault...")
                    kv_client.set_secret('search-endpoint', fixed_endpoint)
                    print("SUCCESS: Search endpoint fixed in Azure Key Vault!")
                    
                    # Verify the fix
                    updated_endpoint = kv_client.get_secret('search-endpoint')
                    print(f"Verified updated endpoint: '{updated_endpoint}'")
                    
                except Exception as e:
                    print(f"ERROR: Could not update Key Vault: {e}")
                    print("Manual fix needed in Azure Key Vault.")
            else:
                print("Unexpected truncation pattern")
        else:
            print("SUCCESS: Search endpoint looks correct")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
