$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .venv\Scripts\python.exe -X utf8 scripts\stop_local.py
if ($LASTEXITCODE -ne 0) { throw 'Stop failed; inspect the output.' }
