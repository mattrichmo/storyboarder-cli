$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
& .\.venv\Scripts\python.exe -m pip install .
if ($LASTEXITCODE -ne 0) { throw "Installation failed." }
Write-Host "Installed. Start with .\.venv\Scripts\storyboarder.exe ui --workspace .\stories"
