@echo off
REM Build vue_shop + mall for Nginx static deploy (Windows)
setlocal EnableExtensions
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
set "ROOT=%CD%"
echo [INFO] ROOT=%ROOT%

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERR] npm not found in PATH
  exit /b 1
)

echo [INFO] build vue_shop ...
cd /d "%ROOT%\vue_shop"
if not exist node_modules (
  call npm install
  if errorlevel 1 exit /b 1
)
set "VUE_APP_API_BASE="
set "NODE_ENV=production"
call npm run build
if errorlevel 1 (
  echo [ERR] vue_shop build failed
  exit /b 1
)

echo [INFO] build mall ...
cd /d "%ROOT%\mall"
if not exist node_modules (
  call npm install
  if errorlevel 1 exit /b 1
)
call npm run build
if errorlevel 1 (
  echo [ERR] mall build failed
  exit /b 1
)

echo [OK] vue_shop\dist  and  mall\dist  ready
exit /b 0
