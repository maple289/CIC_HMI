@echo off
setlocal
"%~dp0..\.venv\Scripts\python.exe" "%~dp0run_hmi.py" %*
if errorlevel 1 pause
