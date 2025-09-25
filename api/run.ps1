# Windows PowerShell script to run the EvidentFit API
Set-Location $PSScriptRoot

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Load environment variables
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

# Start the server
Write-Host "Starting EvidentFit API server..."
Write-Host "API will be available at: http://localhost:8000"
Write-Host "API docs at: http://localhost:8000/docs"
Write-Host "Health check at: http://localhost:8000/healthz"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server"
Write-Host ""

& .\.venv\Scripts\python.exe -m uvicorn main:api --host 0.0.0.0 --port 8000 --reload
