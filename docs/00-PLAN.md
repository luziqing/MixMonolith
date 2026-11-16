# HP TouchPad (tenderloin) 服务器信息展示 · 总体规划

> 目标：让一台老的 **HP TouchPad（2011，代号 tenderloin）** 变成一块「服务器监控副屏」，
> 实时展示 **<SERVER_IP>（jd4090，Ubuntu 24.04.2）** 的 CPU / 内存 / 磁盘 / GPU / 网络 / 开机时长。
> 参考实现思路：`github.com/luziqing/MixMonolith`（宿主机零常驻、原生容器 + WebView HUD、免 Android Studio 打包）。

---

## 0. 结论（当前状态）

| 项 | 状态 |
|---|---|
| 服务器侧（Ubuntu jd4090） | ✅ 已清理：8080 探针与 `~/hpscope` 全部删除，只剩 `authorized_keys` 一行 `restrict … hpscope-touchpad-app` |
| Android 端 APK（HpScope，minSdk 15） | ✅ 已构建并签名：`dist/HpScope.apk`（149 KB），SSH 只读直连（JSch + 内置预授权 RSA 密钥），横屏全屏常亮 |
| 本地工具链（adb / aapt2 / d8 / JDK8 / android.jar） | ✅ 已就绪：`tools/` |
| TouchPad 实机安装 | ⏳ 待设备连接（见 `docs/RUNBOOK.md` 阶段 4） |

数据面已验证（本轮实测输出，见 `docs/RUNBOOK.md` 附录）：
`jd4090 · Linux 6.11.0-17-generic · 24 线程 · CPU 0.4% · 内存 17.8/188.3 GB · / + /boot + /sas14Ta + /sas14Tb(13TB×2) · enp130s0 · RTX 4090 D 48GB(25.5GB used, 29°C, 7.1W) · uptime 1d19h`

扩展指标（全部已在服务器实测通过）：load 1/5/15、CPU 温度（hwmon，37 °C）+ 全传感器区 + 风扇、
TOP 4 进程（CPU% 与 内存 GB，sglang/VLLM/TeamViewer…）、Docker 运行容器与镜像数、GPU 数量。

---

## 1. 设备与 ROM 现状判断（先做，别急着刷）

TouchPad 已刷 Android，但具体版本决定了后续玩法，先用 `adb shell getprop` 确认：

```
adb shell getprop ro.build.version.release     # 期望 4.0.3 / 4.0.4 / 4.4.4 / 5.x / 7.1 ...
adb shell getprop ro.product.model
adb shell getprop ro.build.version.sdk          # 15=4.0.3/4, 19=4.4, 25=7.1
adb shell wm size                              # 期望 1024x768
```

ROM 生态（XDA / rootzwiki 已核实的几条线）：

| ROM | Android | 说明 |
|---|---|---|
| **CM9** | 4.0.3/4.0.4 (API 15) | 最经典、最稳；设备对应 `tenderloin` |
| **Evervolv** | 4.0.3p1 → 4.4.4 → 5.x → 6.x → 7.1 | evervolv.com/devices/tenderloin |
| AOSP Pie (elginsk8r) | 9 | 现代但发热/兼容性挑 |

**建议**：本次目标只是「展示服务器信息」，**不需要重刷**。已装的任何 Android ≥ 4.0.3 都能跑 HpScope（minSdk 15）。
只有当现有 ROM 不稳定、Wi-Fi 不稳定、或 Adb 不可用时，才按阶段 3 重刷。

---

## 2. 架构设计

```
┌──────────────────────┐   SSH exec (2 s, 只读)   ┌─────────────────────────┐
│  HpScope.apk         │ ───────────────────────► │  jd4090 (Ubuntu 24.04)  │
│  (TouchPad, API 15)  │   python3 - <<脚本>>      │  /proc /sys nvidia-smi   │
│  ├─ MainActivity     │ ◄─────────────────────── │  （不落盘、不装包）       │
│  ├─ SshProbe (JSch)  │      原始计数 JSON        │                          │
│  └─ assets/index.html│                          │  authorized_keys 一行    │
│     ES5 + WebKit534  │                          │  restrict ecdsa-…        │
└──────────────────────┘                          └─────────────────────────┘
```

设计取舍：
- **SSH 只读拉取（当前方案）**：App 用 JSch 直连 `jd4090`，每次把 `probe_remote.py` 随 exec 通道送进 `python3 -`，只读 `/proc`、`/sys`、`nvidia-smi`，服务器上不写文件、不装包。
  注意不能用 ed25519：JSch 0.1.55 只支持 RSA/DSA/ECDSA，而 OpenSSH 9.6 禁用了 `ssh-rsa`（SHA-1），所以改用 RSA-3072 + rsa-sha2。
- **HTTP 探针已移除**：它曾用于让浏览器直接看大屏，现在唯一通路是 APK。
- **原生容器 + WebView 桥**：Java 只做传输，`loadUrl("javascript:__push(<json>)")` 把原始计数推给页面；
  页面用 ES5 计算 CPU/每核/网络差值并渲染。避开 WebView 的 XHR/CORS 老问题，也不在页面里用 `fetch`。
- **信息架构参考 Pigsty `node-overview` 与 hardviz Performance 屏**：三行卡片网格 ——
  hero 环表（CPU/RAM/GPU）→ USAGE GRAPHS + PROCESS → PER-CORE + STORAGE + SENSORS + NETWORK。
  早期的 24 核科幻圆环 / GPU 涡扇 / 任务管理器式柱子均已弃用（可读性差、软渲染开销大）。
- **UI 只写 ES5 + table/float/绝对定位**：`let/const`、箭头函数、模板串、`fetch`、flex、grid、CSS 变量在 Android 4.0 的 WebKit 534 全部不可用，会白屏。
- **一个真实的 CSS 坑（已修）**：`#cols` 容器只有浮动子元素、又带 `overflow:hidden`（BFC）时，
  Chromium/WebKit 会把它的宽度按 shrink-to-fit 计算，三栏从 325px 塌成 148px、格子挤成 13px；
  显式写 `width:100%` 才恢复。页面里已加注释说明。`.caps` / `.gpurow` 同理，都要 `width:100%`。
- **信息架构参考 Pigsty `node-overview` Grafana 看板**（`files/grafana/node/node-overview.json`）：
  顶部一排 stat 小块（大数字 + 阈值色 + sparkline）→ 核心可视化 → 成对 timeseries → 表格。
  落地：7 个 stat 块（CPU/LOAD1/内存/磁盘/GPU/显存/温度）、CPU 总量历史曲线、网络 rx/tx 双序列曲线、
  存储空间 bar-gauge 表、TOP5 进程表、显存填充槽、系统信息表。
- **一个 JS 顺序坑（已修）**：`var g = d.gpu` 在 render 后段赋值，stat 块若放在它之前会拿到
  `undefined`（var 提升但未赋值）→ GPU/显存两块永远 "--"。图块块必须放在 GPU 数据段之后。
- **编译期 API 19 / 运行期 API 15**：`@JavascriptInterface` 注解是 API 17 才有的，因此 `javac` 用 `android-19` 的 `android.jar`，`aapt2 link --min-sdk-version 15`；代码本身只调用 4.0.3 就存在的 API。

---

## 3. 阶段计划

### 阶段 0 · 环境（已完成）
Windows 侧工具链全部本地化，不装 Android Studio/Gradle：

```
tools/platform-tools        adb 1.0.41 (v37.0.1)
tools/android-9             build-tools 28.0.3：aapt2、d8.jar、apksigner、zipalign、aapt
tools/android-4.0.4         API 15 android.jar（参考/回退用）
tools/android-4.4.2         API 19 android.jar（编译期实际使用）
C:\Program Files\Eclipse Adoptium\jdk-8.0.512.9-hotspot    Temurin JDK 8
```
步骤见 `docs/01-environment-setup.md`（含全部下载命令，可复现）。

### 阶段 1 · 服务器探针（已移除）
早期版本在服务器上跑过一个零依赖 HTTP 探针（`server_probe.py` + systemd 用户服务，8080）。
现已全部停止并删除（`~/hpscope` 一并清理）。当前服务器侧唯一改动是
`~/.ssh/authorized_keys` 里的一行 `restrict … hpscope-touchpad-app`；
采集脚本 `app/src/HpScope/assets/probe_remote.py` 每次轮询随 SSH exec 通道送入 `python3 -`，不落盘。

### 阶段 2 · TouchPad 端 APK（已完成）
`app/src/HpScope/` + `app/build.ps1` 一键：
`aapt2 compile → aapt2 link(生成 R.java) → javac → d8 --min-api 15 → aapt add → zipalign → apksigner`

### 阶段 3 · 设备侧（待接线）
1. 用 USB 接 TouchPad，装 ADB 驱动（Win10/11 一般自动识别为 "Palm, Inc"，不行就手动指定
   `tools/platform-tools` 附带的 Google USB Driver，或在设备管理器里右键更新驱动 → Android ADB Interface）。
2. `tools\platform-tools\adb.exe devices` 看到序列号后：
   ```
   adb install -r dist\HpScope.apk
   adb shell am start -n com.hpscope.mon/.MainActivity
   ```
   或 `powershell -File app\build.ps1 -Install`（构建+安装+启动一条龙）。
3. 应用启动后默认 SSH 到 `jd4090@<SERVER_IP>:22`；**菜单键（或长按屏幕 1.2 s）**可改主机/端口/用户名。
4. 想让 TouchPad 开机就跑监控：把它设为桌面/主页（设置 → 应用 → HpScope → 清除默认启动器后按 Home 选择并勾选「默认使用」），或装第三方启动器把它固定为首屏。

### 阶段 4 · 故障与兜底
- 页面显示 OFFLINE：先在电脑上跑
  `cd tools\ssh_test; java -cp ".;..\vendor\jsch-0.2.20-android.jar" TestSsh "..\..\app\src\HpScope\assets\hpscope_key" "..\..\app\src\HpScope\assets\probe_remote.py"`，
  能出 JSON 说明服务器与密钥都正常，问题在平板网络（TouchPad 的 Wi-Fi 可能不在 <SERVER_SUBNET>，
  服务器网卡实际是 <LAN_IP>，对外地址是路由器 NAT 进来的）。
- 服务器重启不需要额外动作：没有常驻服务要恢复，App 下次轮询会自动重连。
- 想看历史/大屏：用 `tools\make_ssh_preview.ps1` 生成 `docs\dashboard_ssh_preview.html`。

---

## 4. 风险与边界
- TouchPad 只有 1 GB 内存、1024×768 屏幕；HUD 用单页 + 2 s 轮询，无后台常驻服务，实测无卡顿风险（页面极轻）。
- 单页 ES5 是为了 4.0 兼容；若以后只跑 Android 7.1 Evervolv，可以升级到 flex/CSS 变量/箭头函数，但没必要。
- 若重刷 ROM：**务必先 CWM/TWRP 做 Nandroid 备份**；保留 moboot 双系统引导，webOS 仍可随时回去。
