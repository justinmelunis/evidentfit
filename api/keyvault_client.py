import os
import logging
from typing import Optional
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv('azure-openai.env')
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KeyVaultClient:
    """
    Azure Key Vault client for secure secret management.
    Supports both local development and Azure deployment scenarios.
    """
    
    def __init__(self, vault_url: str = None):
        """
        Initialize Key Vault client.
        
        Args:
            vault_url: Azure Key Vault URL (defaults to environment variable)
        """
        self.vault_url = vault_url or os.getenv("AZURE_KEY_VAULT_URL")
        if not self.vault_url:
            raise ValueError("Azure Key Vault URL must be provided or set in AZURE_KEY_VAULT_URL")
        
        # Initialize credential (supports multiple authentication methods)
        self.credential = self._get_credential()
        
        # Initialize Key Vault client
        self.client = SecretClient(vault_url=self.vault_url, credential=self.credential)
        logger.info(f"Key Vault client initialized for: {self.vault_url}")
    
    def _get_credential(self):
        """
        Get Azure credential based on environment.
        Supports: DefaultAzureCredential, ClientSecretCredential, and local development.
        """
        try:
            # For local development, try DefaultAzureCredential first
            # This will work if you're logged in via Azure CLI
            return DefaultAzureCredential()
        except Exception as e:
            logger.warning(f"DefaultAzureCredential failed: {e}")
            
            # Fallback to ClientSecretCredential for service principal
            client_id = os.getenv("AZURE_CLIENT_ID")
            client_secret = os.getenv("AZURE_CLIENT_SECRET")
            tenant_id = os.getenv("AZURE_TENANT_ID")
            
            if client_id and client_secret and tenant_id:
                logger.info("Using ClientSecretCredential")
                return ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret
                )
            else:
                raise ValueError(
                    "No valid Azure credentials found. Please either:\n"
                    "1. Run 'az login' for local development, or\n"
                    "2. Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID"
                )
    
    def get_secret(self, secret_name: str) -> Optional[str]:
        """
        Retrieve a secret from Azure Key Vault.
        
        Args:
            secret_name: Name of the secret in Key Vault
            
        Returns:
            Secret value as string, or None if not found
        """
        try:
            # Force fresh retrieval by getting the latest version
            secret = self.client.get_secret(secret_name)
            logger.info(f"Successfully retrieved secret: {secret_name}")
            logger.info(f"Secret version: {secret.properties.version}")
            logger.info(f"Secret created: {secret.properties.created_on}")
            logger.info(f"Secret updated: {secret.properties.updated_on}")
            logger.info(f"Secret value starts with: {secret.value[:10]}...")
            return secret.value
        except Exception as e:
            logger.error(f"Failed to retrieve secret '{secret_name}': {e}")
            return None
    
    def set_secret(self, secret_name: str, secret_value: str) -> bool:
        """
        Set/update a secret in Azure Key Vault.
        
        Args:
            secret_name: Name of the secret in Key Vault
            secret_value: Value to store
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.set_secret(secret_name, secret_value)
            logger.info(f"Successfully set secret: {secret_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to set secret '{secret_name}': {e}")
            return False

# Global Key Vault client instance
_keyvault_client = None

def get_keyvault_client() -> KeyVaultClient:
    """
    Get or create the global Key Vault client instance.
    
    Returns:
        KeyVaultClient instance
    """
    global _keyvault_client
    if _keyvault_client is None:
        _keyvault_client = KeyVaultClient()
    return _keyvault_client

def refresh_keyvault_client():
    """
    Force refresh the global Key Vault client instance.
    This can help bypass any caching issues.
    """
    global _keyvault_client
    _keyvault_client = None
    logger.info("Key Vault client refreshed")

def get_secret(secret_name: str, fallback_value: str = None, force_refresh: bool = False) -> str:
    """
    Convenience function to get a secret with fallback.
    
    Args:
        secret_name: Name of the secret in Key Vault
        fallback_value: Fallback value if secret not found
        force_refresh: Force refresh the Key Vault client to bypass caching
        
    Returns:
        Secret value or fallback value
    """
    try:
        if force_refresh:
            refresh_keyvault_client()
        client = get_keyvault_client()
        secret_value = client.get_secret(secret_name)
        return secret_value if secret_value is not None else fallback_value
    except Exception as e:
        logger.warning(f"Key Vault unavailable, using fallback for '{secret_name}': {e}")
        return fallback_value
