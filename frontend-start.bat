@echo off
rem ---------------------------------------------------------------------------
rem  frontend-start.bat - check, set up and start the Next.js frontend (Windows).
rem
rem  Usage:  frontend-start.bat [port]        (default port 3000)
rem
rem  Steps:
rem   1. Node.js 20 or later and npm are installed.
rem   2. Dependencies match package-lock.json (npm ci when the lock changes).
rem   3. The backend answers on BACKEND_URL/healthz (warning only - start
rem      backend-start.bat first, in another window).
rem   4. Any orphan process holding the port is stopped.
rem   5. .next is wiped with PowerShell Remove-Item -Force (safe for OneDrive
rem      placeholder files, unlike rmdir /q).
rem   6. npm run dev starts.
rem
rem  Dev defaults (only applied when not already set in this shell, this run only):
rem     BACKEND_URL=http://localhost:8000
rem     NEXT_PUBLIC_DEV_AUTH=true                 (dev principal picker, D-21; dev only)
rem     NEXT_PUBLIC_FEATURE_SCREENING_RUNS=true   (screening-run screens, D-25)
rem  Nothing is written to frontend\.env.local, so production builds stay unaffected.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions EnableDelayedExpansion

set "PORT=%~1"
if "%PORT%"=="" set "PORT=3000"

set "ROOT=%~dp0"
set "FRONTEND=%ROOT%frontend"
set "LOCK=%FRONTEND%\package-lock.json"
set "STAMP=%FRONTEND%\node_modules\.lock-stamp"

echo.
echo === HR Screening frontend: pre-checks ===

if not exist "%FRONTEND%\package.json" (
    echo [x] frontend folder not found at "%FRONTEND%". Run this file from the repo root.
    goto :fail
)

rem --- 1. Node.js 20+ and npm ----------------------------------------------
where node >nul 2>&1 || (
    echo [x] Node.js is not installed or not on PATH. Install Node.js 20 LTS or later
    echo     from https://nodejs.org/ and run this again.
    goto :fail
)
set "NODEMAJOR="
for /f "tokens=1 delims=v." %%m in ('node -v') do set "NODEMAJOR=%%m"
if not defined NODEMAJOR (
    echo [x] Could not read the Node.js version.
    goto :fail
)
if !NODEMAJOR! LSS 20 (
    echo [x] Node.js 20 or later is required; found v!NODEMAJOR!. Upgrade from https://nodejs.org/
    goto :fail
)
where npm >nul 2>&1 || (
    echo [x] npm is not on PATH. Reinstall Node.js ^(npm ships with it^).
    goto :fail
)
for /f "delims=" %%v in ('node -v') do set "NODEVER=%%v"
echo [ok] Node.js !NODEVER! and npm found

rem --- 2. dependencies ------------------------------------------------------
set "NEED_INSTALL=1"
if exist "%STAMP%" (
    fc /b "%LOCK%" "%STAMP%" >nul 2>&1 && set "NEED_INSTALL=0"
)
if "%NEED_INSTALL%"=="1" (
    echo [..] Installing frontend dependencies ^(npm ci^)
    pushd "%FRONTEND%"
    call npm ci
    if errorlevel 1 ( popd & echo [x] npm ci failed. & goto :fail )
    popd
    copy /y "%LOCK%" "%STAMP%" >nul
)
echo [ok] Dependencies match package-lock.json

rem --- dev defaults (this shell only) ---------------------------------------
if not defined BACKEND_URL set "BACKEND_URL=http://localhost:8000"
if not defined NEXT_PUBLIC_DEV_AUTH set "NEXT_PUBLIC_DEV_AUTH=true"
if not defined NEXT_PUBLIC_FEATURE_SCREENING_RUNS set "NEXT_PUBLIC_FEATURE_SCREENING_RUNS=true"

rem --- 3. backend reachable (warning only) ----------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '%BACKEND_URL%/healthz'; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo [!] Backend is not answering at %BACKEND_URL%/healthz.
    echo     The UI will start, but API calls will fail until you run backend-start.bat.
) else (
    echo [ok] Backend is up at %BACKEND_URL%
)

rem --- 4. free the port -----------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($i in $p) { Write-Host ('[..] Stopping orphan process ' + $i + ' on port %PORT%'); taskkill /PID $i /T /F | Out-Null }"
echo [ok] Port %PORT% is free

rem --- 5. wipe .next (OneDrive-safe) ----------------------------------------
if exist "%FRONTEND%\.next" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Remove-Item -LiteralPath '%FRONTEND%\.next' -Recurse -Force -ErrorAction SilentlyContinue"
)
echo [ok] .next cache cleared

rem --- 6. start ------------------------------------------------------------
echo.
echo === Starting frontend on http://localhost:%PORT%  ^(Ctrl+C to stop^) ===
echo     backend=%BACKEND_URL%  dev picker=%NEXT_PUBLIC_DEV_AUTH%  screening runs=%NEXT_PUBLIC_FEATURE_SCREENING_RUNS%
echo.
pushd "%FRONTEND%"
call npm run dev -- --port %PORT%
set "RC=%ERRORLEVEL%"
popd
endlocal & exit /b %RC%

:fail
echo.
echo Frontend NOT started. Fix the item marked [x] above and run frontend-start.bat again.
pause
endlocal & exit /b 1
