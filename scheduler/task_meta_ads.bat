@echo off
REM Meta Ads Daily + Email Notify (daily 08:00)
cd /d "c:\SynologyDrive\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1"
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" tools\run_and_notify.py --task meta_ads >> scheduler\logs\meta_ads.log 2>&1
