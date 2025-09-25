# Azure Key Vault Migration Guide

This guide explains how to migrate from hardcoded secrets to Azure Key Vault for secure secret management.

## 🔐 Overview

Azure Key Vault provides centralized secret management with:
- **Secure Storage**: Secrets encrypted at rest and in transit
- **Access Control**: Role-based access to secrets
- **Audit Logging**: Track who accessed what secrets when
- **Secret Rotation**: Update secrets without code changes
- **Compliance**: Meet security and compliance requirements

## 📋 Prerequisites

1. **Azure Key Vault**: `https://kv-evidentfit.vault.azure.net/`
2. **Azure CLI**: Installed and configured
3. **Python Dependencies**: `azure-keyvault-secrets`, `azure-identity`

## 🚀 Migration Steps

### Step 1: Install Dependencies

```bash
cd api
pip install -r requirements.txt
```

### Step 2: Authenticate with Azure

```bash
# Login to Azure CLI
az login

# Verify access to Key Vault
az keyvault secret list --vault-name kv-evidentfit
```

### Step 3: Run Migration Script

```bash
python setup_keyvault.py
```

This script will:
- Connect to your Key Vault
- Migrate secrets from environment variables
- Verify the migration was successful

### Step 4: Test the Application

```bash
python main.py
```

The application will now:
1. Try to get secrets from Key Vault first
2. Fall back to environment variables if Key Vault is unavailable
3. Log which source is being used

## 🔧 Configuration

### Environment Variables

The application supports multiple authentication methods:

#### Option 1: Azure CLI (Recommended for local development)
```bash
az login
```

#### Option 2: Service Principal
```bash
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
export AZURE_TENANT_ID="your-tenant-id"
```

### Key Vault Secrets

The following secrets are expected in Key Vault:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `azure-openai-endpoint` | Azure OpenAI endpoint | `https://your-resource.openai.azure.com/` |
| `azure-openai-api-key` | Azure OpenAI API key | `your-api-key` |
| `azure-openai-api-version` | API version | `2024-02-15-preview` |
| `azure-openai-deployment-name` | Model deployment name | `gpt-4o-mini` |
| `demo-user` | Demo username | `demo` |
| `demo-password` | Demo password | `demo123` |

## 🔍 Troubleshooting

### Common Issues

#### 1. Authentication Failed
```
Error: No valid Azure credentials found
```
**Solution**: Run `az login` or set service principal credentials

#### 2. Key Vault Access Denied
```
Error: Access denied to Key Vault
```
**Solution**: Check your Azure permissions and Key Vault access policies

#### 3. Secret Not Found
```
Warning: Key Vault unavailable, using fallback
```
**Solution**: Verify Key Vault URL and secret names

### Debug Mode

Enable debug logging to see Key Vault operations:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🔄 Secret Rotation

To rotate secrets:

1. **Update in Key Vault**: Use Azure Portal or CLI
2. **No Code Changes**: Application automatically picks up new values
3. **Zero Downtime**: Secrets are cached and refreshed as needed

```bash
# Example: Rotate API key
az keyvault secret set --vault-name kv-evidentfit --name azure-openai-api-key --value "new-api-key"
```

## 🛡️ Security Best Practices

1. **Least Privilege**: Grant minimal required permissions
2. **Regular Rotation**: Rotate secrets periodically
3. **Audit Logging**: Monitor secret access
4. **Network Security**: Use private endpoints when possible
5. **Backup**: Ensure Key Vault is backed up

## 📊 Monitoring

Monitor Key Vault usage in Azure Portal:
- **Access Logs**: Who accessed what secrets
- **Audit Logs**: Administrative operations
- **Metrics**: Usage patterns and errors

## 🔗 Related Documentation

- [Azure Key Vault Documentation](https://docs.microsoft.com/en-us/azure/key-vault/)
- [Azure Identity Documentation](https://docs.microsoft.com/en-us/python/api/azure-identity/)
- [FastAPI Security Best Practices](https://fastapi.tiangolo.com/tutorial/security/)
