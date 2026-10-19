# Starts Orion on Windows: the backend API and the frontend dev server, each in its own window.
# The Windows counterpart of start.sh. Postgres is the local PostgreSQL service (backend/.env DATABASE_URL), not Docker;
# extraction runs in-process (EXTRACTION_EXECUTOR="background"), so Redis is not needed. Ollama must be running.
#
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }

Write-Host "Starting Orion World State Engine" -ForegroundColor Cyan

# ---- prerequisites
if (-not (Test-Path "$root\backend\.venv\Scripts\uvicorn.exe")) { Fail "backend\.venv is missing: python -m venv backend\.venv; backend\.venv\Scripts\pip install -r backend\requirements.txt" }
if (-not (Test-Path "$root\backend\.env")) { Fail "backend\.env is missing: copy backend\.env.example backend\.env" }
if (-not (Test-Path "$root\extractor\.venv\Scripts\python.exe")) { Fail "extractor\.venv is missing: extraction needs it (see extractor\requirements.txt)" }
if (-not (Test-Path "$root\Frontend\node_modules")) { Fail "Frontend\node_modules is missing: cd Frontend; npm install" }
$pg = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pg -or $pg.Status -ne "Running") { Fail "The PostgreSQL service is not running (Services: postgresql-x64-16)" }
try { $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 } catch { Fail "Ollama is not running on 127.0.0.1:11434" }
$models = $tags.models.name
if (-not ($models -match "^nuextract2-4b")) { Fail "Ollama has no nuextract2-4b model (extraction): see extractor\requirements.txt" }
if (-not ($models -match "^qwen3.5:9b")) { Write-Host "Ollama has no qwen3.5:9b: the chat will not answer and extraction keeps only title facts (ollama pull qwen3.5:9b)" -ForegroundColor Yellow }
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { Fail "Port 8000 is in use (an API already running?)" }

# ---- environment: caches and temp on D: (C: is nearly full), UTF-8 for the extractor subprocess
$env:PYTHONUTF8 = "1"
foreach ($kv in @{ HF_HOME = "D:\DevCache\huggingface"; TORCH_HOME = "D:\DevCache\torch"; TMP = "D:\DevCache\tmp"; TEMP = "D:\DevCache\tmp" }.GetEnumerator()) {
    if (Test-Path (Split-Path $kv.Value -Qualifier)) { Set-Item "env:$($kv.Key)" $kv.Value }
}

# ---- database schema (no-op when already at head)
Push-Location "$root\backend"
$env:PYTHONPATH = "."
& .\.venv\Scripts\alembic.exe upgrade head
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "alembic upgrade failed: check DATABASE_URL in backend\.env" }
Pop-Location

# ---- API and frontend, one window each
Start-Process powershell -WorkingDirectory "$root\backend" -ArgumentList "-NoExit", "-Command",
    "`$env:PYTHONPATH='.'; .\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -WorkingDirectory "$root\Frontend" -ArgumentList "-NoExit", "-Command",
    "`$env:VITE_API_BASE_URL='http://127.0.0.1:8000/api/v1'; npx vite --host 127.0.0.1 --port 5173"

Write-Host "Frontend: http://127.0.0.1:5173   API: http://127.0.0.1:8000/api/v1/docs" -ForegroundColor Green
Write-Host "Log in as demo@example.com / orion-demo (seed: backend\.venv\Scripts\python.exe backend\scripts\seed_demo_world.py)"
Write-Host "The chat model and the extractor don't fit on the GPU together: let a chapter finish before chatting." -ForegroundColor Yellow
Write-Host "Close the two windows to stop."
