# Start the FastAPI backend on Windows (safe in OneDrive-synced folders).
# Clears any orphan process still holding the port first: uvicorn --reload spawns a
# process tree that does not always exit cleanly on Ctrl+C.
param(
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"

$pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($p in $pids) {
    Write-Host "Stopping orphan process $p on port $Port"
    # /T kills the whole tree (reloader + worker), /F forces it
    taskkill /PID $p /T /F | Out-Null
}

Set-Location $backend
& (Join-Path $backend ".venv\Scripts\Activate.ps1")
uvicorn app.main:app --reload --no-access-log --port $Port
