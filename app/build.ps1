<#
.SYNOPSIS
  One-click build of HpScope for the HP TouchPad (no Android Studio / Gradle).

  aapt2 compile -> aapt2 link (+R.java) -> javac -> d8 -> aapt add dex -> zipalign -> apksigner

  Compile-SDK  = android-19 (only so that android.webkit.JavascriptInterface,
                which appeared in API 17, can be compiled; the app itself only
                calls APIs that exist on the TouchPad's Android 4.0.4).
  minSdkVersion = 15  (Android 4.0.3/4.0.4 = CM9/Evervolv era, also runs on newer ROMs)

.EXAMPLE
  powershell -File app\build.ps1
  powershell -File app\build.ps1 -Install        # also adb install -r
#>
param(
    [switch]$Install,
    [string]$Jdk = "C:\Program Files\Eclipse Adoptium\jdk-8.0.512.9-hotspot"
)

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent $PSScriptRoot
$src    = Join-Path $PSScriptRoot "src\HpScope"
$out    = Join-Path $PSScriptRoot "build"
$dist   = Join-Path $root "dist"
$appName = "HpScope.apk"

# ---- local toolchain (tools/ is created by docs/01-environment-setup) ----
$bt        = Join-Path $root "tools\android-9"
$sdkCompile = Join-Path $root "tools\android-4.4.2\android.jar"   # API 19, compile-time only
$jsch      = Join-Path $root "tools\vendor\jsch-0.2.20-android.jar"       # SSH transport (BSD, rsa-sha2 support)
$minApi    = 15
$jdkHome   = $Jdk
if (-not (Test-Path $jdkHome)) {
    $cand = Get-ChildItem "C:\Program Files\Eclipse Adoptium" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cand) { $jdkHome = $cand.FullName }
}
$java    = Join-Path $jdkHome "bin\java.exe"
$javac   = Join-Path $jdkHome "bin\javac.exe"
$keytool = Join-Path $jdkHome "bin\keytool.exe"
foreach ($p in @($sdkCompile, $java, $javac, $jsch, (Join-Path $bt "aapt2.exe"), (Join-Path $bt "lib\d8.jar"))) {
    if (-not (Test-Path $p)) { throw "missing tool: $p  (run docs/01-environment-setup first)" }
}

# ---- 0. encoding guard: never ship mojibake -------------------------------
& python "$root\tools\check_encoding.py" "$src\assets\index.html" "$src\res\values\strings.xml" `
     "$src\AndroidManifest.xml" 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { throw "encoding check failed - Chinese text is corrupted" }

Write-Host "== tools =="
Write-Host "  jdk        : $jdkHome"
Write-Host "  compile sdk: $sdkCompile (API 19)"
Write-Host "  min sdk     : $minApi (Android 4.0.3+)"

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $out, "$out\classes", "$out\gen" | Out-Null
if (-not (Test-Path $dist)) { New-Item -ItemType Directory -Force -Path $dist | Out-Null }

# ---- 1. compile resources --------------------------------------------------
& "$bt\aapt2.exe" compile --dir "$src\res" -o "$out\res.zip"
if ($LASTEXITCODE -ne 0) { throw "aapt2 compile failed" }

# ---- 2. link manifest + assets + resources (+ generate R.java) --------------
& "$bt\aapt2.exe" link -o "$out\base.apk" -I $sdkCompile --manifest "$src\AndroidManifest.xml" `
    -A "$src\assets" --min-sdk-version $minApi --target-sdk-version $minApi `
    --auto-add-overlay --java "$out\gen" "$out\res.zip"
if ($LASTEXITCODE -ne 0) { throw "aapt2 link failed" }

# ---- 3. java ---------------------------------------------------------------
$srcs = @(Get-ChildItem "$src\java" -Recurse -Filter *.java | ForEach-Object { $_.FullName }) +
        @(Get-ChildItem "$out\gen" -Recurse -Filter R.java | ForEach-Object { $_.FullName })
& $javac -nowarn -encoding UTF-8 -source 1.7 -target 1.7 -bootclasspath $sdkCompile `
    -cp $jsch -d "$out\classes" $srcs
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

# ---- 4. dex ---------------------------------------------------------------
$classes = Get-ChildItem "$out\classes" -Recurse -Filter *.class | ForEach-Object { $_.FullName }
if (-not $classes) { throw "no compiled classes" }
& $java -Xmx1024M -cp "$bt\lib\d8.jar" com.android.tools.r8.D8 --release --min-api $minApi `
    --lib $sdkCompile --output "$out" $jsch $classes
if ($LASTEXITCODE -ne 0) { throw "d8 failed" }
$dex = "$out\classes.dex"
if (-not (Test-Path $dex)) { throw "dex not produced" }

# ---- 5. add dex + align --------------------------------------------------
# aapt stores the name exactly as given, so add the dex from its own directory:
# an absolute path would land in the archive as "C:/.../classes.dex" and Android
# would not find its classes.
Push-Location $out
try {
    & "$bt\aapt.exe" add "$out\base.apk" classes.dex | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "aapt add failed" }
} finally {
    Pop-Location
}
$aligned = "$out\aligned.apk"
& "$bt\zipalign.exe" -f 4 "$out\base.apk" $aligned
if ($LASTEXITCODE -ne 0) { throw "zipalign failed" }

# ---- 6. debug keystore (regenerate when absent) ---------------------------
$keystore = Join-Path $root "app\debug.keystore"
if (-not (Test-Path $keystore)) {
    & $keytool -genkeypair -v -keystore $keystore -storepass android -keypass android `
        -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 `
        -dname "CN=Android Debug,O=Android,C=US" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $keystore)) { throw "keystore generation failed" }
}

# ---- 7. sign -------------------------------------------------------------
$signed = Join-Path $dist $appName
& $java -jar "$bt\lib\apksigner.jar" sign --ks $keystore --ks-pass pass:android --key-pass pass:android `
    --out $signed $aligned
if ($LASTEXITCODE -ne 0) { throw "apksigner failed" }

Write-Host ""
Write-Host "BUILD OK -> $signed ($([int]((Get-Item $signed).Length/1kb)) KB)"

# ---- 8. install ----------------------------------------------------------
$adb = Join-Path $root "tools\platform-tools\adb.exe"
if ($Install) {
    if (-not (Test-Path $adb)) { throw "adb missing, run docs/01-environment-setup" }
    & $adb devices
    & $adb install -r $signed
    & $adb shell am start -n com.hpscope.mon/.MainActivity
}
