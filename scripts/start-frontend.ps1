# Start the frontend dev server on Windows (safe in OneDrive-synced folders).
# Wipes .next with Remove-Item -Force, which handles OneDrive placeholder files silently
# (plain `rmdir /s /q` fails or prompts on them).
param(
    [int]$Port = 3000
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"

$pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($p in $pids) {
    Write-Host "Stopping orphan process $p on port $Port"
    taskkill /PID $p /T /F | Out-Null
}

$next = Join-Path $frontend ".next"
if (Test-Path $next) {
    Remove-Item -LiteralPath $next -Recurse -Force -ErrorAction SilentlyContinue
}

Set-Location $frontend
npm run dev -- --port $Port
