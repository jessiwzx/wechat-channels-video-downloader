# Production network watchdog (external backstop for orchestrator.py).
# Runs minimized, started by the weekly download bat BEFORE python starts.
# - waits until port 8899 first has a listener (grace for slow startup)
# - if the listener then stays dead for 3 x 10s, disables the system proxy
# - self-exits after 3h at most
# NOTE: keep this file ASCII-only (PS 5.1 + no-BOM = GBK; derive dir from script path).
$src = Split-Path -Parent $PSCommandPath
$deadline = (Get-Date).AddHours(3)
$sawUp = $false
$fails = 0
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 10
    $ok = $false
    try {
        $c = Get-NetTCPConnection -LocalPort 8899 -State Listen -ErrorAction Stop
        $ok = ($c.Count -gt 0)
    } catch { $ok = $false }
    if ($ok) { $sawUp = $true; $fails = 0 }
    elseif ($sawUp) { $fails = $fails + 1 }
    if ($fails -ge 3) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File "$src\set_proxy.ps1" -State off
        break
    }
}
