param([switch]$Build)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Create .venv and install requirements.lock first; see README.md' }
if ($Build -or -not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
    Push-Location -LiteralPath 'frontend'
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed (Node >=22.12 required)' }
    } finally { Pop-Location }
}
& .\.venv\Scripts\python.exe scripts/devdb.py
if ($LASTEXITCODE -ne 0) { throw 'Private PostgreSQL startup failed' }
& .\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
# Guest examples are created atomically on first visit; no password accounts needed.
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8186
