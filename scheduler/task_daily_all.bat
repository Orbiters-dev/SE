@echo off
REM WAT Daily All - 전체 자동화 + 이메일 서머리 (매일 08:00)
cd /d "c:\Users\wjcho\Desktop\WJ Test1"
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" tools\run_daily_all.py >> scheduler\logs\daily_all.log 2>&1
