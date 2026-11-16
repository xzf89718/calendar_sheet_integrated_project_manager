# Build the API reference HTML with Sphinx.
# Usage: pwsh scripts/build_docs.ps1
# Creates .docs-venv at the repo root on first run.
$ErrorActionPreference = "Stop"

$root  = Split-Path -Parent $PSScriptRoot
$venv  = Join-Path $root ".docs-venv"
$py    = Join-Path $venv "Scripts/python.exe"
$html  = Join-Path $root "docs/build/html"

if (-not (Test-Path $py)) {
    Write-Host "creating docs venv..."
    python -m venv $venv
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r (Join-Path $root "requirements-docs.txt")
}

Write-Host "checking docstrings..."
& $py (Join-Path $root "scripts/check_docs.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "docstring check failed; fix the issues above first" -ForegroundColor Red
    exit 1
}

Write-Host "building html..."
& $py -m sphinx -b html -q (Join-Path $root "docs") $html
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "done: docs/build/html/index.html"
Start-Process (Join-Path $html "index.html")
