@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist "deploy\win\start_dev_hmr.ps1" goto missing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "deploy\win\start_dev_hmr.ps1"
if errorlevel 1 goto failed
exit /b 0

:failed
pause
exit /b 1

:missing
echo [ERROR] Missing launcher: deploy\win\start_dev_hmr.ps1
pause
exit /b 1
