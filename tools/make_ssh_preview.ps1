<#
.SYNOPSIS
  Build docs/dashboard_ssh_preview.html from REAL SSH data.

  This is the preview path that matches the app: it pipes
  app/src/HpScope/assets/probe_remote.py into `python3 -` over SSH with the
  existing key (default: ~/.ssh/id_ed25519_204), captures two raw snapshots and
  replays them in the page. No probe daemon, no server-side files.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\make_ssh_preview.ps1
  powershell -ExecutionPolicy Bypass -File tools\make_ssh_preview.ps1 -Target jd4090 -Key C:\Users\me\.ssh\id_ed25519_204
#>
param(
    [string]$Target = "jd4090",
    [string]$Key = "$env:USERPROFILE\.ssh\id_ed25519_204",
    [string]$SshUser = "jd4090",
    [string]$SshHost = "192.168.1.100",
    [int]$SshPort = 22,
    [string]$OutFile = "docs\dashboard_ssh_preview.html"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root "app\src\HpScope\assets\index.html"
$py = Join-Path $root "app\src\HpScope\assets\probe_remote.py"
$dst = Join-Path $root $OutFile

if (-not (Test-Path $Key)) { throw "ssh key not found: $Key" }
if (-not (Test-Path $py)) { throw "probe script not found: $py" }

# ---- 1. capture two real snapshots over SSH (script travels on stdin) --------
function Get-Snapshot {
    $script = [System.IO.File]::ReadAllText($py, [System.Text.Encoding]::UTF8)
    $lines = $script | & ssh -i $Key -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 $Target "python3 -" 2>&1
    $text = ($lines -join "`n").Trim()
    if (-not $text.StartsWith("{")) { throw "ssh probe failed: $text" }
    try { $null = $text | ConvertFrom-Json } catch { throw "probe returned non-JSON: $text" }
    return $text
}

Write-Host "== ssh probe =="
Write-Host "  target : $Target ($Key)"
$snap1 = Get-Snapshot
Start-Sleep -Seconds 2
$snap2 = Get-Snapshot
Write-Host ("  snapshot: {0} B / {1} B" -f $snap1.Length, $snap2.Length)

# ---- 2. page = index.html + replay harness ----------------------------------
$html = [System.IO.File]::ReadAllText($src, [System.Text.Encoding]::UTF8)

$inject = @"
<script type="text/javascript">
window.__HP_URL__ = "ssh://$($SshUser)@$($SshHost):$($SshPort)";
window.__HP_BUILD__ = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')";
window.__A__ = $snap1;
window.__B__ = $snap2;
(function () {
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function drift(s, pctCpu, pctGpu, kbps) {
    var c = clone(s);
    c.ts += 2;
    var total = 4800;
    c.cpu[0] += total; c.cpu[1] += Math.round(total * (1 - pctCpu / 100));
    for (var i = 0; i < c.cores.length; i++) {
      var per = 200, p = Math.max(0, Math.min(100, pctCpu + (Math.random() * 30 - 15)));
      c.cores[i][0] += per; c.cores[i][1] += Math.round(per * (1 - p / 100));
    }
    if (c.gpu) {
      c.gpu.util = Math.max(0, Math.min(100, pctGpu + (Math.random() * 10 - 5)));
      /* Keep memory / power / fan close to the captured baseline. This is a
         2 s playback, not a load simulation: an unbounded random walk invented
         idle VRAM swings of GBs and a fan ramping to 100% that never happened. */
      var bg = (window.__B__ && window.__B__.gpu) || {};
      if (typeof c.gpu.mem_used_mb === "number" && typeof c.gpu.mem_total_mb === "number") {
        var baseMem = (typeof bg.mem_used_mb === "number") ? bg.mem_used_mb : c.gpu.mem_used_mb;
        c.gpu.mem_used_mb = Math.max(0, Math.min(c.gpu.mem_total_mb,
          baseMem + (Math.random() * 200 - 30)));
      }
      if (typeof c.gpu.power_w === "number") {
        var basePw = (typeof bg.power_w === "number") ? bg.power_w : c.gpu.power_w;
        c.gpu.power_w = Math.max(5, basePw + (Math.random() * 3 - 1.5));
      }
      if (typeof c.gpu.fan_pct === "number") {
        var baseFan = (typeof bg.fan_pct === "number") ? bg.fan_pct : c.gpu.fan_pct;
        c.gpu.fan_pct = Math.max(0, Math.min(100, baseFan + (Math.random() * 4 - 2)));
      }
    }
    var bytes = kbps * 1024 * 2;
    for (var j = 0; j < c.net.length; j++) {
      c.net[j].rx += Math.round(bytes * (0.7 + Math.random() * 0.6));
      c.net[j].tx += Math.round(bytes * (0.15 + Math.random() * 0.2));
    }
    return c;
  }
  var cur = window.__B__;
  var hist = [];
  for (var k = 24; k > 0; k--) {
    cur = drift(cur, 12 + Math.random() * 18, 4 + Math.random() * 16, 180 + Math.random() * 700);
    hist.push(cur);
  }
  window.__push(window.__A__);
  window.__push(window.__B__);
  for (var m = 0; m < hist.length; m++) { window.__push(hist[m]); }
  setInterval(function () {
    cur = drift(cur, 8 + Math.random() * 22, 5 + Math.random() * 20, 120 + Math.random() * 900);
    try { window.__push(cur); } catch (e) { }
  }, 2000);
  var brand = document.getElementById('brand');
  if (brand) { brand.innerHTML = 'PREVIEW ' + window.__HP_BUILD__ + ' (buttons are display-only)'; }
})();
</script>
</body>
"@

$out = $html -replace '</body>', $inject
# the page's browser fallback would poll a relative "json" URL; useless here
$out = $out -replace 'if \(!\(window\.HpScopeBridge && window\.HpScopeBridge\.config\)\) \{', 'if (false) {'
[System.IO.File]::WriteAllText($dst, $out, (New-Object System.Text.UTF8Encoding($false)))

# ---- 3. guards --------------------------------------------------------------
& python (Join-Path $root "tools\check_encoding.py") $dst 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { throw "preview encoding check failed" }

$bytes = [System.IO.File]::ReadAllBytes($dst)
$text = [System.Text.Encoding]::UTF8.GetString($bytes)
$labels = @('USAGE GRAPHS', 'MOTHERBOARD SENSORS', 'PER-CORE USAGE', 'logical cores',
            'NETWORK &amp; HOST', 'cpu', 'ram')
$keys = 0
foreach ($l in $labels) { if ($text.Contains($l)) { $keys++ } }
if ($keys -lt 6) { throw "preview looks incomplete ($keys/$($labels.Count) labels)" }

Write-Host ("dashboard_ssh_preview.html regenerated: {0} KB, utf-8 clean, {1}/{2} markers" -f `
    [int]($bytes.Length / 1kb), $keys, $labels.Count)