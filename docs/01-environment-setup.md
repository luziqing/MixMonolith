# 阶段 0 · 环境准备（Windows 侧，一键可复现）

> 产出：`tools/` 目录 + JDK 8 + adb。全程不装 Android Studio / Gradle（合计 <200 MB）。

## 1. 目录结构

```
C:\docker\HPpad\
├── tools\                本目录产物（adb / build-tools / android.jar）
├── app\                   HpScope 源码 + build.ps1
├── probe\                 服务器探针 + 安装脚本
├── docs\                 规划与操作手册
└── dist\                 HpScope.apk
```

## 2. 安装 JDK 8（javac / jarsigner / keytool）

```powershell
winget install --id EclipseAdoptium.Temurin.8.JDK -e --silent --accept-package-agreements
```

## 3. 下载 Android SDK 平台工具与构建工具

```powershell
cd C:\docker\HPpad
New-Item -ItemType Directory -Force -Path tools, app, probe, docs, dist | Out-Null
cd tools

# adb / fastboot
curl.exe -L -o platform-tools.zip https://dl.google.com/android/repository/platform-tools-latest-windows.zip

# build-tools 28.0.3（aapt2.exe / d8.jar / apksigner.jar / zipalign.exe / aapt.exe / dx）
curl.exe -L -o build-tools.zip https://dl.google.com/android/repository/build-tools_r28.0.3-windows.zip

# android.jar：API 15=设备实际运行版本，API 19=编译期需要 @JavascriptInterface（API 17 才引入）
curl.exe -L -o android15.zip https://dl.google.com/android/repository/android-15_r05.zip
curl.exe -L -o android19.zip https://dl.google.com/android/repository/android-19_r04.zip

tar.exe -xf platform-tools.zip; tar.exe -xf build-tools.zip
tar.exe -xf android15.zip; tar.exe -xf android19.zip; Remove-Item *.zip

# 生成应用图标（System.Drawing，也可换成自己的 96x96 PNG）
powershell -File ..\tools\make_icon.ps1
```

解包后：
```
tools\platform-tools\adb.exe
tools\android-9\{aapt2.exe,aapt.exe,zipalign.exe,lib\d8.jar,lib\apksigner.jar,...}
tools\android-4.0.4\android.jar     (API 15)
tools\android-4.4.2\android.jar     (API 19，编译期 bootclasspath)
```

## 4. 自检

```powershell
C:\docker\HPpad\tools\platform-tools\adb.exe version
# Android Debug Bridge version 1.0.41 / Version 37.0.1-...

& 'C:\Program Files\Eclipse Adoptium\jdk-8.0.512.9-hotspot\bin\java.exe' -version
# openjdk version "1.8.0_512"

C:\docker\HPpad\tools\android-9\aapt2.exe version
# Android Asset Packaging Tool (aapt) 2:19
```

## 5. 常见坑（本次都踩过）

| 现象 | 原因 / 解法 |
|---|---|
| `package JavascriptInterface does not exist` | `@JavascriptInterface` 是 **API 17** 才有；编译必须用 API ≥17 的 android.jar（用 19），`minSdkVersion` 仍写 15 |
| `aapt2 link: unknown option '-M'` | aapt2 用 `--manifest`；编译后的资源作为**位置参数**传入（不要用 `-R`，那会按 overlay 语义合并而报 "does not override"）；需要 `--auto-add-overlay` |
| `d8: Unsupported source file type` | 不能把 class 目录直接丢给 d8；要展开 `*.class` 文件（或打成 jar） |
| `javac: 找不到目录 build\classes` | `-d` 的父目录要存在，先 `New-Item` |
| NativeCommandError 让脚本中断 | keytool 等原生命令的 stderr 在 `$ErrorActionPreference='Stop'` 下会停脚本；用 `2>&1 \| Out-Null` 并检查 `$LASTEXITCODE` |

参考对照：`luziqing/MixMonolith`（build_apk.py 的免 Studio 打包思路、aapt2/r8/adb 组合栈）。
