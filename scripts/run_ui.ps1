# Launch MUPO Streamlit ops UI
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$py = if (Test-Path .venv-llm\Scripts\python.exe) {
    ".venv-llm\Scripts\python.exe"
} elseif (Test-Path .venv\Scripts\python.exe) {
    ".venv\Scripts\python.exe"
} else {
    "python"
}

& $py -m pip install -q streamlit
Write-Host "Opening http://localhost:8501 ..."
& $py -m mupo_sales.main ui
