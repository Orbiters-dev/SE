# Register DataKeeper NAS Sync Task Scheduler
# Runs sync-nas every 12 hours (9AM + 9PM KST)

$taskName = "DataKeeper NAS Sync"

# Remove existing
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing task: $taskName"
}

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument '/c "Z:\Orbiters\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1\tools\sync_nas_datakeeper.bat"'
$trigger1 = New-ScheduledTaskTrigger -Daily -At "09:00AM"
$trigger2 = New-ScheduledTaskTrigger -Daily -At "09:00PM"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger1,$trigger2 -Settings $settings -Description "Sync DataKeeper PG data to NAS Shared folder every 12 hours"

Write-Host ""
Write-Host "Task registered: $taskName"
Get-ScheduledTask -TaskName $taskName | Format-List TaskName, State
