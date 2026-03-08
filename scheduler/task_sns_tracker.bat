@echo off
REM SNS Content Tracker + Email Notify (daily 08:00)
cd /d "c:\SynologyDrive\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1"
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" tools\run_and_notify.py --task sns_tracker >> scheduler\logs\sns_tracker.log 2>&1
