$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run installation steps from README.md first.' }
& .venv\Scripts\python.exe -X utf8 scripts\setup_local.py
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed.' }
& .venv\Scripts\python.exe -X utf8 scripts\start_local.py
if ($LASTEXITCODE -ne 0) { throw 'Application startup failed.' }
