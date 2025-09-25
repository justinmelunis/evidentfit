# Deploy EvidentFit to Azure Container Apps
# This script builds and deploys both API and Web applications

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$true)]
    [string]$ContainerAppEnvironmentName,
    
    [Parameter(Mandatory=$true)]
    [string]$ApiAppName = "evidentfit-api",
    
    [Parameter(Mandatory=$true)]
    [string]$WebAppName = "evidentfit-web",
    
    [Parameter(Mandatory=$true)]
    [string]$RegistryName,
    
    [Parameter(Mandatory=$false)]
    [string]$Location = "East US 2"
)

Write-Host "🚀 Starting EvidentFit deployment to Azure Container Apps..." -ForegroundColor Green

# Check if Azure CLI is installed and logged in
try {
    $account = az account show 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Not logged in to Azure CLI"
    }
    Write-Host "✅ Azure CLI authenticated" -ForegroundColor Green
} catch {
    Write-Host "❌ Please run 'az login' first" -ForegroundColor Red
    exit 1
}

# Check if required extensions are installed
Write-Host "📦 Checking Azure CLI extensions..." -ForegroundColor Yellow
$extensions = @("containerapp", "container")
foreach ($ext in $extensions) {
    $installed = az extension list --query "[?name=='$ext']" -o tsv
    if (-not $installed) {
        Write-Host "Installing $ext extension..." -ForegroundColor Yellow
        az extension add --name $ext
    }
}

# Build and push API container
Write-Host "🔨 Building API container..." -ForegroundColor Yellow
Set-Location "api"
docker build -t $RegistryName.azurecr.io/evidentfit-api:latest .
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to build API container" -ForegroundColor Red
    exit 1
}

Write-Host "📤 Pushing API container to registry..." -ForegroundColor Yellow
docker push $RegistryName.azurecr.io/evidentfit-api:latest
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to push API container" -ForegroundColor Red
    exit 1
}

# Build and push Web container
Write-Host "🔨 Building Web container..." -ForegroundColor Yellow
Set-Location "../web/evidentfit-web"
docker build -t $RegistryName.azurecr.io/evidentfit-web:latest .
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to build Web container" -ForegroundColor Red
    exit 1
}

Write-Host "📤 Pushing Web container to registry..." -ForegroundColor Yellow
docker push $RegistryName.azurecr.io/evidentfit-web:latest
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to push Web container" -ForegroundColor Red
    exit 1
}

Set-Location "../.."

# Deploy API Container App
Write-Host "🚀 Deploying API Container App..." -ForegroundColor Yellow
az containerapp create `
    --name $ApiAppName `
    --resource-group $ResourceGroupName `
    --environment $ContainerAppEnvironmentName `
    --image $RegistryName.azurecr.io/evidentfit-api:latest `
    --target-port 8000 `
    --ingress external `
    --registry-server $RegistryName.azurecr.io `
    --cpu 0.5 `
    --memory 1Gi `
    --min-replicas 1 `
    --max-replicas 3 `
    --env-vars "HOST=0.0.0.0" "PORT=8000"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to deploy API Container App" -ForegroundColor Red
    exit 1
}

# Get API URL
$apiUrl = az containerapp show --name $ApiAppName --resource-group $ResourceGroupName --query "properties.configuration.ingress.fqdn" -o tsv
$apiUrl = "https://$apiUrl"

# Deploy Web Container App
Write-Host "🚀 Deploying Web Container App..." -ForegroundColor Yellow
az containerapp create `
    --name $WebAppName `
    --resource-group $ResourceGroupName `
    --environment $ContainerAppEnvironmentName `
    --image $RegistryName.azurecr.io/evidentfit-web:latest `
    --target-port 3000 `
    --ingress external `
    --registry-server $RegistryName.azurecr.io `
    --cpu 0.5 `
    --memory 1Gi `
    --min-replicas 1 `
    --max-replicas 3 `
    --env-vars "NEXT_PUBLIC_API_BASE=$apiUrl" "NEXT_PUBLIC_DEMO_USER=demo" "NEXT_PUBLIC_DEMO_PW=demo123"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to deploy Web Container App" -ForegroundColor Red
    exit 1
}

# Get Web URL
$webUrl = az containerapp show --name $WebAppName --resource-group $ResourceGroupName --query "properties.configuration.ingress.fqdn" -o tsv
$webUrl = "https://$webUrl"

Write-Host "🎉 Deployment completed successfully!" -ForegroundColor Green
Write-Host "📱 Web Application: $webUrl" -ForegroundColor Cyan
Write-Host "🔗 API Application: $apiUrl" -ForegroundColor Cyan
Write-Host "📊 API Health Check: $apiUrl/healthz" -ForegroundColor Cyan

Write-Host "`n🔧 Next steps:" -ForegroundColor Yellow
Write-Host "1. Configure Azure Key Vault access for the Container Apps" -ForegroundColor White
Write-Host "2. Set up managed identity for secure secret access" -ForegroundColor White
Write-Host "3. Test the deployed application" -ForegroundColor White
