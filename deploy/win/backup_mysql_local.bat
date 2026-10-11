@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "OUT=%ROOT%\deploy\backups"
if not exist "%OUT%" mkdir "%OUT%"

set "MYSQL_HOST=127.0.0.1"
set "MYSQL_PORT=3307"
set "MYSQL_USER=root"
set "MYSQL_PWD=123456"
set "MYSQL_DB=flask_shop"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set "FILE=%OUT%\flask_shop_%TS%.sql"

where mysqldump >nul 2>nul
if errorlevel 1 (
  echo [INFO] mysqldump not in PATH, use Python backup...
  "%ROOT%\flask_shop\.venv\Scripts\python.exe" "%ROOT%\deploy\win\backup_mysql_local.py"
  exit /b %errorlevel%
)

echo [INFO] dumping %MYSQL_DB% to %FILE%
mysqldump -h%MYSQL_HOST% -P%MYSQL_PORT% -u%MYSQL_USER% -p%MYSQL_PWD% --routines --events --single-transaction %MYSQL_DB% > "%FILE%"
if errorlevel 1 (
  echo [ERR] mysqldump failed, try Python...
  "%ROOT%\flask_shop\.venv\Scripts\python.exe" "%ROOT%\deploy\win\backup_mysql_local.py"
  exit /b %errorlevel%
)
echo [OK] %FILE%
exit /b 0
