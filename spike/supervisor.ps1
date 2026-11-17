# SPIKE supervisor: auto-restart mitmdump (max 5 tries); if all fail, disable system proxy
# NOTE: keep this file ASCII-only (PS 5.1 reads no-BOM files as ANSI/GBK; Chinese path
# literals would mojibake). Dir is derived from script location instead.
$spike = Split-Path -Parent $PSCommandPath
$mitmdump = "C:\Users\wzx\AppData\Local\Programs\Python\Python312\Scripts\mitmdump.exe"
$maxRetry = 5
for ($i = 1; $i -le $maxRetry; $i++) {
    Write-Output "[$(Get-Date -Format 'HH:mm:ss')] mitmdump start #$i"
    & $mitmdump -p 8899 -s "$spike\capture5_addon.py" -w "$spike\traffic_round5_$i.flow" *>> "$spike\mitmdump_r5.log"
    Write-Output "[$(Get-Date -Format 'HH:mm:ss')] mitmdump exited, retry in 2s"
    Start-Sleep -Seconds 2
}
# all retries exhausted: restore network (avoid dangling proxy)
& powershell -NoProfile -ExecutionPolicy Bypass -File "$spike\set_proxy.ps1" -State off
