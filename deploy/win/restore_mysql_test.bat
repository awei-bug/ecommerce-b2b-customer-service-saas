@echo off
setlocal
if "%~1"=="" (
  echo Usage: %~nx0 path\to\trusted-backup.sql
  exit /b 1
)
cd /d "%~dp0..\.."
"flask_shop\.venv\Scripts\python.exe" "deploy\win\restore_mysql_local.py" "%~1"
exit /b %errorlevel%
