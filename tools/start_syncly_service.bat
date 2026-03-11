@echo off
REM ============================================
REM  Auto-start: Syncly Server + ngrok tunnel
REM  Place shortcut in shell:startup folder
REM ============================================

REM Auto-detect Python
if exist "C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" (
    set PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe
) else if exist "C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" (
    set PYTHON=C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe
) else (
    echo [ERROR] Python not found
    exit /b 1
)

REM Project root (this script lives in tools/)
set PROJECT=%~dp0..

echo [%date% %time%] Starting Syncly service...

REM 1. Start syncly webhook server (background)
start /min "SynclyServer" "%PYTHON%" "%PROJECT%\tools\run_syncly_server.py" --port 5050

REM Wait for server to be ready
timeout /t 3 /nobreak >nul

REM 2. Start ngrok tunnel (background)
start /min "NgrokTunnel" ngrok http 5050

echo [%date% %time%] Syncly service started.
echo   - Server: http://localhost:5050
echo   - ngrok:  check http://127.0.0.1:4040

REM 3. Check if today's sync already ran; if not, trigger immediately
timeout /t 5 /nobreak >nul
"%PYTHON%" -c "import sys,os,json,urllib.request;r=urllib.request.urlopen('http://localhost:5050/status',timeout=5);d=json.loads(r.read());lr=d.get('last_run','');today=__import__('datetime').date.today().isoformat();ran=(lr[:10]==today if lr else False);print(f'Last run: {lr}, Today: {today}, Already ran: {ran}');sys.exit(0 if ran else 1)"
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Today's sync not done yet. Triggering now...
    curl -s -X POST http://localhost:5050/sync
    echo.
    echo [%date% %time%] Sync triggered.
) else (
    echo [%date% %time%] Today's sync already completed. Skipping.
)
