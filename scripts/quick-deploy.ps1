# Quick deployment script for EvidentFit to Azure Container Apps
# This script provides an interactive deployment experience

param(
    [string]$ResourceGroupName = "rg-evidentfit",
    [string]$Location = "eastus2",
    [string]$ACRName = "evidentfitacr",
    [string]$EnvironmentName = "evidentfit-env"
)

Write-Host "🚀 EvidentFit Quick Deploy to Azure Container Apps" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green

# Check prerequisites
Write-Host "`n🔍 Checking prerequisites..." -ForegroundColor Yellow

# Check Azure CLI
try {
    $azVersion = az version --output tsv 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI not found"
    }
    Write-Host "✅ Azure CLI: $azVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Azure CLI not found. Please install Azure CLI." -ForegroundColor Red
    exit 1
}

# Check Docker
try {
    docker version | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check if logged in to Azure
try {
    $account = az account show 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Not logged in"
    }
    Write-Host "✅ Azure CLI authenticated" -ForegroundColor Green
} catch {
    Write-Host "❌ Please run 'az login' first" -ForegroundColor Red
    exit 1
}

# Interactive setup
Write-Host "`n📋 Deployment Configuration:" -ForegroundColor Yellow
Write-Host "Resource Group: $ResourceGroupName" -ForegroundColor White
Write-Host "Location: $Location" -ForegroundColor White
Write-Host "ACR Name: $ACRName" -ForegroundColor White
Write-Host "Environment: $EnvironmentName" -ForegroundColor White

$confirm = Read-Host "`nDo you want to proceed with this configuration? (y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "❌ Deployment cancelled" -ForegroundColor Red
    exit 0
}

# Create resource group
Write-Host "`n🏗️ Creating resource group..." -ForegroundColor Yellow
az group create --name $ResourceGroupName --location $Location
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to create resource group" -ForegroundColor Red
    exit 1
}

# Create ACR
Write-Host "`n📦 Creating Azure Container Registry..." -ForegroundColor Yellow
az acr create --resource-group $ResourceGroupName --name $ACRName --sku Basic --admin-enabled true
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to create ACR" -ForegroundColor Red
    exit 1
}

# Create Container Apps Environment
Write-Host "`n🌍 Creating Container Apps Environment..." -ForegroundColor Yellow
az containerapp env create --name $EnvironmentName --resource-group $ResourceGroupName --location $Location
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to create Container Apps Environment" -ForegroundColor Red
    exit 1
}

# Login to ACR
Write-Host "`n🔐 Logging into ACR..." -ForegroundColor Yellow
az acr login --name $ACRName

# Build and push images
Write-Host "`n🔨 Building and pushing images..." -ForegroundColor Yellow

# Build API
Write-Host "Building API image..." -ForegroundColor Yellow
docker build -t $ACRName.azurecr.io/evidentfit-api:latest -f api/Dockerfile .
docker push $ACRName.azurecr.io/evidentfit-api:latest

# Build Web
Write-Host "Building Web image..." -ForegroundColor Yellow
docker build -t $ACRName.azurecr.io/evidentfit-web:latest -f web/evidentfit-web/Dockerfile ./web/evidentfit-web
docker push $ACRName.azurecr.io/evidentfit-web:latest

# Deploy API
Write-Host "`n🚀 Deploying API Container App..." -ForegroundColor Yellow
az containerapp create `
    --name "evidentfit-api" `
    --resource-group $ResourceGroupName `
    --environment $EnvironmentName `
    --image $ACRName.azurecr.io/evidentfit-api:latest `
    --target-port 8000 `
    --ingress external `
    --registry-server $ACRName.azurecr.io `
    --cpu 0.5 `
    --memory 1Gi `
    --min-replicas 1 `
    --max-replicas 3 `
    --env-vars "HOST=0.0.0.0" "PORT=8000"

# Get API URL
$apiUrl = az containerapp show --name "evidentfit-api" --resource-group $ResourceGroupName --query "properties.configuration.ingress.fqdn" -o tsv
$apiUrl = "https://$apiUrl"

# Deploy Web
Write-Host "`n🚀 Deploying Web Container App..." -ForegroundColor Yellow
az containerapp create `
    --name "evidentfit-web" `
    --resource-group $ResourceGroupName `
    --environment $EnvironmentName `
    --image $ACRName.azurecr.io/evidentfit-web:latest `
    --target-port 3000 `
    --ingress external `
    --registry-server $ACRName.azurecr.io `
    --cpu 0.5 `
    --memory 1Gi `
    --min-replicas 1 `
    --max-replicas 3 `
    --env-vars "NEXT_PUBLIC_API_BASE=$apiUrl" "NEXT_PUBLIC_DEMO_USER=demo" "NEXT_PUBLIC_DEMO_PW=demo123"

# Get Web URL
$webUrl = az containerapp show --name "evidentfit-web" --resource-group $ResourceGroupName --query "properties.configuration.ingress.fqdn" -o tsv
$webUrl = "https://$webUrl"

# Success message
Write-Host "`n🎉 Deployment completed successfully!" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green
Write-Host "📱 Web Application: $webUrl" -ForegroundColor Cyan
Write-Host "🔗 API Application: $apiUrl" -ForegroundColor Cyan
Write-Host "📊 API Health Check: $apiUrl/healthz" -ForegroundColor Cyan
Write-Host "📚 API Documentation: $apiUrl/docs" -ForegroundColor Cyan

Write-Host "`n🔧 Next Steps:" -ForegroundColor Yellow
Write-Host "1. Configure Azure Key Vault access for the Container Apps" -ForegroundColor White
Write-Host "2. Set up managed identity for secure secret access" -ForegroundColor White
Write-Host "3. Test the deployed application" -ForegroundColor White
Write-Host "4. Configure custom domains (optional)" -ForegroundColor White

Write-Host "`n📖 For detailed configuration, see: docs/DOCKER_DEPLOYMENT.md" -ForegroundColor Yellow
