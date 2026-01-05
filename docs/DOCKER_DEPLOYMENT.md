# EvidentFit Docker Deployment Guide

This guide covers deploying EvidentFit to Azure Container Apps using Docker containers.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Next.js Web   │    │   FastAPI API   │    │  Azure Key Vault│
│   (Port 3000)   │◄──►│   (Port 8000)   │◄──►│   (Secrets)     │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │ Azure AI Foundry │
                    │   (AI Models)   │
                    └─────────────────┘
```

## 📋 Prerequisites

- Docker Desktop installed and running
- Azure CLI installed (`az --version`)
- Azure subscription with billing configured (see [Azure Billing Setup Guide](AZURE_BILLING_SETUP.md))
- Payment method added to Azure account
- Azure Container Registry (ACR) created
- Azure Container Apps Environment created
- Azure Key Vault with secrets configured

**Important**: Before deploying, ensure you have completed the billing setup steps in [AZURE_BILLING_SETUP.md](AZURE_BILLING_SETUP.md).

## 🚀 Local Development

### 1. Start Docker Desktop
Ensure Docker Desktop is running on your machine.

### 2. Build API Container
```bash
# From project root
docker build -t evidentfit-api:local -f api/Dockerfile .
```

### 3. Build Web Container
```bash
# From project root
docker build -t evidentfit-web:local -f web/evidentfit-web/Dockerfile ./web/evidentfit-web
```

### 4. Run with Docker Compose
```bash
# Start both services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### 5. Test Locally
- **API Health**: http://localhost:8000/healthz
- **Web App**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

## 🔧 Azure Container Apps Deployment

### 1. Prerequisites Setup

#### Create Azure Container Registry
```bash
# Set variables
RESOURCE_GROUP="rg-evidentfit"
LOCATION="eastus2"
ACR_NAME="evidentfitacr"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create ACR
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true
```

#### Create Container Apps Environment
```bash
# Create Container Apps Environment
az containerapp env create \
  --name "evidentfit-env" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### 2. Build and Push Images

#### Login to ACR
```bash
az acr login --name $ACR_NAME
```

#### Build and Push API
```bash
# Build API image
docker build -t $ACR_NAME.azurecr.io/evidentfit-api:latest -f api/Dockerfile .

# Push to ACR
docker push $ACR_NAME.azurecr.io/evidentfit-api:latest
```

#### Build and Push Web
```bash
# Build Web image
docker build -t $ACR_NAME.azurecr.io/evidentfit-web:latest -f web/evidentfit-web/Dockerfile ./web/evidentfit-web

# Push to ACR
docker push $ACR_NAME.azurecr.io/evidentfit-web:latest
```

### 3. Deploy to Container Apps

#### Deploy API Container App
```bash
az containerapp create \
  --name "evidentfit-api" \
  --resource-group $RESOURCE_GROUP \
  --environment "evidentfit-env" \
  --image $ACR_NAME.azurecr.io/evidentfit-api:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server $ACR_NAME.azurecr.io \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars "HOST=0.0.0.0" "PORT=8000"
```

#### Deploy Web Container App
```bash
# Get API URL first
API_URL=$(az containerapp show --name "evidentfit-api" --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)
API_URL="https://$API_URL"

# Deploy Web Container App
az containerapp create \
  --name "evidentfit-web" \
  --resource-group $RESOURCE_GROUP \
  --environment "evidentfit-env" \
  --image $ACR_NAME.azurecr.io/evidentfit-web:latest \
  --target-port 3000 \
  --ingress external \
  --registry-server $ACR_NAME.azurecr.io \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars "NEXT_PUBLIC_API_BASE=$API_URL" "NEXT_PUBLIC_DEMO_USER=demo" "NEXT_PUBLIC_DEMO_PW=demo123"
```

### 4. Automated Deployment Script

Use the provided PowerShell script for automated deployment:

```powershell
# Run deployment script
.\deploy\deploy-to-aca.ps1 `
  -ResourceGroupName "rg-evidentfit" `
  -ContainerAppEnvironmentName "evidentfit-env" `
  -ApiAppName "evidentfit-api" `
  -WebAppName "evidentfit-web" `
  -RegistryName "evidentfitacr"
```

## 🔐 Key Vault Integration

### 1. Configure Managed Identity

#### Create Managed Identity for API
```bash
# Create managed identity
az identity create \
  --name "evidentfit-api-identity" \
  --resource-group $RESOURCE_GROUP

# Get identity details
IDENTITY_ID=$(az identity show --name "evidentfit-api-identity" --resource-group $RESOURCE_GROUP --query "id" -o tsv)
IDENTITY_CLIENT_ID=$(az identity show --name "evidentfit-api-identity" --resource-group $RESOURCE_GROUP --query "clientId" -o tsv)
```

#### Assign Key Vault Access
```bash
# Get Key Vault details
KEY_VAULT_NAME="kv-evidentfit"
SUBSCRIPTION_ID=$(az account show --query "id" -o tsv)

# Assign Key Vault Secrets User role
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $IDENTITY_CLIENT_ID \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME"
```

### 2. Update Container App with Managed Identity

```bash
# Update API Container App with managed identity
az containerapp update \
  --name "evidentfit-api" \
  --resource-group $RESOURCE_GROUP \
  --user-assigned $IDENTITY_ID
```

## 🧪 Testing Deployment

### 1. Get Application URLs
```bash
# Get API URL
API_URL=$(az containerapp show --name "evidentfit-api" --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)
echo "API URL: https://$API_URL"

# Get Web URL
WEB_URL=$(az containerapp show --name "evidentfit-web" --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)
echo "Web URL: https://$WEB_URL"
```

### 2. Test Endpoints
```bash
# Test API health
curl https://$API_URL/healthz

# Test API root
curl https://$API_URL/

# Test web application
curl https://$WEB_URL/
```

## 📊 Monitoring and Logs

### View Container Logs
```bash
# API logs
az containerapp logs show --name "evidentfit-api" --resource-group $RESOURCE_GROUP --follow

# Web logs
az containerapp logs show --name "evidentfit-web" --resource-group $RESOURCE_GROUP --follow
```

### Monitor Performance
- Use Azure Monitor for application insights
- Set up alerts for container health
- Monitor Key Vault access patterns

## 🔄 Updates and Scaling

### Update Application
```bash
# Build new image
docker build -t $ACR_NAME.azurecr.io/evidentfit-api:latest -f api/Dockerfile .
docker push $ACR_NAME.azurecr.io/evidentfit-api:latest

# Update container app
az containerapp update \
  --name "evidentfit-api" \
  --resource-group $RESOURCE_GROUP \
  --image $ACR_NAME.azurecr.io/evidentfit-api:latest
```

### Scale Application
```bash
# Scale API
az containerapp update \
  --name "evidentfit-api" \
  --resource-group $RESOURCE_GROUP \
  --min-replicas 2 \
  --max-replicas 5
```

## 🛠️ Troubleshooting

### Common Issues

1. **Container won't start**
   - Check logs: `az containerapp logs show`
   - Verify environment variables
   - Check Key Vault permissions

2. **Key Vault access denied**
   - Verify managed identity assignment
   - Check Key Vault access policies
   - Ensure secrets exist

3. **API not responding**
   - Check health endpoint: `/healthz`
   - Verify port configuration
   - Check CORS settings

### Debug Commands
```bash
# Check container status
az containerapp show --name "evidentfit-api" --resource-group $RESOURCE_GROUP

# View environment variables
az containerapp show --name "evidentfit-api" --resource-group $RESOURCE_GROUP --query "properties.template.containers[0].env"

# Check ingress configuration
az containerapp show --name "evidentfit-api" --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress"
```

## 📚 Additional Resources

- [Azure Container Apps Documentation](https://docs.microsoft.com/en-us/azure/container-apps/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Next.js Docker Deployment](https://nextjs.org/docs/deployment#docker-image)
- [FastAPI Docker Deployment](https://fastapi.tiangolo.com/deployment/docker/)

## 🎯 Next Steps

1. Set up CI/CD pipeline with GitHub Actions
2. Configure custom domains
3. Implement SSL certificates
4. Set up monitoring and alerting
5. Configure backup and disaster recovery
