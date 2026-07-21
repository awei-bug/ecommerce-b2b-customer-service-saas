@echo off
REM Local DEV API (manager.py). ASCII only.
REM Path: <repo>\deploy\win\  ->  <repo>\flask_shop
setlocal EnableExtensions

cd /d "%~dp0..\..\flask_shop"
if errorlevel 1 (
  echo [ERR] Cannot cd to flask_shop
  exit /b 1
)

echo [INFO] Working dir: %CD%

if not exist ".venv\Scripts\python.exe" (
  echo [ERR] .venv not found under %CD%
  exit /b 1
)

set "FLASK_CONFIG=develop"
echo [INFO] Starting DEV server http://127.0.0.1:5000  FLASK_CONFIG=%FLASK_CONFIG%
.venv\Scripts\python.exe manager.py
