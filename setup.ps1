# One-shot setup + launch for GitPulse on Windows.
# Usage: .\setup.ps1

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$pythonBin = $null
foreach ($candidate in @("python", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pythonBin = $candidate
        break
    }
}

if (-not $pythonBin) {
    Write-Error "No python interpreter found on PATH. Install Python 3.10+ first."
    exit 1
}

Write-Host "Using interpreter: $(& $pythonBin --version)"

if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    & $pythonBin -m venv venv
}

$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

Write-Host "Installing dependencies..."
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r requirements.txt

Write-Host "Launching GitPulse..."
& $venvPython start.py
