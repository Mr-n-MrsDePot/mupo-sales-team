# Live multi-agent demo (CrewAI + xAI Grok)
# Requires: Python 3.12 venv at .venv-llm, .env with XAI_API_KEY
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path .venv-llm\Scripts\python.exe)) {
    Write-Host "Creating Python 3.12 venv..."
    py -3.12 -m venv .venv-llm
    .\.venv-llm\Scripts\python.exe -m pip install --upgrade pip
    .\.venv-llm\Scripts\python.exe -m pip install -e ".[llm,dev]"
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env — set XAI_API_KEY then re-run."
    exit 1
}

$env:PYTHONPATH = ""
Write-Host "Running live CrewAI demo (email stays dry_run)..."
.\.venv-llm\Scripts\python.exe -m mupo_sales.main demo --llm
Write-Host ""
Write-Host "Dashboard:"
.\.venv-llm\Scripts\python.exe -m mupo_sales.main dashboard
