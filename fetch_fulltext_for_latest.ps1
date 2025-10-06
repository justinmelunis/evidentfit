# PowerShell version: Fetch full text for the latest get_papers run
#
# Usage:
#   .\fetch_fulltext_for_latest.ps1
#
# Or with options:
#   $env:NCBI_API_KEY="your_key"
#   .\fetch_fulltext_for_latest.ps1 -Limit 1000 -Concurrency 2

param(
    [int]$Limit = 0,
    [int]$Concurrency = 8,
    [switch]$Overwrite
)

$LatestJson = "data/ingest/runs/latest.json"

if (-not (Test-Path $LatestJson)) {
    Write-Error "Error: $LatestJson not found"
    Write-Host "Run get_papers pipeline first:"
    Write-Host "  python -m agents.ingest.get_papers.pipeline --mode bootstrap"
    exit 1
}

# Parse latest.json
$latest = Get-Content $LatestJson -Raw | ConvertFrom-Json
$PapersPath = $latest.papers_path
$RunId = $latest.run_id

Write-Host "==========================================`n" -ForegroundColor Cyan
Write-Host "Fetching full text for run: $RunId" -ForegroundColor Green
Write-Host "Papers: $PapersPath"
Write-Host "`n=========================================="

# Build command
$cmd = "python -m agents.ingest.get_papers.fulltext_fetcher --jsonl `"$PapersPath`" --concurrency $Concurrency"

if ($Limit -gt 0) {
    $cmd += " --limit $Limit"
}

if ($Overwrite) {
    $cmd += " --overwrite"
}

Write-Host "`nRunning: $cmd`n" -ForegroundColor Yellow

# Execute
Invoke-Expression $cmd

Write-Host "`n=========================================="
Write-Host "Full-text fetch complete!" -ForegroundColor Green
Write-Host "Manifest: data/ingest/runs/$RunId/fulltext_manifest.json"
Write-Host "Store: data/fulltext_store/"
Write-Host "==========================================" -ForegroundColor Cyan

