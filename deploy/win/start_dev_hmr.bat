@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
set "ROOT=%CD%"
echo [dev-hmr] mall 5202 / admin 8082 / api 5002
echo [check] go_live_check ...
"%ROOT%\flask_shop\.venv\Scripts\python.exe" "%ROOT%\flask_shop\scripts\verify\go_live_check.py"
start "shop-api" /D "%ROOT%\flask_shop" cmd /k "set FLASK_PORT=5002&& set CORS_ORIGINS=http://127.0.0.1:5202,http://localhost:5202,http://127.0.0.1:8082,http://localhost:8082&& .venv\Scripts\python.exe manager.py"
timeout /t 2 /nobreak >nul
start "shop-mall-HMR" /D "%ROOT%\mall" cmd /k "set VITE_API_PROXY_TARGET=http://127.0.0.1:5002&& npm run dev -- --host 127.0.0.1 --port 5202 --strictPort"
timeout /t 1 /nobreak >nul
start "shop-admin-HMR" /D "%ROOT%\vue_shop" cmd /k "npm run serve -- --host 127.0.0.1 --port 8082"
echo opened. use http://127.0.0.1:5202
pause
