@echo off
REM Start API in production-like mode (Windows). ASCII only.
setlocal EnableExtensions

cd /d "%~dp0..\..\flask_shop"
if errorlevel 1 (
  echo [ERR] Cannot cd to flask_shop from %~dp0
  exit /b 1
)
echo [INFO] Working dir: %CD%

if not exist ".venv\Scripts\python.exe" (
  echo [ERR] .venv not found under %CD%
  exit /b 1
)

REM --- production-like defaults (manual pay path) ---
set "FLASK_CONFIG=product"
set "ALLOW_MOCK_PAY=0"
set "PAY_DEFAULT_CHANNEL=mock"
set "SMS_DEV_MODE=0"
set "PRIVATE_DEPLOY=1"
set "ORDER_PENDING_TIMEOUT_MINUTES=1440"

REM Prefer secrets from deploy\.env.prod if present (simple parser)
set "ENVPROD=%~dp0..\.env.prod"
if exist "%ENVPROD%" (
  echo [INFO] Loading keys from %ENVPROD%
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENVPROD%") do (
    if /I "%%A"=="SECRET_KEY" set "SECRET_KEY=%%B"
    if /I "%%A"=="PLATFORM_BOOTSTRAP_KEY" set "PLATFORM_BOOTSTRAP_KEY=%%B"
    if /I "%%A"=="CORS_ORIGINS" set "CORS_ORIGINS=%%B"
    if /I "%%A"=="PUBLIC_BASE_URL" set "PUBLIC_BASE_URL=%%B"
    if /I "%%A"=="DATABASE_URL" set "DATABASE_URL=%%B"
  )
)

if not defined CORS_ORIGINS set "CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:18080"
if not defined PUBLIC_BASE_URL set "PUBLIC_BASE_URL=http://127.0.0.1:18080"

REM Keep local sqlite if already configured in flask_shop\.env (python-dotenv)
REM For pure product MySQL, set DATABASE_URL or MYSQL_* in environment.

.venv\Scripts\python.exe -c "import waitress" 1>nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing waitress ...
  .venv\Scripts\pip.exe install waitress
  if errorlevel 1 exit /b 1
)

echo [INFO] Preflight product config ...
.venv\Scripts\python.exe -c "from flask_shop import create_app; create_app('product'); print('config_ok')"
if errorlevel 1 (
  echo [ERR] product config validation failed. Check SECRET_KEY / PLATFORM_BOOTSTRAP_KEY / CORS.
  echo      Generate: python -c "import secrets;print(secrets.token_urlsafe(48))"
  exit /b 1
)

echo [INFO] Starting Waitress http://127.0.0.1:5000  FLASK_CONFIG=%FLASK_CONFIG% ALLOW_MOCK_PAY=%ALLOW_MOCK_PAY%
.venv\Scripts\python.exe -c "from waitress import serve; from wsgi import app; serve(app, host='127.0.0.1', port=5000, threads=8)"
if errorlevel 1 (
  echo [ERR] Server exited with error.
  exit /b 1
)
