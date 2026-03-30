@echo off
REM Meta Ads Daily + Email Notify (daily 08:00)
cd /d "c:\Users\wjcho\Desktop\WJ Test1"
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" tools\run_and_notify.py --task meta_ads >> scheduler\logs\meta_ads.log 2>&1
