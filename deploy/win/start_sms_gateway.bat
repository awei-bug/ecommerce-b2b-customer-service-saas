@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
set SMS_GW_HOST=127.0.0.1
set SMS_GW_PORT=19090
set SMS_HTTP_TOKEN=dev-sms-token
echo Starting SMS HTTP gateway on http://127.0.0.1:19090
"flask_shop\.venv\Scripts\python.exe" "deploy\win\sms_http_gateway.py"
pause
