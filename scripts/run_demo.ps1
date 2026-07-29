# MUPO Sales Team — quick local demo (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
python -m pip install -q -e ".[dev]"
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example — add XAI_API_KEY for LLM workflows."
}

python -m mupo_sales.main demo
python -m mupo_sales.main dashboard
