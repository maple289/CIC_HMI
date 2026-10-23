@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" scripts\run_hmi.py --read-only-com4
