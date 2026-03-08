@echo off
REM Syncly Export + Email Notify (daily 08:00)
cd /d "c:\SynologyDrive\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1"
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" tools\run_and_notify.py --task syncly >> scheduler\logs\syncly_export.log 2>&1
