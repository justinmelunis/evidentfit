# Complete Azure Setup Guide

This guide walks through the complete Azure setup process for EvidentFit, from billing to deployment.

## Overview

Complete setup includes:
1. Azure billing configuration
2. Resource group creation
3. Azure Container Registry (ACR)
4. Azure Key Vault
5. Azure AI Foundry setup
6. Container Apps Environment
7. Managed Identity
8. Container Apps deployment

## Step-by-Step Instructions

### Step 1: Billing Setup

**See detailed guide**: [docs/AZURE_BILLING_SETUP.md](../docs/AZURE_BILLING_SETUP.md)

Quick checklist:
- [ ] Add payment method (credit card) in Azure Portal
- [ ] Set up billing alerts ($50, $100, $200 thresholds)
- [ ] Configure budget alerts (optional but recommended)
- [ ] Review free tier limits (if applicable)

### Step 2: Create Resource Group

```bash
az group create --name rg-evidentfit --location eastus2
```

### Step 3: Create Azure Container Registry (ACR)

```bash
ACR_NAME="evidentfitacr"
az acr create \
  --resource-group rg-evidentfit \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true
```

### Step 4: Create Azure Key Vault

```bash
KEY_VAULT_NAME="kv-evidentfit"
az keyvault create \
  --name $KEY_VAULT_NAME \
  --resource-group rg-evidentfit \
  --location eastus2
```

### Step 5: Store Secrets in Key Vault

**Important**: Replace placeholder values with your actual credentials.

```bash
# Azure AI Foundry endpoint and key (from Azure AI Studio)
az keyvault secret set --vault-name $KEY_VAULT_NAME --name FOUNDATION-ENDPOINT --value "https://your-project-endpoint.openai.azure.com"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name FOUNDATION-KEY --value "your-api-key"

# Azure AI Search endpoint and key
az keyvault secret set --vault-name $KEY_VAULT_NAME --name SEARCH-ENDPOINT --value "https://your-search-service.search.windows.net"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name SEARCH-QUERY-KEY --value "your-search-query-key"

# JWT secret key (generate a secure key)
az keyvault secret set --vault-name $KEY_VAULT_NAME --name JWT-SECRET-KEY --value "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

# Chatbot credentials (change from defaults)
az keyvault secret set --vault-name $KEY_VAULT_NAME --name DEMO-USER --value "your_username"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name DEMO-PW --value "your_secure_password"
```

### Step 6: Set Up Azure AI Foundry

1. Navigate to [Azure Portal](https://portal.azure.com) → **Azure AI Studio**
2. Create or select an AI Project
3. Deploy or use existing GPT-4o-mini model
4. Copy the Project endpoint URL (e.g., `https://your-project-endpoint.openai.azure.com`)
5. Copy the API key
6. Store in Key Vault (see Step 5)

**Note**: Azure AI Foundry requires enrollment/approval. If you don't have access, request it through Azure support.

### Step 7: Create Container Apps Environment

```bash
az containerapp env create \
  --name evidentfit-env \
  --resource-group rg-evidentfit \
  --location eastus2
```

### Step 8: Create Managed Identity

```bash
# Create identity
az identity create \
  --name evidentfit-api-identity \
  --resource-group rg-evidentfit

# Get identity client ID
IDENTITY_CLIENT_ID=$(az identity show \
  --name evidentfit-api-identity \
  --resource-group rg-evidentfit \
  --query clientId -o tsv)

# Get subscription ID
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Grant Key Vault access
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $IDENTITY_CLIENT_ID \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/rg-evidentfit/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME"
```

### Step 9: Build and Push Docker Images

```bash
# Login to ACR
az acr login --name $ACR_NAME

# Build and push API
docker build -t $ACR_NAME.azurecr.io/evidentfit-api:latest -f api/Dockerfile .
docker push $ACR_NAME.azurecr.io/evidentfit-api:latest

# Build and push Web
docker build -t $ACR_NAME.azurecr.io/evidentfit-web:latest -f web/evidentfit-web/Dockerfile ./web/evidentfit-web
docker push $ACR_NAME.azurecr.io/evidentfit-web:latest
```

### Step 10: Deploy API Container App

```bash
# Get identity resource ID
IDENTITY_ID=$(az identity show \
  --name evidentfit-api-identity \
  --resource-group rg-evidentfit \
  --query id -o tsv)

# Deploy API
az containerapp create \
  --name evidentfit-api \
  --resource-group rg-evidentfit \
  --environment evidentfit-env \
  --image $ACR_NAME.azurecr.io/evidentfit-api:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server $ACR_NAME.azurecr.io \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --user-assigned $IDENTITY_ID \
  --env-vars "HOST=0.0.0.0" "PORT=8000"
```

### Step 11: Configure API Environment Variables from Key Vault

```bash
# Reference Key Vault secrets as environment variables
az containerapp update \
  --name evidentfit-api \
  --resource-group rg-evidentfit \
  --set-env-vars \
    "FOUNDATION_ENDPOINT=@Microsoft.KeyVault(SecretUri=https://$KEY_VAULT_NAME.vault.azure.net/secrets/FOUNDATION-ENDPOINT/)" \
    "FOUNDATION_KEY=@Microsoft.KeyVault(SecretUri=https://$KEY_VAULT_NAME.vault.azure.net/secrets/FOUNDATION-KEY/)" \
    "SEARCH_ENDPOINT=@Microsoft.KeyVault(SecretUri=https://$KEY_VAULT_NAME.vault.azure.net/secrets/SEARCH-ENDPOINT/)" \
    "SEARCH_QUERY_KEY=@Microsoft.KeyVault(SecretUri=https://$KEY_VAULT_NAME.vault.azure.net/secrets/SEARCH-QUERY-KEY/)" \
    "JWT_SECRET_KEY=@Microsoft.KeyVault(SecretUri=https://$KEY_VAULT_NAME.vault.azure.net/secrets/JWT-SECRET-KEY/)" \
    "DEMO_USER=@Microsoft.KeyVault(SecretUri=https://$KEY_VAULT_NAME.vault.azure.net/secrets/DEMO-USER/)" \
    "DEMO_PW=@Microsoft.KeyVault(SecretUri=https://$KEY_VAULT_NAME.vault.azure.net/secrets/DEMO-PW/)"
```

### Step 12: Deploy Web Container App

```bash
# Get API URL
API_URL=$(az containerapp show \
  --name evidentfit-api \
  --resource-group rg-evidentfit \
  --query properties.configuration.ingress.fqdn -o tsv)
API_URL="https://$API_URL"

# Deploy Web
az containerapp create \
  --name evidentfit-web \
  --resource-group rg-evidentfit \
  --environment evidentfit-env \
  --image $ACR_NAME.azurecr.io/evidentfit-web:latest \
  --target-port 3000 \
  --ingress external \
  --registry-server $ACR_NAME.azurecr.io \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars "NEXT_PUBLIC_API_BASE=$API_URL"
```

### Step 13: Verify Deployment

```bash
# Get API URL
API_URL=$(az containerapp show \
  --name evidentfit-api \
  --resource-group rg-evidentfit \
  --query properties.configuration.ingress.fqdn -o tsv)

# Get Web URL
WEB_URL=$(az containerapp show \
  --name evidentfit-web \
  --resource-group rg-evidentfit \
  --query properties.configuration.ingress.fqdn -o tsv)

# Test API health
curl https://$API_URL/healthz

# Test Web
curl https://$WEB_URL/
```

## Troubleshooting

### Container App won't start
- Check logs: `az containerapp logs show --name evidentfit-api --resource-group rg-evidentfit --follow`
- Verify Key Vault secrets are accessible
- Check managed identity has Key Vault permissions

### Key Vault access denied
- Verify managed identity is assigned to Container App
- Check role assignment: `az role assignment list --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/rg-evidentfit/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME"`
- Ensure "Key Vault Secrets User" role is assigned

### API returns 401
- Verify DEMO_USER and DEMO_PW are set correctly
- Check Key Vault secret names match exactly
- Test with curl: `curl -u username:password https://$API_URL/healthz`

## Next Steps

After deployment:
1. Monitor costs in Azure Portal → Cost Management
2. Set up application insights for monitoring (optional)
3. Configure custom domains (optional)
4. Review and adjust scaling settings as needed

## Cost Estimates

- **Container Apps**: ~$15-30/month
- **Container Registry**: ~$5/month
- **Key Vault**: ~$0.03/month
- **AI Foundry (GPT-4o-mini)**: Pay-per-use (~$0.10 per 1M input tokens)
- **Total**: ~$20-85/month for basic deployment

See [docs/AZURE_BILLING_SETUP.md](../docs/AZURE_BILLING_SETUP.md) for detailed cost management.
