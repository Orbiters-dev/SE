@echo off
REM Sync Data Keeper PG -> NAS Shared folder
REM Runs every 12 hours via Task Scheduler
REM This keeps Shared/datakeeper/latest/ up to date for all team members

cd /d "c:\Users\wjcho\Desktop\WJ Test1"
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" tools/data_keeper.py --sync-nas

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] sync-nas failed at %date% %time% >> "%~dp0\..\\.tmp\\sync_nas_log.txt"
) else (
    echo [OK] sync-nas completed at %date% %time% >> "%~dp0\..\\.tmp\\sync_nas_log.txt"
)
