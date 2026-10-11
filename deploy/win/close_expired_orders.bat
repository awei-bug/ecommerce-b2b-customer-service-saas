@echo off
cd /d "%~dp0..\..\flask_shop"
".venv\Scripts\python.exe" scripts\jobs\close_expired_orders.py
