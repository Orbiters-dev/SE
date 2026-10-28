# Influencer form upload video renamer - Task Scheduler wrapper (hourly)
# Task name: InfluencerFormUploadRename
$py = "C:\Users\orbit\AppData\Local\Programs\Python\Python314\python.exe"
$script = "c:\Users\orbit\Desktop\SE\tools\rename_form_uploads.py"
$log = "c:\Users\orbit\Desktop\SE\.tmp\influencer_forms\rename_uploads_log.txt"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$out = & $py -X utf8 $script 2>&1 | Out-String
"[$ts] exit=$LASTEXITCODE`n$out" | Out-File -FilePath $log -Append -Encoding utf8

# keep log under ~200KB
if ((Get-Item $log -ErrorAction SilentlyContinue).Length -gt 200KB) {
    $lines = Get-Content $log -Encoding utf8
    $lines[-500..-1] | Out-File -FilePath $log -Encoding utf8
}
exit $LASTEXITCODE
