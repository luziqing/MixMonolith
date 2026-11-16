<#
.SYNOPSIS
  USB tunnel: expose the server's SSH (192.168.1.100:22) to the TouchPad as
  127.0.0.1:8022 over the adb connection, for when the tablet's Wi-Fi is on a
  different subnet than the server.

  Usage:
    powershell -ExecutionPolicy Bypass -File tools\usb_tunnel.ps1            # listen 127.0.0.1:8022 -> 192.168.1.100:22
    powershell -ExecutionPolicy Bypass -File tools\usb_tunnel.ps1 -LocalPort 8022 -TargetHost 192.168.1.100 -TargetPort 22

  After starting it:
    adb reverse tcp:8022 tcp:8022
    (App settings: host 127.0.0.1, port 8022)
#>
param(
    [int]$LocalPort = 8022,
    [string]$TargetHost = "192.168.1.100",
    [int]$TargetPort = 22
)

$ErrorActionPreference = "Stop"
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $LocalPort)
$listener.Start()
Write-Host "tunnel: 127.0.0.1:$LocalPort -> ${TargetHost}:${TargetPort}  (Ctrl+C to stop)"

while ($true) {
    $client = $listener.AcceptTcpClient()
    $client.NoDelay = $true
    try {
        $remote = [System.Net.Sockets.TcpClient]::new()
        $remote.Connect($TargetHost, $TargetPort)
        $remote.NoDelay = $true

        $cs = $client.GetStream()
        $rs = $remote.GetStream()

        $up = $cs.CopyToAsync($rs)
        $down = $rs.CopyToAsync($cs)
        [System.Threading.Tasks.Task]::WaitAny(@($up, $down)) | Out-Null

        $remote.Close()
    } catch {
        Write-Host ("connection failed: " + $_.Exception.Message)
    } finally {
        $client.Close()
    }
}