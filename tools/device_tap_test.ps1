<#
.SYNOPSIS
  End-to-end tap test of the HUD service discs on the TouchPad (1024x720 page).

  Coordinates were measured against the current build:
    QWEN 9020   361,630      MUSE 9022   461,630
    ASR 13560   584,585      TTS 13561   653,585
    MINERU 9038 722,585      STOP ALL    653,632
  Page y == screen y (fullscreen activity, 48 px nav bar below the WebView, DPR 1).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\device_tap_test.ps1
  powershell -ExecutionPolicy Bypass -File tools\device_tap_test.ps1 -SkipInstall
#>
param(
    [switch]$SkipInstall,
    [string]$SshTarget = "jd4090",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519_204"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$adb = Join-Path $root "tools\platform-tools\adb.exe"
$apk = Join-Path $root "dist\HpScope.apk"
$shots = Join-Path $env:TEMP "hpscope_taps"
New-Item -ItemType Directory -Force $shots | Out-Null

$BTN = @{
    "llm9020" = @(361, 630); "llm9022" = @(461, 630)
    "asr"     = @(584, 585); "tts"     = @(653, 585)
    "mineru"  = @(722, 585); "all"     = @(653, 632)
}
$PORT = @{ "llm9020" = 9020; "llm9022" = 9022; "asr" = 13560; "tts" = 13561; "mineru" = 9038 }

function Invoke-Tap($id) {
    $xy = $BTN[$id]
    & $adb shell input tap $xy[0] $xy[1]
    Write-Host ("  tap {0} -> ({1},{2})" -f $id, $xy[0], $xy[1])
}

function Get-Port($id) {
    $p = $PORT[$id]
    $r = & ssh -i $SshKey -o IdentitiesOnly=yes -o BatchMode=yes $SshTarget "ss -ltn | grep ':$p ' >/dev/null && echo UP || echo down" 2>$null
    return ("$r").Trim()
}

function Save-Shot($name) {
    & $adb shell screencap -p "/sdcard/$name.png" | Out-Null
    & $adb pull "/sdcard/$name.png" (Join-Path $shots "$name.png") 2>&1 | Out-Null
    Write-Host ("  screenshot -> {0}\{1}.png" -f $shots, $name)
}

function Wait-Port($id, $wantUp, $seconds) {
    for ($i = 0; $i -lt $seconds; $i += 5) {
        Start-Sleep -Seconds 5
        $state = Get-Port $id
        if ($wantUp -and $state -eq "UP") { return $true }
        if ((-not $wantUp) -and $state -eq "down") { return $true }
        Write-Host ("    ...{0}s: {1}" -f ($i + 5), $state)
    }
    return $false
}

# ---- 0. device ------------------------------------------------------------
& $adb devices -l
$dev = (& $adb devices) | Select-String "device$"
if (-not $dev) { throw "no device: plug the TouchPad in with USB debugging on" }

if (-not $SkipInstall) {
    Write-Host "`n== install =="
    & $adb install -r $apk | Select-Object -Last 1
}

& $adb shell input keyevent KEYCODE_WAKEUP | Out-Null
& $adb shell am force-stop com.hpscope.mon
& $adb shell am start -n com.hpscope.mon/.MainActivity | Select-Object -Last 1
Start-Sleep -Seconds 4

# ---- 1. ASR start ---------------------------------------------------------
Write-Host "`n== ASR start =="
if ((Get-Port asr) -eq "UP") { Write-Host "  already up, skipping start" }
else {
    Invoke-Tap "asr"
    if (-not (Wait-Port asr $true 90)) { throw "ASR did not listen in 90 s" }
}
Save-Shot "1_asr_on"

# ---- 2. ASR stop (arm once, confirm within 3 s) ---------------------------
Write-Host "`n== ASR stop (double tap) =="
Invoke-Tap "asr"
Start-Sleep -Milliseconds 700
Invoke-Tap "asr"
if (-not (Wait-Port asr $false 30)) { throw "ASR port still listening" }
Save-Shot "2_asr_off"

# ---- 3. STOP ALL ----------------------------------------------------------
Write-Host "`n== stop all =="
Invoke-Tap "all"
Start-Sleep -Milliseconds 700
Invoke-Tap "all"
Start-Sleep -Seconds 4
Save-Shot "3_all_stop"

Write-Host "`n== final state =="
foreach ($id in @("llm9020", "llm9022", "asr", "tts", "mineru")) {
    Write-Host ("  {0,-8} port {1} = {2}" -f $id, $PORT[$id], (Get-Port $id))
}
& ssh -i $SshKey -o IdentitiesOnly=yes -o BatchMode=yes $SshTarget "nvidia-smi --query-gpu=memory.free,memory.used --format=csv,noheader"
Write-Host "`nDONE - screenshots in $shots"