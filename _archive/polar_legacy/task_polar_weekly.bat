@echo off
REM ORBI KPIs Weekly + Email Notify (Monday 08:00)
cd /d "c:\SynologyDrive\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1"
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" tools\run_and_notify.py --task orbi_kpis >> scheduler\logs\orbi_kpis.log 2>&1
