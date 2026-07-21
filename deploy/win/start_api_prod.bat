@echo off
REM Start API in production-like mode (Windows). ASCII only.
REM This file lives in:  <repo>\deploy\win\
REM Project venv lives in: <repo>\flask_shop\.venv
setlocal EnableExtensions

REM Go to flask_shop (two levels up from deploy\win, then flask_shop)
cd /d "%~dp0..\..\flask_shop"
if errorlevel 1 (
  echo [ERR] Cannot cd to flask_shop from %~dp0
  exit /b 1
)

echo [INFO] Working dir: %CD%

if not exist ".venv\Scripts\python.exe" (
  echo [ERR] .venv not found under %CD%
  echo Create it with:
  echo   cd /d %CD%
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  echo   .venv\Scripts\pip install waitress
  exit /b 1
)

set "FLASK_CONFIG=product"
set "ALLOW_MOCK_PAY=0"
set "PAY_DEFAULT_CHANNEL=mock"
set "SMS_DEV_MODE=0"

if not defined SECRET_KEY (
  if exist ".env" (
    echo [INFO] SECRET_KEY not in shell; python will load flask_shop\.env
  ) else (
    echo [WARN] No SECRET_KEY and no .env - product mode may refuse to start
  )
)

.venv\Scripts\python.exe -c "import waitress" 1>nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing waitress ...
  .venv\Scripts\pip.exe install waitress
  if errorlevel 1 (
    echo [ERR] pip install waitress failed
    exit /b 1
  )
)

echo [INFO] Starting Waitress http://127.0.0.1:5000  FLASK_CONFIG=%FLASK_CONFIG%
.venv\Scripts\python.exe -c "from waitress import serve; from wsgi import app; serve(app, host='127.0.0.1', port=5000, threads=8)"
if errorlevel 1 (
  echo [ERR] Server exited with error. Check SECRET_KEY in .env and MySQL.
  exit /b 1
)
