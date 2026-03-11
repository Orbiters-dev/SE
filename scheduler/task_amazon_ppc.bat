@echo off
REM Amazon PPC Daily + Email Notify (daily 08:00)
cd /d "c:\SynologyDrive\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1"
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" tools\run_and_notify.py --task amazon_ppc >> scheduler\logs\amazon_ppc.log 2>&1
