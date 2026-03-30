@echo off
echo Registering WAT scheduled tasks...

set "BASE=c:\Users\wjcho\Desktop\WJ Test1\scheduler"

schtasks /create /tn "WAT\AmazonPPC_Daily" /tr "\"%BASE%\task_amazon_ppc.bat\"" /sc daily /st 09:03 /f
schtasks /create /tn "WAT\MetaAds_Daily" /tr "\"%BASE%\task_meta_ads.bat\"" /sc daily /st 09:07 /f
schtasks /create /tn "WAT\Syncly_Daily" /tr "\"%BASE%\task_syncly_export.bat\"" /sc daily /st 08:03 /f
schtasks /create /tn "WAT\SNSTracker_Daily" /tr "\"%BASE%\task_sns_tracker.bat\"" /sc daily /st 08:13 /f
schtasks /create /tn "WAT\PolarWeekly" /tr "\"%BASE%\task_polar_weekly.bat\"" /sc weekly /d MON /st 09:13 /f

echo.
echo Verifying...
schtasks /query /fo TABLE /tn "WAT\AmazonPPC_Daily"
schtasks /query /fo TABLE /tn "WAT\MetaAds_Daily"
schtasks /query /fo TABLE /tn "WAT\Syncly_Daily"
schtasks /query /fo TABLE /tn "WAT\SNSTracker_Daily"
schtasks /query /fo TABLE /tn "WAT\PolarWeekly"

echo.
echo All tasks registered!
pause
