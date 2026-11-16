# HPpad — HP TouchPad 服务器监控副屏

把老的 **HP TouchPad（tenderloin，Android 4.0+）** 变成一块实时展示
**<SERVER_IP>（jd4090 / Ubuntu 24.04）** 硬件状态的副屏。

思路参考 [`luziqing/MixMonolith`](https://github.com/luziqing/MixMonolith)：
宿主机零常驻守护、原生容器 + WebView HUD、免 Android Studio / Gradle 一键打包。

> **分支说明（`touchpad`）**：本分支是 HpScope 的完整源码 + 文档 + 本地脚本，
> **不含** `tools/` 里的 Android SDK / JDK / jar（约 300 MB，按 `docs/01-environment-setup.md` 自行放置）、
> `dist/` 构建产物，以及 APK 内置的 SSH 私钥 `app/src/HpScope/assets/hpscope_key`
> （用设置 →「重置密钥」生成自己的密钥对，公钥追加到服务器 `~/.ssh/authorized_keys`）。
> 服务器端不需要安装任何东西：`assets/svc_ctl.py` 与 `probe_remote.py` 每次随 SSH 通道用
> `python3 -` 送入执行，不落盘。

## 组成

```
app/src/HpScope/           Android 端（minSdk 15，API 15 老设备也能跑）
  AndroidManifest.xml      minSdk 15 / targetSdk 15 / 横屏 / 全屏 / 常亮
  java/com/hpscope/mon/    MainActivity + SshProbe（JSch）+ JS 桥（菜单键改 SSH 目标）
  assets/index.html        ES5 + WebKit 534 兼容的单页 HUD
  assets/probe_remote.py   随 SSH 通道送到服务器执行的只读采集脚本（不落盘）
  assets/hpscope_key    APK 内置身份（服务器已预授权，restrict）
  res/                     应用图标 / 字符串
app/build.ps1              aapt2 → javac → d8 → zipalign → apksigner 一键构建
docs/00-PLAN.md            总体规划（ROM 线、架构、阶段、风险）
docs/01-environment-setup.md  环境下载与踩坑记录
docs/RUNBOOK.md            A2 SSH 只读 / B 构建 / C TouchPad 安装 / D 备选
tools/                     adb + build-tools + android.jar + jsch-0.2.20-android.jar（本地工具链）
dist/HpScope.apk           构建产物（241 KB，已签名，含 SSH 传输层）
```

## 接入方式

只有一条通路：**APK 直连 SSH，只读拉取**。服务端除 `authorized_keys` 一行外不需要任何东西
（无脚本、无守护进程、无端口）。

SSH 模式下，采集脚本 `assets/probe_remote.py` 每次轮询随 exec 通道送入 `python3 -`，
只读 `/proc`、`/sys`、`nvidia-smi`，**不写服务器磁盘**；CPU/每核/网络的百分比在平板端
用累积计数的差值计算，所以丢一帧也不会让曲线失真。

APK 内置**已预授权**的 ECDSA 身份（`assets/hpscope_key`，服务器上那一行带 `restrict`：
禁端口转发/agent/X11/PTY），装完即连，不需要手动加公钥。想换成自己的密钥：设置 →「重置密钥」→
「公钥」→ 追加到 `~/.ssh/authorized_keys`。详见 `docs/RUNBOOK.md` 的 A2 节。

## 本地服务与启停（STORAGE / SENSORS 卡内的拟物圆盘）

服务按钮放在底部两张卡片的空白区：**STORAGE 里 2 个（QWEN·HQ / QWEN·Q8）、MOTHERBOARD SENSORS 里 3 个（ASR/TTS/MINERU）**。
拟物风格：径向渐变的圆盘 + 顶部高光 + 底座投影，按下有位移与触觉反馈。

- **灰盘 + ▶** = 未运行，点一下启动
- **绿盘 + ■** = 运行中（绿边+辉光），点一下进入“待确认”（红盘），3 秒内再点一次才停止（2 s 轮询不会抹掉红盘）
- **琥珀呼吸** = 操作中（命令已发出）：启动等到端口开始监听、停止等到端口释放才结束，90 s 只是兜底
- **彩色进度环**（圆盘外圈 2–3 px）：灰环 = 确定已停止；绿环满圈 = 确定运行中；琥珀环按加载时间填充
  （约 40–100 s 视服务而定，端口一监听立刻补满变绿）；停止时红环从满圈收缩，确认态是满圈红
  ——不用猜「到底起没起/停没停」，环满/环空就是答案

每次按下都会调用 Android `Vibrator`（轻触 + 桥内 22 ms 确认）；命令失败时给 35/70/35 ms 的短促双震。

三条服务按钮下方还有一条红色 **`■ STOP ALL · GPU`** 胶囊：点一下变亮红，文字变成 **`TAP AGAIN · STOP ALL`**
（3 s 内再点一次才执行，超时自动还原），执行中显示 `STOPPING…`；按端口顺序停掉 **5 个服务**里所有正在监听的实例——
先 ASR/TTS/MINERU，最后才是 9020/9022（慢的收尾放最后，避免通道超时把前面的都拖掉）——
结果用 `stopped: asr,tts` 这样的原文提示（APK 是 Toast，本地 harness 是页面底部浮层）。

| 按钮 | 端口 | 服务 / 模型 | 启动命令（服务器 `~/README.md` 同步） |
|---|---|---|---|
| `QWEN·HQ 9020` | 9020 | Qwen3.8-27B AWQ-W4A16 + HyperQwen（vLLM 0.31，生产） | `bash ~/qwen_service/serve_9020_hyperqwen.sh` |
| `QWEN·Q8 9022` | 9022 | Qwen3.8-27B UD-Q8_K_XL + mmproj-F16，262K ctx / KV q8_0（llama.cpp b12384，新主口） | `bash ~/qwen_service/serve_9022_qwen38.sh --start` |
| `ASR 13560` | 13560 | Qwen3-ASR-1.7B（sglang-omni） | `bash ~/serve_asr_13560.sh` |
| `TTS 13561` | 13561 | Qwen3-TTS-1.7B（sglang-omni） | `bash ~/serve_tts_13561.sh` |
| `MINERU 9038` | 9038 | MinerU api-server（tier advanced，vllm+torch） | `bash ~/serve_mineru_9038.sh` |

实现：按钮经 JS 桥调用 `assets/svc_ctl.py`（同样走 `python3 - <<`，**不落盘**），白名单 5 个 id；
停止顺序是「服务自带 `--stop` → pidfile → 端口精确 kill」，pidfile 里的 pid 先用 `/proc/<pid>/cmdline`
核对身份（防止 pid 复用误杀无关进程），停成功后删 pidfile；kill 只打进程树，不碰 ssh。
大模型加载要 1–2 分钟，期间按钮一直是琥珀「操作中」，端口一监听就变绿（不再固定 25 s 掉回灰盘）。
9020 / 9022 共用一张卡，一次只能跑一个：两个脚本都带端口 + 显存护栏（9020 门限 20 GB、9022 43 GB），
未达门限会被拒绝并在 Toast 里给出原因。8090 / 9021 / 8000 已废弃，页面也不再管它们。

9022 的权重是 `models/Qwen3.8-27B-GGUF-unsloth/`（UD-Q8_K_XL 31.46 GB + mmproj 0.93 GB + 可选 MTP 1.37 GB），
**三件没下全时按钮会失败**（脚本只查文件存在）；key 在 `~/qwen_service/qwen_9022.key`（首次启动自动生成），
日志 `qwen_service/qwen_9022.log`，pid `~/run/llama_9022.pid`。

2026-11-15 实测（APK 同一条链路 `python3 - <action> <id>`）：ASR 起 30 s / 停 2 s；TTS 起 42 s / 停 1 s；
QWEN·HQ 9020 起 32 s（`/health` 200）/ 停 3 s；STOP ALL 在 1 s 内停掉在监听的实例。
每次停止都会清掉 pidfile。

同一天用 `tools/preview_live_harness.py` 做了**真实点击联调**（浏览器按钮 → 本地 harness → SSH → jd4090）：
点 ASR 后 1.2 s 琥珀环 20°、11 s 时 104°、30.7 s 端口监听环满分绿；再点一次是满圈红，
第二次点击后 0.1 s 红环 354°，约 0.6 s 后端口释放、环归零。9022 的权重已下完
（31.46 GB + mmproj + MTP），服务侧此前已实际跑起来过（llama-server，占 42.4 GB）。

## 快速开发循环（默认方式）

> **除非明确要求，不要重建 APK。** 迭代只看效果：

```powershell
# 1) 编辑 app\src\HpScope\assets\index.html
# 2) 用真实 SSH 快照重新生成预览
powershell -ExecutionPolicy Bypass -File tools\make_ssh_preview.ps1
# 3) 看 docs\dashboard_ssh_preview.html（Review 窗格）
```

预览会采两次真实 SSH 快照，并在页面里以 2 s 间隔重放（历史曲线用合成漂移填满）。
只有你明确要求时，才跑 `powershell -File app\build.ps1` 重建并签名 APK。

构建期固定会跑 `tools\check_encoding.py`，一旦汉字被写成乱码直接中止构建。

```powershell
# 1) 构建 APK
cd C:\docker\HPpad
powershell -ExecutionPolicy Bypass -File app\build.ps1

# 2) 插上 TouchPad 后安装
powershell -ExecutionPolicy Bypass -File app\build.ps1 -Install

# 3) 首次运行无需配置：APK 内置的 ECDSA 密钥已在服务器预授权（restrict）
```

开发期看真实 SSH 数据的预览（不需要服务器探针）：

```powershell
powershell -ExecutionPolicy Bypass -File tools\make_ssh_preview.ps1
# -> docs\dashboard_ssh_preview.html（内嵌两次真实 SSH 快照 + 2 s 重放）
```

（可选）服务器端 HTTP 探针，只用于在电脑浏览器里看大屏：见 `docs/RUNBOOK.md` A 节。

## 界面结构（参考 Pigsty `node-overview` + hardviz Performance）

单屏 1024×768 三行卡片网格，全部本地 canvas/CSS 渲染，无外部资源：

| 行 | 内容 |
|---|---|
| **A（hero）** | CPU / RAM / GPU 三张卡，每张 2 个环表 + 60 点面积图 + caption（绝对用量写在小字里）；分指标配色：CPU 青绿、RAM 品红、GPU 琥珀 |
| **B** | USAGE GRAPHS（CPU/RAM/GPU 三序列，可点 chip 显隐）+ PROCESS 表（PID / 进程 / CPU 条 / % / 内存，top 6） |
| **C** | PER-CORE USAGE（24 条 `P0 ●── 1%`，三列）+ STORAGE 表 + MOTHERBOARD SENSORS 网格 + NETWORK & HOST（rx/tx 双线图、负载、架构/内核、探针信息） |
| **抬头** | 金色「◆ 数据中心 GPU 算力节点 jd4090」居中 + 规格参数带（CPU 型号/线程、GPU/显存、发行版、内存、UPTIME） |

离线时显示 OFFLINE 与错误原因；掉线超过 8 s 抬头变 STALE。
