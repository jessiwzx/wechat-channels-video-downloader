# SPIKE network watchdog: if port 8899 has no listener 3 times in a row (10s apart),
# disable the system proxy automatically, then exit.
# NOTE: keep this file ASCII-only (PS 5.1 + no-BOM = GBK; derive dir from script path).
$spike = Split-Path -Parent $PSCommandPath
$fails = 0
while ($true) {
    Start-Sleep -Seconds 10
    $ok = $false
    try {
        $c = Get-NetTCPConnection -LocalPort 8899 -State Listen -ErrorAction Stop
        $ok = ($c.Count -gt 0)
    } catch { $ok = $false }
    if ($ok) { $fails = 0 } else { $fails = $fails + 1 }
    if ($fails -ge 3) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File "$spike\set_proxy.ps1" -State off
        break
    }
}
