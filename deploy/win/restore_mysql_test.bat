@echo off
REM Restore a .sql backup into a TEMP database (not production).
REM Usage: deploy\win\restore_mysql_test.bat path\to\backup.sql
setlocal EnableExtensions EnableDelayedExpansion

if "%~1"=="" (
  echo Usage: %~nx0 path\to\backup.sql
  echo Example: %~nx0 deploy\backups\flask_shop_flask_shop_saas_20260720_120000.sql
  exit /b 1
)

set "SQLFILE=%~1"
if not exist "%SQLFILE%" (
  echo [ERR] file not found: %SQLFILE%
  exit /b 1
)

set "ROOT=%~dp0..\.."
set "ENV_FILE=%ROOT%\flask_shop\.env"
set "MYSQL_HOST=127.0.0.1"
set "MYSQL_PORT=3306"
set "MYSQL_USERNAME=root"
set "MYSQL_PASSWORD="
set "TEST_DB=flask_shop_restore_test"

if exist "%ENV_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    set "K=%%A"
    set "V=%%B"
    if /i "!K!"=="MYSQL_HOST" set "MYSQL_HOST=!V!"
    if /i "!K!"=="MYSQL_PORT" set "MYSQL_PORT=!V!"
    if /i "!K!"=="MYSQL_USERNAME" set "MYSQL_USERNAME=!V!"
    if /i "!K!"=="MYSQL_PASSWORD" set "MYSQL_PASSWORD=!V!"
  )
)

where mysql >nul 2>nul
if errorlevel 1 (
  echo [ERR] mysql client not in PATH
  exit /b 1
)

echo [WARN] This creates/overwrites database: %TEST_DB%
echo [INFO] Host=%MYSQL_HOST% User=%MYSQL_USERNAME%
pause

mysql -h%MYSQL_HOST% -P%MYSQL_PORT% -u%MYSQL_USERNAME% -p%MYSQL_PASSWORD% -e "DROP DATABASE IF EXISTS %TEST_DB%; CREATE DATABASE %TEST_DB% DEFAULT CHARSET utf8mb4;"
if errorlevel 1 exit /b 1

mysql -h%MYSQL_HOST% -P%MYSQL_PORT% -u%MYSQL_USERNAME% -p%MYSQL_PASSWORD% %TEST_DB% < "%SQLFILE%"
if errorlevel 1 (
  echo [ERR] import failed
  exit /b 1
)

echo [OK] Imported into %TEST_DB%
mysql -h%MYSQL_HOST% -P%MYSQL_PORT% -u%MYSQL_USERNAME% -p%MYSQL_PASSWORD% -e "USE %TEST_DB%; SHOW TABLES; SELECT COUNT(*) AS tenants FROM t_tenants; SELECT COUNT(*) AS orders FROM t_order;"
echo [INFO] Drop test DB when done:
echo   mysql ... -e "DROP DATABASE %TEST_DB%;"
exit /b 0
