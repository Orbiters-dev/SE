@echo off
REM WAT Daily All - 전체 자동화 + 이메일 서머리 (매일 08:00)
cd /d "c:\SynologyDrive\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1"
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" tools\run_daily_all.py >> scheduler\logs\daily_all.log 2>&1
