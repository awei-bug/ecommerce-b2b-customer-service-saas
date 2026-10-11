@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "ROOT=%CD%"
echo [sample] ROOT=%ROOT%

if not exist "%ROOT%\flask_shop\.venv\Scripts\python.exe" (
  echo [ERR] flask_shop\.venv not found
  exit /b 1
)

if not exist "%ROOT%\mall\dist\index.html" (
  echo [sample] building mall...
  cd /d "%ROOT%\mall"
  call npm run build
  if errorlevel 1 exit /b 1
)

if not exist "%ROOT%\vue_shop\dist\index.html" (
  echo [sample] building vue_shop with /admin/ publicPath...
  cd /d "%ROOT%\vue_shop"
  set "VUE_APP_PUBLIC_PATH=/admin/"
  call npm run build
  if errorlevel 1 exit /b 1
) else (
  findstr /C:"/admin/" "%ROOT%\vue_shop\dist\index.html" >nul
  if errorlevel 1 (
    echo [sample] rebuilding vue_shop for /admin/ base...
    cd /d "%ROOT%\vue_shop"
    set "VUE_APP_PUBLIC_PATH=/admin/"
    call npm run build
    if errorlevel 1 exit /b 1
  )
)

cd /d "%ROOT%\flask_shop"
echo [sample] starting sample shop on http://127.0.0.1:18080 ...
".venv\Scripts\python.exe" "%ROOT%\deploy\win\sample_shop_server.py"