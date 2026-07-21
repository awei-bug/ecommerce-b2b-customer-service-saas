@echo off
REM Backup local MySQL using flask_shop\.env (Windows).
REM Requires mysqldump in PATH, or set MYSQL_BIN to MySQL\bin folder.
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0..\.."
cd /d "%ROOT%"
set "BACKUP_DIR=%ROOT%\deploy\backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

set "ENV_FILE=%ROOT%\flask_shop\.env"
set "MYSQL_HOST=127.0.0.1"
set "MYSQL_PORT=3306"
set "MYSQL_USERNAME=root"
set "MYSQL_PASSWORD="
set "MYSQL_DB=flask_shop_saas"

if exist "%ENV_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    set "K=%%A"
    set "V=%%B"
    if /i "!K!"=="MYSQL_HOST" set "MYSQL_HOST=!V!"
    if /i "!K!"=="MYSQL_PORT" set "MYSQL_PORT=!V!"
    if /i "!K!"=="MYSQL_USERNAME" set "MYSQL_USERNAME=!V!"
    if /i "!K!"=="MYSQL_PASSWORD" set "MYSQL_PASSWORD=!V!"
    if /i "!K!"=="MYSQL_DB" set "MYSQL_DB=!V!"
  )
)

set "DUMP="
if defined MYSQL_BIN if exist "%MYSQL_BIN%\mysqldump.exe" set "DUMP=%MYSQL_BIN%\mysqldump.exe"
if not defined DUMP if exist "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" set "DUMP=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"
if not defined DUMP if exist "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe" set "DUMP=C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe"
if not defined DUMP if exist "C:\Program Files\MySQL\MySQL Server 5.7\bin\mysqldump.exe" set "DUMP=C:\Program Files\MySQL\MySQL Server 5.7\bin\mysqldump.exe"
if not defined DUMP (
  where mysqldump >nul 2>nul
  if not errorlevel 1 set "DUMP=mysqldump"
)

if not defined DUMP (
  echo [ERR] mysqldump not found.
  echo Install MySQL Shell/Client tools, or:
  echo   set MYSQL_BIN=C:\Path\To\MySQL\bin
  echo   deploy\win\backup_mysql.bat
  echo Or Docker: bash deploy/backup_mysql.sh
  exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "FILE=%BACKUP_DIR%\flask_shop_%MYSQL_DB%_%STAMP%.sql"

echo [INFO] Dump %MYSQL_USERNAME%@%MYSQL_HOST%:%MYSQL_PORT%/%MYSQL_DB%
echo [INFO] Tool: %DUMP%
echo [INFO] Out:  %FILE%

"%DUMP%" -h%MYSQL_HOST% -P%MYSQL_PORT% -u%MYSQL_USERNAME% -p%MYSQL_PASSWORD% --single-transaction --routines --triggers %MYSQL_DB% > "%FILE%"
if errorlevel 1 (
  echo [ERR] mysqldump failed
  exit /b 1
)

for %%Z in ("%FILE%") do echo [OK] size=%%~zZ bytes
powershell -NoProfile -Command "Compress-Archive -Path '%FILE%' -DestinationPath '%FILE%.zip' -Force" 1>nul 2>nul
if exist "%FILE%.zip" echo [OK] zip=%FILE%.zip

echo [INFO] Done.
exit /b 0
