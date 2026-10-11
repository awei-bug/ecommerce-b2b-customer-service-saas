@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist "deploy\win\start_dev_hmr.bat" goto missing
call "deploy\win\start_dev_hmr.bat"
exit /b %errorlevel%

:missing
echo [ERROR] Missing launcher: deploy\win\start_dev_hmr.bat
pause
exit /b 1
