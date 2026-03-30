@echo off
REM SNS Content Tracker + Email Notify (daily 08:00)
cd /d "c:\Users\wjcho\Desktop\WJ Test1"
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" tools\run_and_notify.py --task sns_tracker >> scheduler\logs\sns_tracker.log 2>&1
