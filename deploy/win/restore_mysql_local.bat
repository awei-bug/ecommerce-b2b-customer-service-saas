@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
"flask_shop\.venv\Scripts\python.exe" "deploy\win\restore_mysql_local.py" %*
pause
