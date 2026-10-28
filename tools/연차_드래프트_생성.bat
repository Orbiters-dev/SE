@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe tools\outlook_leave_tracker.py --sync
pause