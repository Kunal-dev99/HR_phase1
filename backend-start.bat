@echo off
rem ---------------------------------------------------------------------------
rem  backend-start.bat - check, set up and start the FastAPI backend (Windows).
rem
rem  Usage:  backend-start.bat [port]        (default port 8000)
rem
rem  Steps:
rem   1. Python 3.12 is installed (py launcher or python on PATH).
rem   2. backend\.env exists and DATABASE_URL is filled in.
rem   3. backend\.venv exists (created on first run).
rem   4. Dependencies match requirements-dev.lock (re-installed when the lock changes).
rem   5. Settings are valid, DATABASE_URL is a *_copy / *_test database (D-03),
rem      and PostgreSQL accepts a connection.
rem   6. Migrations are at head (alembic upgrade head - additive, D-01).
rem   7. Any orphan process holding the port is stopped (uvicorn --reload leaves trees).
rem   8. uvicorn starts with --reload and --no-access-log.
rem
rem  Dev defaults (only applied when not already set in this shell; they override
rem  backend\.env for this run only):
rem     FEATURE_SCREENING_RUNS=true   AUTH_MODE=dev_header   HR_SYSTEM_ADAPTER=mock
rem  To run with the MVP UI switched off:  set FEATURE_SCREENING_RUNS=false
rem ---------------------------------------------------------------------------
setlocal EnableExtensions EnableDelayedExpansion

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"
set "LOCK=%BACKEND%\requirements-dev.lock"
set "STAMP=%BACKEND%\.venv\.lock-stamp"

echo.
echo === HR Screening backend: pre-checks ===

if not exist "%BACKEND%\pyproject.toml" (
    echo [x] backend folder not found at "%BACKEND%". Run this file from the repo root.
    goto :fail
)

rem --- 1. Python 3.12 -------------------------------------------------------
set "PY="
py -3.12 --version >nul 2>&1 && set "PY=py -3.12"
if not defined PY (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    if "!PYVER:~0,5!"=="3.12." set "PY=python"
)
if not defined PY (
    echo [x] Python 3.12 is required. Install it from https://www.python.org/downloads/
    echo     ^(tick "Add python.exe to PATH" or use the py launcher^), then run this again.
    goto :fail
)
echo [ok] Python 3.12 found ^(%PY%^)

rem --- 2. backend\.env ------------------------------------------------------
if not exist "%BACKEND%\.env" (
    copy /y "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
    echo [x] backend\.env did not exist, so it was created from .env.example.
    echo     Open backend\.env, set DATABASE_URL to your database COPY, e.g.
    echo       postgresql+asyncpg://hr_app:YOUR_PASSWORD@localhost:5432/hr_phase1_dev_copy
    echo     then run this again. The database name must end in _copy or _test.
    goto :fail
)
findstr /c:"<password>" "%BACKEND%\.env" >nul && (
    echo [x] backend\.env still contains the ^<user^>/^<password^> placeholders in DATABASE_URL.
    echo     Edit it and run this again.
    goto :fail
)
echo [ok] backend\.env present

rem --- 3. virtual environment ----------------------------------------------
if not exist "%VENV_PY%" (
    echo [..] Creating virtual environment backend\.venv
    %PY% -m venv "%BACKEND%\.venv" || ( echo [x] Could not create the virtual environment. & goto :fail )
    if exist "%STAMP%" del /q "%STAMP%"
)
echo [ok] Virtual environment ready

rem --- 4. dependencies ------------------------------------------------------
set "NEED_INSTALL=1"
if exist "%STAMP%" (
    fc /b "%LOCK%" "%STAMP%" >nul 2>&1 && set "NEED_INSTALL=0"
)
if "%NEED_INSTALL%"=="1" (
    echo [..] Installing backend dependencies from requirements-dev.lock
    "%VENV_PY%" -m pip install --upgrade pip >nul || ( echo [x] pip upgrade failed. & goto :fail )
    "%VENV_PY%" -m pip install -r "%LOCK%" || ( echo [x] Dependency install failed. & goto :fail )
    "%VENV_PY%" -m pip install --no-deps -e "%BACKEND%" || ( echo [x] Installing the backend package failed. & goto :fail )
    copy /y "%LOCK%" "%STAMP%" >nul
)
echo [ok] Dependencies match requirements-dev.lock

rem --- dev defaults (this shell only) ---------------------------------------
if not defined FEATURE_SCREENING_RUNS set "FEATURE_SCREENING_RUNS=true"
if not defined AUTH_MODE set "AUTH_MODE=dev_header"
if not defined HR_SYSTEM_ADAPTER set "HR_SYSTEM_ADAPTER=mock"

rem --- 5. settings, database copy guard, PostgreSQL connection -------------
pushd "%BACKEND%"
"%VENV_PY%" scripts\dev_precheck.py
if errorlevel 1 (
    popd
    echo     Is PostgreSQL running? Does the database in DATABASE_URL exist? Create it with e.g.
    echo       psql -U postgres -c "CREATE DATABASE hr_phase1_dev_copy OWNER hr_app;"
    goto :fail
)

rem --- 6. migrations --------------------------------------------------------
echo [..] Applying database migrations ^(alembic upgrade head^)
"%VENV_PY%" -m alembic upgrade head || ( popd & echo [x] Migration failed. & goto :fail )
for /f "delims=" %%r in ('"%VENV_PY%" -m alembic current 2^>nul') do set "REV=%%r"
echo [ok] Database at revision: !REV!
popd

rem --- 7. free the port -----------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($i in $p) { Write-Host ('[..] Stopping orphan process ' + $i + ' on port %PORT%'); taskkill /PID $i /T /F | Out-Null }"
echo [ok] Port %PORT% is free

rem --- 8. start ------------------------------------------------------------
echo.
echo === Starting backend on http://localhost:%PORT%  ^(Ctrl+C to stop^) ===
echo     screening runs=%FEATURE_SCREENING_RUNS%  auth=%AUTH_MODE%  hr adapter=%HR_SYSTEM_ADAPTER%
echo     health check: http://localhost:%PORT%/healthz
echo.
pushd "%BACKEND%"
"%VENV_PY%" -m uvicorn app.main:app --reload --no-access-log --port %PORT%
set "RC=%ERRORLEVEL%"
popd
endlocal & exit /b %RC%

:fail
echo.
echo Backend NOT started. Fix the item marked [x] above and run backend-start.bat again.
pause
endlocal & exit /b 1
