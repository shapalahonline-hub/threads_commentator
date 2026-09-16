# Build ThreadsCommentator.exe with PyInstaller.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File build_exe.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Test-Path ".venv")) {
    Write-Host "Creating venv..."
    python -m venv .venv
}
$py = Join-Path $here ".venv\Scripts\python.exe"

Write-Host "Installing deps..."
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r requirements.txt pyinstaller | Out-Null

Write-Host "Building (onedir, windowed)..."
& $py -m PyInstaller --noconfirm --windowed --name ThreadsCommentator `
    --collect-all playwright `
    --collect-all PySide6 `
    app.py

Write-Host ""
Write-Host "Done. Exe -> dist\ThreadsCommentator\ThreadsCommentator.exe"
Write-Host "(Uses your system Chrome; no Chromium bundled. If Chrome isn't found,"
Write-Host " run once:  .venv\Scripts\python -m playwright install chromium )"
