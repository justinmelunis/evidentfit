# Update EvidentFit API Container App with new image
# This script updates the existing API container app with the latest image from GitLab CI

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$true)]
    [string]$ApiAppName = "evidentfit-api",
    
    [Parameter(Mandatory=$false)]
    [string]$ImageTag = "latest"
)

Write-Host "🚀 Updating EvidentFit API Container App..." -ForegroundColor Green

# Check if Azure CLI is logged in
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

# Check if container app exists
Write-Host "🔍 Checking if container app exists..." -ForegroundColor Yellow
$appExists = az containerapp show --name $ApiAppName --resource-group $ResourceGroupName --query "name" -o tsv 2>$null
if (-not $appExists) {
    Write-Host "❌ Container app '$ApiAppName' not found in resource group '$ResourceGroupName'" -ForegroundColor Red
    Write-Host "Please create the container app first using the deployment scripts" -ForegroundColor Yellow
    exit 1
}

# Update the container app with new image
Write-Host "🔄 Updating API container app with new image..." -ForegroundColor Yellow
$imageName = "justinmelunis/evidentfit-api:$ImageTag"

az containerapp update `
    --name $ApiAppName `
    --resource-group $ResourceGroupName `
    --image $imageName

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to update API container app" -ForegroundColor Red
    exit 1
}

# Get updated API URL
$apiUrl = az containerapp show --name $ApiAppName --resource-group $ResourceGroupName --query "properties.configuration.ingress.fqdn" -o tsv
$apiUrl = "https://$apiUrl"

Write-Host "✅ API container app updated successfully!" -ForegroundColor Green
Write-Host "🔗 API Application: $apiUrl" -ForegroundColor Cyan
Write-Host "📊 API Health Check: $apiUrl/healthz" -ForegroundColor Cyan
Write-Host "📚 API Documentation: $apiUrl/docs" -ForegroundColor Cyan

Write-Host "`n🔧 Testing the updated API..." -ForegroundColor Yellow
Write-Host "You can test the API endpoints:" -ForegroundColor White
Write-Host "  - Health: $apiUrl/healthz" -ForegroundColor White
Write-Host "  - Summaries: $apiUrl/summaries/creatine" -ForegroundColor White
Write-Host "  - Stack: POST $apiUrl/stack" -ForegroundColor White

