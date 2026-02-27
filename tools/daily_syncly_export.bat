@echo off
REM ============================================
REM  Daily Syncly Export + Google Sheets Sync
REM  Schedule: Every day at 17:00 KST (= PST 00:00)
REM ============================================

set PYTHON=C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe
set PROJECT=Z:\Orbiters\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1

echo [%date% %time%] Starting Syncly daily export...

REM Step 1: Download CSV from Syncly
"%PYTHON%" "%PROJECT%\tools\fetch_syncly_export.py"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Syncly export failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

REM Step 2: Sync to Google Sheets
"%PYTHON%" "%PROJECT%\tools\sync_syncly_to_sheets.py"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Sheets sync failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo [%date% %time%] Daily Syncly export complete.
