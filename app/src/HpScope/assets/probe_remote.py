#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HpScope remote probe -- Linux only, strictly READ-ONLY.

Nothing is installed on the server: the TouchPad app pipes this file into
`python3 -` over an SSH exec channel and reads one JSON line back.
No files are written, no daemon, no packages.

Output schema is "raw counters": CPU / per-core / network are cumulative and
the app computes the deltas (so a missed poll never skews the percentages).
Only top-process CPU% is measured here, with a short in-process delta.
"""

import json
import os
import platform
import socket
import subprocess
import time

PAGE_KB = 4
try:
    PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024
except Exception:
    pass
CLK = 100
try:
    CLK = os.sysconf("SC_CLK_TCK")
except Exception:
    pass


def read(path, binary=False):
    try:
        with open(path, "rb" if binary else "r") as fh:
            return fh.read()
    except Exception:
        return None


def read_strip(path):
    v = read(path)
    return v.strip() if v is not None else None


# ---------------------------------------------------------------- cpu / cores
def cpu_raw():
    data = read("/proc/stat")
    if not data:
        return None, []
    total = idle = 0.0
    cores = []
    for line in data.splitlines():
        if line.startswith("cpu "):
            p = [float(x) for x in line.split()[1:]]
            idle = p[3] + (p[4] if len(p) > 4 else 0.0)
            total = sum(p)
        elif line.startswith("cpu") and line[3:4].isdigit():
            p = [float(x) for x in line.split()[1:]]
            cores.append([sum(p), p[3] + (p[4] if len(p) > 4 else 0.0)])
    return [total, idle], cores


# ------------------------------------------------------------------- memory
def memory():
    info = {}
    data = read("/proc/meminfo")
    if not data:
        return {}
    for line in data.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        try:
            info[k.strip()] = float(v.split()[0])
        except Exception:
            pass
    return {
        "total_kb": info.get("MemTotal", 0.0),
        "avail_kb": info.get("MemAvailable", info.get("MemFree", 0.0)),
        "swap_total_kb": info.get("SwapTotal", 0.0),
        "swap_free_kb": info.get("SwapFree", 0.0),
    }


# -------------------------------------------------------------------- disks
def disks():
    mounts = ["/"]
    data = read("/proc/mounts")
    if data:
        for line in data.splitlines():
            p = line.split()
            if len(p) > 2 and p[2] in ("ext4", "ext3", "xfs", "btrfs", "f2fs"):
                mounts.append(p[1])
    out, seen = [], set()
    for m in mounts:
        if m in seen:
            continue
        seen.add(m)
        try:
            st = os.statvfs(m)
        except Exception:
            continue
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        out.append({
            "mount": m,
            "fs": "auto",
            "total_gb": total / 1024.0 ** 3,
            "free_gb": free / 1024.0 ** 3,
        })
    return out


# ------------------------------------------------------------------ network
def net_raw():
    out = []
    data = read("/proc/net/dev")
    if not data:
        return out
    for line in data.splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        f = rest.split()
        try:
            out.append({"name": name.strip(),
                        "rx": int(f[0]), "tx": int(f[8])})
        except Exception:
            pass
    return out


# --------------------------------------------------------------------- misc
def loadavg():
    data = read("/proc/loadavg")
    if not data:
        return None
    p = data.split()
    return {"1": float(p[0]), "5": float(p[1]), "15": float(p[2])}


def uptime():
    data = read("/proc/uptime")
    return float(data.split()[0]) if data else 0.0


def distro():
    data = read("/etc/os-release")
    if not data:
        return None
    info = {}
    for line in data.splitlines():
        if "=" in line:
            k, v = line.rstrip("\n").split("=", 1)
            info[k.strip()] = v.strip().strip('"').strip("'")
    pretty = info.get("PRETTY_NAME")
    if not pretty:
        pretty = (info.get("NAME", "") + " " + info.get("VERSION_ID", "")).strip()
    return pretty or None


def cpu_model():
    data = read("/proc/cpuinfo")
    if data:
        for line in data.splitlines():
            if line.startswith(("model name", "Processor", "Hardware")):
                return line.split(":", 1)[1].strip()
    return ""


# ------------------------------------------------------------- temperatures
def sysfs(path):
    return read_strip(path)


def temperatures():
    cpu = None
    zones, fans = [], []
    base = "/sys/class/hwmon"
    try:
        for h in sorted(os.listdir(base)):
            d = os.path.join(base, h)
            dev = sysfs(os.path.join(d, "name")) or h
            for i in range(1, 10):
                val = sysfs(os.path.join(d, "temp%d_input" % i))
                if not val:
                    continue
                try:
                    c = int(val) / 1000.0
                except ValueError:
                    continue
                if c <= 0 or c > 150:
                    continue
                lbl = sysfs(os.path.join(d, "temp%d_label" % i)) or ("t%d" % i)
                zones.append({"name": ("%s %s" % (dev, lbl)).strip(), "c": round(c, 1)})
                if cpu is None and (dev in ("k10temp", "coretemp", "zenpower", "cpu_thermal")
                                    or "package" in lbl.lower() or lbl.lower() == "tctl"):
                    cpu = c
            for i in range(1, 6):
                v = sysfs(os.path.join(d, "fan%d_input" % i))
                if not v:
                    continue
                try:
                    rpm = int(v)
                except ValueError:
                    continue
                if rpm > 0 or "nvidia" in dev.lower():
                    # nvidia hwmon reads 0 rpm in zero-fan idle mode; still report it
                    fans.append({"name": "%s fan%d" % (dev, i), "rpm": rpm})
    except Exception:
        pass
    if cpu is None:
        tz = "/sys/class/thermal"
        try:
            for z in sorted(os.listdir(tz)):
                if not z.startswith("thermal_zone"):
                    continue
                v = sysfs(os.path.join(tz, z, "temp"))
                if not v:
                    continue
                try:
                    c = int(v) / 1000.0
                except ValueError:
                    continue
                if c <= 0 or c > 150:
                    continue
                t = sysfs(os.path.join(tz, z, "type")) or z
                zones.append({"name": t, "c": round(c, 1)})
                if cpu is None and t in ("x86_pkg_temp", "coretemp", "cpu-thermal", "soc_thermal"):
                    cpu = c
        except Exception:
            pass
    return {"cpu_c": round(cpu, 1) if cpu else None, "zones": zones, "fans": fans}


# ---------------------------------------------------------------------- gpu
def fnum(v):
    """nvidia-smi prints [N/A] / [Not Supported] for absent fields."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def gpu():
    try:
        p = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,memory.used,memory.total,fan.speed,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4)
        text = p.stdout.decode("utf-8", "ignore").strip()
        if p.returncode != 0 or not text:
            return None
        # the GPU name may itself contain a comma: split off the 6 known fields
        f = [x.strip() for x in text.splitlines()[0].split(",")]
        if len(f) < 7:
            return None
        name = ",".join(f[:-6])
        util, mu, mt, fan, temp, pw = f[-6:]
        return {
            "name": name,
            "util": float(util),
            "mem_used_mb": float(mu),
            "mem_total_mb": float(mt),
            "fan_pct": fnum(fan),       # percent; None when the card exposes no fan
            "temp": float(temp),
            "power_w": float(pw),
        }
    except Exception:
        return None


# ------------------------------------------------------------ top processes
def proc_ticks():
    out = {}
    try:
        pids = os.listdir("/proc")
    except Exception:
        return out
    for pid in pids:
        if not pid.isdigit():
            continue
        data = read("/proc/%s/stat" % pid, binary=True)
        if not data:
            continue
        try:
            text = data.decode("utf-8", "ignore")
            rp = text.rfind(")")
            comm = text[text.find("(") + 1:rp]
            f = text[rp + 2:].split()
            ticks = int(f[11]) + int(f[12])
            rss_kb = int(f[21]) * PAGE_KB
        except Exception:
            continue
        out[pid] = (comm, ticks, rss_kb)
    return out


def top_procs(window=0.35, n=6):
    first = proc_ticks()
    if not first:
        return []
    time.sleep(window)
    second = proc_ticks()
    rows = []
    budget = max(1.0, window * CLK)
    for pid, (comm, ticks, rss) in second.items():
        old = first.get(pid)
        if old is None:
            continue
        rows.append(((ticks - old[1]) / budget * 100.0, rss, pid, comm))
    rows.sort(reverse=True)
    out = []
    for cpu, rss, pid, comm in rows[:n]:
        cmd = comm
        raw = read("/proc/%s/cmdline" % pid, binary=True)
        if raw:
            t = raw.decode("utf-8", "ignore").replace("\x00", " ").strip()
            if t:
                cmd = t
        out.append({
            "pid": int(pid),
            "name": comm,
            "cmd": cmd[:60],
            "cpu": round(max(0.0, cpu), 1),
            "mem_gb": round(rss / 1024.0 / 1024.0, 2),
        })
    return out


# --------------------------------------------------------------- services
SERVICE_PORTS = [
    ("llm9020", 9020),
    ("llm9022", 9022),
    ("asr", 13560),
    ("tts", 13561),
    ("mineru", 9038),
]


def listening_ports():
    ports = set()
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        data = read(path)
        if not data:
            continue
        for line in data.splitlines()[1:]:
            f = line.split()
            if len(f) < 4 or f[3] != "0A":      # 0A = LISTEN
                continue
            try:
                ports.add(int(f[1].split(":")[1], 16))
            except Exception:
                pass
    return ports


def main():
    cpu, cores = cpu_raw()
    snap = {
        "ts": time.time(),
        "host": socket.gethostname(),
        "os": "%s %s" % (platform.system(), platform.release()),
        "distro": distro(),
        "arch": platform.machine(),
        "cpu_model": cpu_model(),
        "cpu_cores": os.cpu_count() or 1,
        "cpu": cpu,
        "cores": cores,
        "mem": memory(),
        "disks": disks(),
        "net": net_raw(),
        "load": loadavg(),
        "gpu": gpu(),
        "temp": temperatures(),
        "top": top_procs(),
        "uptime_sec": int(uptime()),
    }
    # second CPU sample: the process table above already cost ~0.35 s, so the
    # app can render a real first frame without waiting for the next poll.
    cpu2, cores2 = cpu_raw()
    snap["cpu2"] = cpu2
    snap["cores2"] = cores2
    snap["ts2"] = time.time()
    up = listening_ports()
    snap["services"] = [{"id": sid, "port": p, "up": p in up} for sid, p in SERVICE_PORTS]
    print(json.dumps(snap, separators=(",", ":")))


if __name__ == "__main__":
    main()