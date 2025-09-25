# PowerShell script to deploy EvidentFit to Azure
# Run this from the project root directory

Write-Host "🚀 Deploying EvidentFit to Azure..." -ForegroundColor Green

# Check if Azure CLI is installed
if (!(Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Azure CLI not found. Please install it first: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli" -ForegroundColor Red
    exit 1
}

# Login to Azure (if not already logged in)
Write-Host "🔐 Checking Azure login status..." -ForegroundColor Yellow
$loginStatus = az account show 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Please login to Azure..." -ForegroundColor Yellow
    az login
}

# Set variables
$resourceGroup = "evidentfit-rg"
$location = "eastus"
$apiAppName = "evidentfit-api-$(Get-Random)"
$frontendAppName = "evidentfit-web-$(Get-Random)"
$appServicePlan = "evidentfit-plan"

Write-Host "📦 Creating resource group: $resourceGroup" -ForegroundColor Blue
az group create --name $resourceGroup --location $location

Write-Host "🏗️ Creating App Service Plan: $appServicePlan" -ForegroundColor Blue
az appservice plan create --name $appServicePlan --resource-group $resourceGroup --sku B1 --is-linux

Write-Host "🐍 Creating API App Service: $apiAppName" -ForegroundColor Blue
az webapp create --resource-group $resourceGroup --plan $appServicePlan --name $apiAppName --runtime "PYTHON|3.11"

Write-Host "⚙️ Configuring API settings..." -ForegroundColor Blue
az webapp config appsettings set --resource-group $resourceGroup --name $apiAppName --settings `
  HOST=0.0.0.0 `
  PORT=8000 `
  ALLOWED_ORIGINS=https://$frontendAppName.azurewebsites.net `
  DEMO_USER=demo `
  DEMO_PW=demo123 `
  AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/ `
  AZURE_OPENAI_API_KEY=your-openai-api-key `
  AZURE_OPENAI_API_VERSION=2024-02-15-preview `
  AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini

Write-Host "🌐 Creating Frontend App Service: $frontendAppName" -ForegroundColor Blue
az webapp create --resource-group $resourceGroup --plan $appServicePlan --name $frontendAppName --runtime "NODE|18-lts"

Write-Host "⚙️ Configuring Frontend settings..." -ForegroundColor Blue
az webapp config appsettings set --resource-group $resourceGroup --name $frontendAppName --settings `
  NEXT_PUBLIC_API_BASE=https://$apiAppName.azurewebsites.net `
  NEXT_PUBLIC_DEMO_USER=demo `
  NEXT_PUBLIC_DEMO_PW=demo123

Write-Host "📁 Creating deployment packages..." -ForegroundColor Blue

# Create API package
Compress-Archive -Path "api\*" -DestinationPath "api.zip" -Force

# Create Frontend package  
Compress-Archive -Path "web\evidentfit-web\*" -DestinationPath "web.zip" -Force

Write-Host "🚀 Deploying API..." -ForegroundColor Green
az webapp deployment source config-zip --resource-group $resourceGroup --name $apiAppName --src api.zip

Write-Host "🚀 Deploying Frontend..." -ForegroundColor Green
az webapp deployment source config-zip --resource-group $resourceGroup --name $frontendAppName --src web.zip

Write-Host "🔗 Enabling CORS..." -ForegroundColor Blue
az webapp cors add --resource-group $resourceGroup --name $apiAppName --allowed-origins https://$frontendAppName.azurewebsites.net

Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host "🌐 API URL: https://$apiAppName.azurewebsites.net" -ForegroundColor Cyan
Write-Host "🌐 Frontend URL: https://$frontendAppName.azurewebsites.net" -ForegroundColor Cyan
Write-Host "🔍 Test API: https://$apiAppName.azurewebsites.net/healthz" -ForegroundColor Yellow

# Clean up
Remove-Item "api.zip" -ErrorAction SilentlyContinue
Remove-Item "web.zip" -ErrorAction SilentlyContinue

Write-Host "🎉 EvidentFit is now live on Azure!" -ForegroundColor Green
