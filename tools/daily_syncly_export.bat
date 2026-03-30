@echo off
REM ============================================
REM  Daily Syncly Export + Google Sheets Sync
REM  Runs both US and JP regions
REM  Works on both Desktop (wjcho) and Laptop (user)
REM ============================================

REM Auto-detect Python path
if exist "C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" (
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

REM ── US Region ──
echo.
echo [US] Fetching Syncly data...
"%PYTHON%" "%PROJECT%\tools\fetch_syncly_export.py" --region us
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] US Syncly export failed
) else (
    echo [US] Syncing to Google Sheets...
    "%PYTHON%" "%PROJECT%\tools\sync_syncly_to_sheets.py" --region us
)

REM ── JP Region ──
echo.
echo [JP] Fetching Syncly data...
"%PYTHON%" "%PROJECT%\tools\fetch_syncly_export.py" --region jp
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] JP Syncly export failed
) else (
    echo [JP] Syncing to Google Sheets...
    "%PYTHON%" "%PROJECT%\tools\sync_syncly_to_sheets.py" --region jp
)

REM ── Email Notification ──
echo.
echo [EMAIL] Sending daily update email...
"%PYTHON%" "%PROJECT%\tools\syncly_daily_email.py"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Email send failed
)

echo.
echo [%date% %time%] Daily Syncly export complete (US + JP).
