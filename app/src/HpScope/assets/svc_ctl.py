#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HpScope service control -- start/stop the local model services on jd4090.

Runs as the SSH user; nothing is installed. The TouchPad pipes this file into
`python3 - <action> <id>` and reads one JSON line back.

    actions: start | stop | status | stopall
    ids:     llm9020 | llm9022 | asr | tts | mineru

Only commands documented in ~/README.md are used; every id is whitelisted.
"""

import json
import os
import signal
import subprocess
import sys
import time

HOME = "/home/jd4090"

SERVICES = {
    "llm9020": {
        "port": 9020,
        "label": "Qwen3.8-27B HyperQwen (vLLM)",
        "start": "cd ~/qwen_service && bash serve_9020_hyperqwen.sh",
        "stop": "bash ~/qwen_service/serve_9020_hyperqwen.sh --stop",
        "log": HOME + "/qwen_service/hyperqwen_9020.log",
        "pid": HOME + "/qwen_service/hyperqwen_9020.pid",
        "match": "vllm",
    },
    "llm9022": {
        "port": 9022,
        "label": "Qwen3.8-27B UD-Q8 (llama.cpp)",
        "start": "cd ~/qwen_service && bash serve_9022_qwen38.sh --start",
        "stop": "bash ~/qwen_service/serve_9022_qwen38.sh --stop",
        "log": HOME + "/qwen_service/qwen_9022.log",
        "pid": HOME + "/run/llama_9022.pid",
        "match": "llama-server",
    },
    "asr": {
        "port": 13560,
        "label": "Qwen3-ASR-1.7B",
        "start": "bash ~/serve_asr_13560.sh",
        "stop": None,
        "log": HOME + "/sglang_omni_asr_13560.log",
        "pid": HOME + "/run/asr_13560.pid",
        "match": "sgl-omni",
    },
    "tts": {
        "port": 13561,
        "label": "Qwen3-TTS-1.7B",
        "start": "bash ~/serve_tts_13561.sh",
        "stop": None,
        "log": HOME + "/sglang_omni_tts_13561.log",
        "pid": HOME + "/run/tts_13561.pid",
        "match": "sgl-omni",
    },
    "mineru": {
        "port": 9038,
        "label": "MinerU api-server",
        "start": "bash ~/serve_mineru_9038.sh",
        "stop": None,
        "log": HOME + "/mineru_9038.log",
        "pid": HOME + "/run/mineru_9038.pid",
        "match": "mineru",
    },
    }

# Fast services first: a slow 9020/9022 teardown must never eat the SSH
# channel timeout before ASR/TTS/MinerU have been stopped.
STOP_ORDER = ("asr", "tts", "mineru", "llm9020", "llm9022")


def listening(port):
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as fh:
                next(fh)
                for line in fh:
                    f = line.split()
                    if len(f) > 3 and f[3] == "0A" and int(f[1].split(":")[1], 16) == port:
                        return True
        except Exception:
            pass
    return False


def pid_on_port(port):
    try:
        out = subprocess.run(["ss", "-ltnp", "sport = :%d" % port],
                             capture_output=True, text=True, timeout=5).stdout
        for tok in out.replace(",", " ").split():
            if tok.startswith("pid="):
                return int(tok[4:])
    except Exception:
        pass
    return None


def tail(path, n=3):
    try:
        with open(path, "r", errors="ignore") as fh:
            lines = fh.readlines()[-n:]
        return " ".join(x.strip() for x in lines)[-300:]
    except Exception:
        return ""


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmdline(pid):
    """/proc/<pid>/cmdline as text; None when the pid is gone."""
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            return fh.read().replace(b"\x00", b" ").decode("utf-8", "ignore").strip()
    except Exception:
        return None


def pidfile_pid(svc):
    """pid from the pidfile, only when it still names this service."""
    path = svc.get("pid")
    if not path:
        return None
    try:
        with open(path) as fh:
            pid = int(fh.read().strip())
    except Exception:
        return None
    if pid <= 1 or pid == os.getpid():
        return None
    line = cmdline(pid)
    if not line:
        return None
    if svc.get("match") and svc["match"] not in line:
        return None          # pid was recycled by an unrelated process
    return pid


def drop_pidfile(svc, killed=None):
    """Remove the pidfile once the process it names is gone."""
    path = svc.get("pid")
    if not path:
        return
    try:
        with open(path) as fh:
            cur = int(fh.read().strip())
    except Exception:
        return
    if killed and cur in killed:
        pass                 # we just killed it
    elif cmdline(cur) is not None:
        return               # still a live process -- keep the record
    try:
        os.unlink(path)
    except OSError:
        pass


def descendants(pid):
    """All live child pids of pid (sgl-omni spawns pipeline stages as children)."""
    children = {}
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open("/proc/%s/stat" % entry) as fh:
                    data = fh.read()
                rp = data.rfind(")")
                ppid = int(data[rp + 2:].split()[1])
                children.setdefault(ppid, []).append(int(entry))
            except Exception:
                continue
    except Exception:
        return []
    out, stack = [], [pid]
    while stack:
        cur = stack.pop()
        for kid in children.get(cur, []):
            stack.append(kid)
            out.append(kid)
    return out


def do_start(svc):
    log = svc["log"]
    drop_pidfile(svc)
    with open(log, "ab") as fh:
        fh.write(("\n=== HpScope start %s ===\n" % time.strftime("%F %T")).encode())
        fh.flush()
        proc = subprocess.Popen(
            ["bash", "-lc", svc["start"]],
            cwd=HOME, stdout=fh, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    # give the guard scripts ~1.5 s to reject (port busy / low VRAM)
    time.sleep(1.5)
    if listening(svc["port"]):
        return True, "listening already"
    if proc.poll() is not None:
        return False, "exited %d: %s" % (proc.returncode, tail(log))
    return True, "spawned pid %d" % proc.pid


def do_stop(svc):
    port = svc["port"]
    if svc.get("stop"):
        # the service's own --stop: pidfile -> port -> VRAM back to idle
        try:
            subprocess.run(["bash", "-lc", svc["stop"]], timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass             # the tree kill below is the fallback
    pid = pidfile_pid(svc)
    if pid is None:
        pid = pid_on_port(port)
    killed = set()
    if pid:
        # the launch used start_new_session, so kill the whole tree: signalling
        # only the parent leaves sgl-omni stage workers holding GPU memory
        targets = descendants(pid) + [pid]
        for p in targets:
            try:
                os.kill(p, signal.SIGTERM)
                killed.add(p)
            except Exception:
                pass
        for _ in range(20):
            time.sleep(0.5)
            if not listening(port) and not any(alive(p) for p in targets):
                break
        for p in targets:
            if alive(p):
                try:
                    os.kill(p, signal.SIGKILL)
                    killed.add(p)
                except Exception:
                    pass
    for _ in range(10):
        if not listening(port):
            drop_pidfile(svc, killed)
            return True, "stopped"
        time.sleep(0.3)
    return False, "port %d still listening" % port


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "msg": "usage: <start|stop|status> <id>"}))
        return
    action, sid = sys.argv[1], sys.argv[2]
    if action == "stopall":
        done, failed = [], []
        for key in STOP_ORDER:
            item = SERVICES[key]
            if not listening(item["port"]):
                continue
            try:
                ok, _ = do_stop(item)
            except Exception as exc:
                ok = False
                sys.stderr.write("%s: %s\n" % (key, exc))
            (done if ok else failed).append(key)
        msg = "stopped: " + (",".join(done) if done else "nothing was running")
        if failed:
            msg += " | failed: " + ",".join(failed)
        print(json.dumps({"ok": not failed, "id": "all", "action": "stopall", "msg": msg}))
        return
    svc = SERVICES.get(sid)
    if not svc:
        print(json.dumps({"ok": False, "msg": "unknown id"}))
        return
    if action == "status":
        print(json.dumps({"ok": True, "id": sid, "up": listening(svc["port"])}))
        return
    try:
        if action == "start":
            ok, msg = do_start(svc)
        elif action == "stop":
            ok, msg = do_stop(svc)
        else:
            ok, msg = False, "unknown action"
    except Exception as exc:
        ok, msg = False, "%s: %s" % (type(exc).__name__, exc)
    print(json.dumps({"ok": ok, "id": sid, "action": action, "msg": msg}))


if __name__ == "__main__":
    main()