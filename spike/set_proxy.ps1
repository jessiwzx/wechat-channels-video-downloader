param(
    [ValidateSet("on", "off")]
    [string]$State,
    [int]$Port = 8899
)
# SPIKE 临时脚本：设置/还原 Windows 系统代理（当前用户级，无需管理员）
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
if ($State -eq "on") {
    Set-ItemProperty -Path $reg -Name ProxyServer -Value "127.0.0.1:$Port"
    Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
}
else {
    Set-ItemProperty -Path $reg -Name ProxyEnable -Value 0
}

# 通知 WinINET 刷新设置，让已运行的程序感知变化
$src = @"
[DllImport("wininet.dll", SetLastError=true)]
public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);
"@
$t = Add-Type -MemberDefinition $src -Name WinINET -Namespace Win32 -PassThru
[void]$t::InternetSetOption([IntPtr]::Zero, 95, [IntPtr]::Zero, 0)  # SETTINGS_CHANGED
[void]$t::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0)  # REFRESH
Write-Host "system proxy -> $State (127.0.0.1:$Port)"
