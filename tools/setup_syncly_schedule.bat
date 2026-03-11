@echo off
REM ============================================
REM  Register Daily Syncly Export in Task Scheduler
REM  KST 08:00 (daily)
REM  Run this script once as Administrator
REM ============================================

set TASK_NAME=DailySynclyExport
set BAT_PATH=%~dp0daily_syncly_export.bat
set SCHEDULE_TIME=08:00

echo [INFO] Registering scheduled task: %TASK_NAME%
echo [INFO] Script: %BAT_PATH%
echo [INFO] Time: %SCHEDULE_TIME% (daily)

schtasks /create /tn "%TASK_NAME%" /tr "\"%BAT_PATH%\"" /sc daily /st %SCHEDULE_TIME% /f

if %ERRORLEVEL% EQU 0 (
    echo [OK] Task registered successfully.
    echo [INFO] Verify with: schtasks /query /tn %TASK_NAME%
) else (
    echo [ERROR] Failed to register task. Try running as Administrator.
)

pause
