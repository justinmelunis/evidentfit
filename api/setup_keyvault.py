#!/usr/bin/env python3
"""
Azure Key Vault Setup Script for EvidentFit

This script helps you migrate secrets from environment variables to Azure Key Vault.
Run this script to populate your Key Vault with the necessary secrets.

Usage:
    python setup_keyvault.py
"""

import os
import sys
from dotenv import load_dotenv
from keyvault_client import KeyVaultClient

def main():
    """Setup Key Vault with secrets from environment variables."""
    
    # Load environment variables
    load_dotenv('azure-openai.env')
    load_dotenv()
    
    print("🔐 Azure Key Vault Setup for EvidentFit")
    print("=" * 50)
    
    try:
        # Initialize Key Vault client
        print("Connecting to Azure Key Vault...")
        client = KeyVaultClient()
        print(f"✅ Connected to: {client.vault_url}")
        
        # Define secrets to migrate
        secrets_to_migrate = {
            "azure-openai-endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "FoundryApiKey": os.getenv("AZURE_OPENAI_API_KEY"),  # Using your existing secret name
            "azure-openai-api-version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
            "azure-openai-deployment-name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini"),
            "demo-user": os.getenv("DEMO_USER", "demo"),
            "demo-password": os.getenv("DEMO_PW", "demo123")
        }
        
        print("\n📋 Secrets to migrate:")
        for name, value in secrets_to_migrate.items():
            if value:
                # Mask sensitive values for display
                display_value = value[:8] + "..." if len(value) > 8 else value
                print(f"  • {name}: {display_value}")
            else:
                print(f"  • {name}: ❌ Not found in environment")
        
        print("\n🚀 Migrating secrets to Key Vault...")
        
        success_count = 0
        for secret_name, secret_value in secrets_to_migrate.items():
            if secret_value:
                print(f"  Setting {secret_name}...", end=" ")
                if client.set_secret(secret_name, secret_value):
                    print("✅")
                    success_count += 1
                else:
                    print("❌")
            else:
                print(f"  Skipping {secret_name} (no value)")
        
        print(f"\n✅ Successfully migrated {success_count} secrets to Key Vault")
        
        # List all secrets in Key Vault
        print("\n📝 Current secrets in Key Vault:")
        all_secrets = client.list_secrets()
        for secret_name in sorted(all_secrets):
            print(f"  • {secret_name}")
        
        print("\n🎉 Key Vault setup complete!")
        print("\nNext steps:")
        print("1. Test the application: python main.py")
        print("2. Verify secrets are being retrieved from Key Vault")
        print("3. Remove sensitive values from azure-openai.env (optional)")
        
    except Exception as e:
        print(f"❌ Error setting up Key Vault: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you're logged in: az login")
        print("2. Verify Key Vault URL is correct")
        print("3. Check your Azure permissions")
        sys.exit(1)

if __name__ == "__main__":
    main()
