#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真机联调 harness：把浏览器里的 HUD 页面接到 jd4090 的 SSH 上。

预览页 docs/dashboard_ssh_preview.html 里的按钮是死的（没有 HpScopeBridge）。
本脚本起一个只监听 127.0.0.1 的小服务，用与 APK 相同的两条链路服务页面：

  GET  /probe.json  ->  ssh jd4090 python3 -          < assets/probe_remote.py   (2 s 轮询)
  POST /svc?action=start|stop|stopall&id=...          < assets/svc_ctl.py

页面里的圆盘因此可以真的启动/停止服务器服务，备用环（进度环）的
琥珀 -> 绿 / 红 -> 灰 也就能在浏览器里真实观察。

用法:
    python tools/preview_live_harness.py           # http://127.0.0.1:8099/
    python tools/preview_live_harness.py 8123

只读预览（不启停服务）仍用: powershell -File tools\\make_ssh_preview.ps1
"""
import json
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "app", "src", "HpScope", "assets", "index.html")
PROBE = os.path.join(ROOT, "app", "src", "HpScope", "assets", "probe_remote.py")
SVCC = os.path.join(ROOT, "app", "src", "HpScope", "assets", "svc_ctl.py")

SHIM = r"""
<script type="text/javascript">
(function () {
  window.__HP_URL__ = "/probe.json";
  var ACT = { start: 1, stop: 1, stopall: 1 };
  var ID = { llm9020: 1, llm9022: 1, asr: 1, tts: 1, mineru: 1, all: 1 };
  function hpToast(msg, ok) {
    var d = document.getElementById("hpToast");
    if (!d) {
      d = document.createElement("div");
      d.id = "hpToast";
      d.style.cssText = "position:fixed;left:50%;bottom:26px;-webkit-transform:translateX(-50%);transform:translateX(-50%);" +
        "max-width:78%;padding:7px 11px;border-radius:8px;background:rgba(6,10,16,.94);color:#cfe9f5;" +
        "border:1px solid rgba(47,230,160,.55);font:11px/1.45 monospace;z-index:9999;white-space:pre-wrap;pointer-events:none";
      document.body.appendChild(d);
    }
    d.style.borderColor = ok ? "rgba(47,230,160,.55)" : "rgba(255,93,108,.65)";
    d.textContent = msg;
    d.style.display = "block";
    clearTimeout(hpToast._t);
    hpToast._t = setTimeout(function () { d.style.display = "none"; }, 5000);
  }
  window.HpScopeBridge = {
    config: function () { return "/probe.json"; },
    ready: function () { },
    haptic: function () { },
    edit: function () { },
    svc: function (action, id) {
      if (!ACT[action] || !ID[id]) { return; }
      try {
        var x = new XMLHttpRequest();
        x.open("POST", "/svc?action=" + encodeURIComponent(action) + "&id=" + encodeURIComponent(id), true);
        x.onload = function () {
          hpToast(action + " " + id + " -> " + (x.responseText || ("HTTP " + x.status)), x.status === 200);
        };
        x.onerror = function () { hpToast(action + " " + id + " -> request failed", false); };
        x.send(null);
      } catch (e) { }
    }
  };
  function poll() {
    var x = new XMLHttpRequest();
    x.open("GET", "/probe.json", true);
    x.onreadystatechange = function () {
      if (x.readyState === 4 && x.status === 200) {
        try { window.__push(x.responseText); } catch (e) { }
      }
    };
    try { x.send(); } catch (e2) { }
    setTimeout(poll, 2000);
  }
  window.addEventListener("load", function () { setTimeout(poll, 150); });
})();
</script>
"""


def run_ssh(args, stdin_text, timeout):
    import subprocess
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "jd4090"] + args,
        input=stdin_text, capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[harness] " + (fmt % args), flush=True)

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(PAGE, encoding="utf-8") as fh:
                html = fh.read().replace("<head>", "<head>" + SHIM, 1)
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/probe.json":
            t0 = time.time()
            code, out, err = run_ssh(["python3 -"], open(PROBE, encoding="utf-8").read(), 30)
            print("[harness] probe rc=%d %.2fs %s" % (code, time.time() - t0, err[:120]), flush=True)
            if out.startswith("{"):
                self._send(200, out, "application/json")
            else:
                self._send(500, json.dumps({"error": "probe rc=%d %s" % (code, err[:200])}), "application/json")
            return
        if path == "/health":
            self._send(200, "ok", "text/plain")
            return
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        action = (q.get("action") or [""])[0]
        sid = (q.get("id") or [""])[0]
        if self.path.split("?")[0] != "/svc" or action not in ("start", "stop", "stopall") \
                or sid not in ("llm9020", "llm9022", "asr", "tts", "mineru", "all"):
            self._send(400, "bad request", "text/plain")
            return
        t0 = time.time()
        code, out, err = run_ssh(["python3 - %s %s" % (action, sid)],
                                 open(SVCC, encoding="utf-8").read(), 95)
        print("[harness] svc %s %s rc=%d %.2fs %s" % (action, sid, code, time.time() - t0, out[:160]), flush=True)
        self._send(200 if out.startswith("{") else 500, out or err, "application/json")


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    print("[harness] http://127.0.0.1:%d/  (ssh target jd4090, 按钮会真的启停服务)" % port, flush=True)
    QuietServer(("127.0.0.1", port), Handler).serve_forever()