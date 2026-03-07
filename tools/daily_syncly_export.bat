@echo off
REM ============================================
REM  Daily Syncly Export + Google Sheets Sync
REM  Works on both Desktop (wjcho) and Laptop (user)
REM ============================================

REM Auto-detect Python path
if exist "C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" (
    set PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe
) else if exist "C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" (
    set PYTHON=C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe
) else (
    echo [ERROR] Python not found on this machine
    exit /b 1
)

REM Auto-detect project root (this script lives in tools/)
set PROJECT=%~dp0..

echo [%date% %time%] Starting Syncly daily export...
echo [INFO] Python: %PYTHON%
echo [INFO] Project: %PROJECT%

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
