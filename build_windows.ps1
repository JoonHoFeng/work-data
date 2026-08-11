# Worklog Windows build (PowerShell) - safer encoding than .bat
# Usage: Right-click -> Run with PowerShell
#    or: powershell -ExecutionPolicy Bypass -File .\build_windows.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "========================================"
Write-Host "  Worklog - Windows build (PyInstaller)"
Write-Host "========================================"
Write-Host ""
Write-Host "Output: dist\Worklog\Worklog.exe"
Write-Host ""

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[ERROR] python not found."
    Write-Host "Install Python 3.9+ and check 'Add python.exe to PATH'."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[1/4] $($py.Source)"
& python --version

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[2/4] Creating venv..."
    & python -m venv .venv
} else {
    Write-Host "[2/4] venv already exists."
}

Write-Host "[3/4] Installing dependencies..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install "pyinstaller>=6.0"

if (Test-Path "scripts\patch_streamlit_zh.py") {
    Write-Host "Patching Streamlit menu (optional)..."
    & .\.venv\Scripts\python.exe scripts\patch_streamlit_zh.py
}

Write-Host "[4/4] Building..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm worklog.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] PyInstaller failed."
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path "dist\Worklog\Worklog.exe")) {
    Write-Host "[ERROR] Worklog.exe not found."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "BUILD OK -> dist\Worklog\Worklog.exe"
Write-Host "Copy the whole dist\Worklog folder to distribute."
if (Test-Path "dist\Worklog") {
    Start-Process explorer.exe -ArgumentList (Resolve-Path "dist\Worklog")
}
Read-Host "Press Enter to exit"
