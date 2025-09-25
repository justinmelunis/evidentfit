# Test Docker setup for EvidentFit
# This script tests the Docker containers locally

param(
    [switch]$Build,
    [switch]$Run,
    [switch]$Clean
)

Write-Host "🐳 EvidentFit Docker Test Script" -ForegroundColor Green

if ($Build) {
    Write-Host "🔨 Building Docker containers..." -ForegroundColor Yellow
    
    # Check if Docker is running
    try {
        docker version | Out-Null
        Write-Host "✅ Docker is running" -ForegroundColor Green
    } catch {
        Write-Host "❌ Docker is not running. Please start Docker Desktop." -ForegroundColor Red
        exit 1
    }
    
    # Build API container
    Write-Host "Building API container..." -ForegroundColor Yellow
    docker build -t evidentfit-api:local -f api/Dockerfile .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to build API container" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ API container built successfully" -ForegroundColor Green
    
    # Build Web container
    Write-Host "Building Web container..." -ForegroundColor Yellow
    docker build -t evidentfit-web:local -f web/evidentfit-web/Dockerfile ./web/evidentfit-web
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to build Web container" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Web container built successfully" -ForegroundColor Green
}

if ($Run) {
    Write-Host "🚀 Starting containers with Docker Compose..." -ForegroundColor Yellow
    
    # Start services
    docker-compose up -d
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to start containers" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Containers started successfully" -ForegroundColor Green
    Write-Host "📱 Web App: http://localhost:3000" -ForegroundColor Cyan
    Write-Host "🔗 API: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "📊 API Health: http://localhost:8000/healthz" -ForegroundColor Cyan
    Write-Host "📚 API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
    
    Write-Host "`n🔍 To view logs:" -ForegroundColor Yellow
    Write-Host "docker-compose logs -f" -ForegroundColor White
    
    Write-Host "`n🛑 To stop containers:" -ForegroundColor Yellow
    Write-Host "docker-compose down" -ForegroundColor White
}

if ($Clean) {
    Write-Host "🧹 Cleaning up Docker resources..." -ForegroundColor Yellow
    
    # Stop containers
    docker-compose down
    
    # Remove images
    docker rmi evidentfit-api:local -f
    docker rmi evidentfit-web:local -f
    
    # Clean up unused resources
    docker system prune -f
    
    Write-Host "✅ Cleanup completed" -ForegroundColor Green
}

if (-not $Build -and -not $Run -and -not $Clean) {
    Write-Host "Usage: .\scripts\test-docker.ps1 [options]" -ForegroundColor Yellow
    Write-Host "Options:" -ForegroundColor White
    Write-Host "  -Build    Build Docker containers" -ForegroundColor White
    Write-Host "  -Run      Start containers with docker-compose" -ForegroundColor White
    Write-Host "  -Clean    Clean up Docker resources" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\scripts\test-docker.ps1 -Build -Run" -ForegroundColor White
    Write-Host "  .\scripts\test-docker.ps1 -Clean" -ForegroundColor White
}
