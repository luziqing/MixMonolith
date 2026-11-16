package com.hpscope.mon;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.ProgressDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.DialogInterface;
import android.content.SharedPreferences;
import android.os.AsyncTask;
import android.os.Bundle;
import android.os.Handler;
import android.os.PowerManager;
import android.os.Vibrator;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;

/**
 * HpScope - HP TouchPad (tenderloin, Android 4.0+) server telemetry display.
 *
 * The app is the whole client: it logs in over SSH with an RSA key that it
 * generates on the device, runs a read-only probe script through `python3 -`
 * (the script only travels over the channel, it is never written to disk on
 * the server) and feeds the raw JSON into assets/index.html, which computes the
 * deltas and renders the dashboard. No daemon or package is installed on the
 * monitored host - only one authorized_keys line.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "hpscope";
    private static final String KEY_HOST = "ssh_host";
    private static final String KEY_PORT = "ssh_port";
    private static final String KEY_USER = "ssh_user";
    private static final String KEY_INTERVAL = "probe_interval";

    private static final String DEFAULT_HOST = "192.168.1.100";
    private static final int DEFAULT_PORT = 22;
    private static final String DEFAULT_USER = "jd4090";
    private static final java.util.regex.Pattern SAFE =
            java.util.regex.Pattern.compile("^[a-z0-9]{1,16}$");

    private WebView web;
    private Handler handler;
    private PollTask pollTask;
    private PowerManager.WakeLock wakeLock;
    private Vibrator vibrator;

    private String host = DEFAULT_HOST;
    private int port = DEFAULT_PORT;
    private String user = DEFAULT_USER;
    private long intervalMs = 2000L;

    private String keyPath;
    private String script;
    private String svcScript;
    private SshProbe probe;
    private boolean running;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_FULLSCREEN);
        setTitle("");

        SharedPreferences sp = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        host = sp.getString(KEY_HOST, DEFAULT_HOST);
        port = sp.getInt(KEY_PORT, DEFAULT_PORT);
        user = sp.getString(KEY_USER, DEFAULT_USER);
        intervalMs = sp.getLong(KEY_INTERVAL, 2000L);
        keyPath = new File(getFilesDir(), "hpscope_ecdsa").getAbsolutePath();

        script = loadAsset("probe_remote.py");
        svcScript = loadAsset("svc_ctl.py");

        web = new WebView(this);
        web.setScrollBarStyle(View.SCROLLBARS_INSIDE_OVERLAY);
        WebSettings ws = web.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDefaultTextEncodingName("utf-8");
        ws.setUseWideViewPort(false);
        ws.setLoadWithOverviewMode(false);
        ws.setCacheMode(WebSettings.LOAD_NO_CACHE);
        ws.setBuiltInZoomControls(false);
        ws.setSupportZoom(false);
        web.addJavascriptInterface(new Bridge(), "HpScopeBridge");
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");

        handler = new Handler();
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.SCREEN_BRIGHT_WAKE_LOCK, "hpscope:monitor");
        vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);

        prepareKey(false);
    }

    private String loadAsset(String name) {
        try {
            InputStream in = getAssets().open(name);
            ByteArrayOutputStream out = new ByteArrayOutputStream(16384);
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            in.close();
            return new String(out.toByteArray(), "UTF-8");
        } catch (Exception e) {
            return null;
        }
    }

    /** Creates the ECDSA identity if needed, then (optionally) shows the pubkey. */
    private void prepareKey(final boolean showAfter) {
        new Thread(new Runnable() {
            public void run() {
                String message = null;
                try {
                    keyPath = SshProbe.installKey(MainActivity.this, getFilesDir());
                } catch (Exception e) {
                    message = e.getClass().getSimpleName() + ": " + e.getMessage();
                }
                final String err = message;
                runOnUiThread(new Runnable() {
                    public void run() {
                        if (err != null) {
                            Toast.makeText(MainActivity.this, "密钥生成失败: " + err,
                                    Toast.LENGTH_LONG).show();
                        } else if (showAfter) {
                            showPublicKey();
                        }
                    }
                });
            }
        }, "hpscope-keygen").start();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (!wakeLock.isHeld()) {
            wakeLock.acquire();
        }
        running = true;
        handler.postDelayed(poll, 400);
    }

    @Override
    protected void onPause() {
        super.onPause();
        running = false;
        handler.removeCallbacks(poll);
        if (pollTask != null) {
            pollTask.cancel(true);
            pollTask = null;
        }
        if (probe != null) {
            probe.close();
            probe = null;
        }
        if (wakeLock.isHeld()) {
            wakeLock.release();
        }
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(poll);
        if (probe != null) {
            probe.close();
        }
        web.destroy();
        super.onDestroy();
    }

    /** Menu key / long press anywhere -> settings. */
    @Override
    public boolean onKeyDown(int keyCode, android.view.KeyEvent event) {
        if (keyCode == android.view.KeyEvent.KEYCODE_MENU) {
            showSettings();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public boolean onCreateOptionsMenu(android.view.Menu menu) {
        showSettings();
        return true;
    }

    /** Kept for API < 11 devices (menu soft-key behaviour). */
    @Override
    public boolean onKeyLongPress(int keyCode, android.view.KeyEvent event) {
        if (keyCode == android.view.KeyEvent.KEYCODE_MENU) {
            showSettings();
            return true;
        }
        return super.onKeyLongPress(keyCode, event);
    }

    private final Runnable poll = new Runnable() {
        public void run() {
            if (!running) {
                return;
            }
            if (pollTask == null || pollTask.getStatus() == AsyncTask.Status.FINISHED) {
                pollTask = new PollTask();
                pollTask.execute();
            }
            handler.postDelayed(this, intervalMs);
        }
    };

    private SshProbe probe() {
        if (probe == null) {
            probe = new SshProbe(host, port, user, keyPath, script, svcScript);
        }
        return probe;
    }

    private class PollTask extends AsyncTask<Void, Void, String> {
        private String error;

        @Override
        protected String doInBackground(Void... ignored) {
            if (script == null || script.length() == 0) {
                error = "probe_remote.py missing from assets";
                return null;
            }
            try {
                return probe().poll();
            } catch (Exception e) {
                error = e.getClass().getSimpleName() + ": " + e.getMessage();
                return null;
            }
        }

        @Override
        protected void onPostExecute(String result) {
            if (result == null) {
                push("{\"error\":\"ssh decode failed (" + esc(error) + ")\"}");
                return;
            }
            push(result);
        }
    }

    private void push(String json) {
        if (web == null) {
            return;
        }
        web.loadUrl("javascript:window.__push(" + jsString(json) + ")");
    }

    /** JSON text -> safe JS string literal (handles ", \, newlines, U+2028/9). */
    private static String jsString(String s) {
        if (s == null) {
            return "null";
        }
        StringBuilder sb = new StringBuilder(s.length() + 16).append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                case '\b': sb.append("\\b"); break;
                case '\f': sb.append("\\f"); break;
                case '\u2028': sb.append("\\u2028"); break;
                case '\u2029': sb.append("\\u2029"); break;
                default:   sb.append(c);
            }
        }
        return sb.append('"').toString();
    }

    private static String esc(String s) {
        return s == null ? "?" : s.replace("\"", "'").replace("\n", " ");
    }

    /** 0 = press tick, 1 = action failed. */
    private void buzz(int kind) {
        if (vibrator == null) {
            return;
        }
        try {
            if (kind == 1) {
                vibrator.vibrate(new long[]{0, 35, 70, 35}, -1);
            } else {
                vibrator.vibrate(22);
            }
        } catch (Exception ignored) {
        }
    }

    private static String svcName(String id) {
        if ("llm9020".equals(id)) { return "QWEN·HQ"; }
        if ("llm9022".equals(id)) { return "QWEN·Q8"; }
        if ("asr".equals(id)) { return "ASR"; }
        if ("tts".equals(id)) { return "TTS"; }
        if ("mineru".equals(id)) { return "MINERU"; }
        if ("all".equals(id)) { return "全部服务"; }
        return id;
    }

    /** svc_ctl.py 的 JSON 回包 -> 一行中文，不把原始 JSON 甩给用户。 */
    private static String prettySvc(String raw) {
        try {
            org.json.JSONObject o = new org.json.JSONObject(raw);
            boolean ok = o.optBoolean("ok", false);
            String id = o.optString("id", "");
            String action = o.optString("action", "");
            String msg = o.optString("msg", "").trim();
            String name = svcName(id);
            if (!ok) {
                return "✗ " + name + "：" + (msg.length() > 0 ? msg : "命令失败");
            }
            if ("start".equals(action)) {
                if (msg.startsWith("spawned pid ")) {
                    return "▶ " + name + " 启动中（pid " + msg.substring(12) + "）";
                }
                if (msg.startsWith("listening")) {
                    return "▶ " + name + " 已在运行";
                }
                return "▶ " + name + " 启动中";
            }
            if ("stop".equals(action)) {
                return "■ " + name + " 已停止";
            }
            if ("stopall".equals(action)) {
                if (msg.startsWith("stopped: ")) {
                    String list = msg.substring(9).trim();
                    if ("nothing was running".equals(list)) {
                        return "■ 没有服务在运行";
                    }
                    return "■ 已停止：" + list.replace(",", "、");
                }
                return "■ " + (msg.length() > 0 ? msg : "已执行");
            }
            return msg.length() > 0 ? msg : "完成";
        } catch (Exception e) {
            return raw.length() > 120 ? raw.substring(0, 120) : raw;
        }
    }

    /** Bridge exposed to the page: the page calls HpScopeBridge.ready() / config(). */
    private class Bridge {

        @JavascriptInterface
        public void ready() {
            push("{\"bridge\":true,\"interval\":" + intervalMs + "}");
        }

        @JavascriptInterface
        public String config() {
            return "ssh://" + user + "@" + host + ":" + port;
        }

        /** Called from the page when it wants fresh data immediately. */
        @JavascriptInterface
        public void refresh() {
            handler.post(poll);
        }

        /** Light haptic tick for disc presses. */
        @JavascriptInterface
        public void haptic(int ms) {
            if (vibrator == null) {
                return;
            }
            try {
                vibrator.vibrate(Math.max(5, Math.min(60, ms)));
            } catch (Exception ignored) {
            }
        }

        /** Start/stop a whitelisted local service (llm9020, llm9022, asr, tts, mineru). */
        @JavascriptInterface
        public void svc(final String action, final String id) {
            if (action == null || id == null
                    || !SAFE.matcher(action).matches() || !SAFE.matcher(id).matches()) {
                return;
            }
            buzz(0);
            new Thread(new Runnable() {
                public void run() {
                    String msg;
                    try {
                        msg = probe().svc(action, id);
                    } catch (Exception e) {
                        msg = "{\"ok\":false,\"msg\":\"" + esc(e.getMessage()) + "\"}";
                    }
                    final String m = msg;
                    final boolean ok = m.indexOf("\"ok\": true") >= 0 || m.indexOf("\"ok\":true") >= 0;
                    if (!ok) {
                        buzz(1);
                    }
                    runOnUiThread(new Runnable() {
                        public void run() {
                            Toast t = Toast.makeText(MainActivity.this, prettySvc(m), Toast.LENGTH_SHORT);
                            // top edge: a bottom toast covers the STOP ALL capsule for seconds
                            t.setGravity(Gravity.TOP | Gravity.CENTER_HORIZONTAL, 0, 56);
                            t.show();
                        }
                    });
                    handler.post(poll);
                }
            }, "hpscope-svc").start();
        }

        /** Called from the page so a long press opens the settings dialog. */
        @JavascriptInterface
        public void edit() {
            runOnUiThread(new Runnable() {
                public void run() {
                    showSettings();
                }
            });
        }
    }

    // ------------------------------------------------------------------ settings

    private void showSettings() {
        final float d = getResources().getDisplayMetrics().density;
        int pad = (int) (12 * d);

        final EditText inHost = new EditText(this);
        inHost.setInputType(InputType.TYPE_CLASS_TEXT);
        inHost.setHint(getString(R.string.server_host));
        inHost.setText(host);
        inHost.setSelectAllOnFocus(true);

        final EditText inPort = new EditText(this);
        inPort.setInputType(InputType.TYPE_CLASS_NUMBER);
        inPort.setHint("22");
        inPort.setText("" + port);

        final EditText inUser = new EditText(this);
        inUser.setInputType(InputType.TYPE_CLASS_TEXT);
        inUser.setHint("jd4090");
        inUser.setText(user);

        final TextView keyState = new TextView(this);
        keyState.setPadding(0, (int) (6 * d), 0, (int) (6 * d));
        keyState.setText(new File(keyPath).exists() ? getString(R.string.key_ready) : getString(R.string.key_missing));

        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);
        buttons.setPadding(0, (int) (4 * d), 0, 0);

        Button bKey = new Button(this);
        bKey.setText(getString(R.string.key_gen));
        bKey.setTextSize(12);
        Button bPub = new Button(this);
        bPub.setText(getString(R.string.key_show));
        bPub.setTextSize(12);
        Button bTest = new Button(this);
        bTest.setText(getString(R.string.test));
        bTest.setTextSize(12);
        buttons.addView(bKey, new LinearLayout.LayoutParams(0, -2, 1));
        buttons.addView(bPub, new LinearLayout.LayoutParams(0, -2, 1));
        buttons.addView(bTest, new LinearLayout.LayoutParams(0, -2, 1));

        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(pad, pad, pad, pad);
        box.addView(inHost);
        box.addView(inPort);
        box.addView(inUser);
        box.addView(keyState);
        box.addView(buttons);

        final AlertDialog dlg = new AlertDialog.Builder(this)
                .setTitle(R.string.ssh_target)
                .setView(box)
                .setPositiveButton(R.string.ok, new DialogInterface.OnClickListener() {
                    public void onClick(DialogInterface di, int which) {
                        String h = inHost.getText().toString().trim();
                        String u = inUser.getText().toString().trim();
                        int p;
                        try {
                            p = Integer.parseInt(inPort.getText().toString().trim());
                        } catch (Exception e) {
                            p = DEFAULT_PORT;
                        }
                        if (h.length() == 0) {
                            h = DEFAULT_HOST;
                        }
                        if (u.length() == 0) {
                            u = DEFAULT_USER;
                        }
                        if (p <= 0 || p > 65535) {
                            p = DEFAULT_PORT;
                        }
                        host = h;
                        port = p;
                        user = u;
                        getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                                .putString(KEY_HOST, host)
                                .putInt(KEY_PORT, port)
                                .putString(KEY_USER, user)
                                .commit();
                        probe = null;
                        pollTask = null;
                        handler.post(poll);
                    }
                })
                .setNegativeButton(R.string.cancel, null)
                .create();

        bKey.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle(R.string.key_regen)
                        .setMessage(R.string.key_regen_msg)
                        .setPositiveButton(R.string.ok, new DialogInterface.OnClickListener() {
                            public void onClick(DialogInterface di, int which) {
                                new File(keyPath).delete();
                                prepareKey(true);
                            }
                        })
                        .setNegativeButton(R.string.cancel, null)
                        .show();
            }
        });
        bPub.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                showPublicKey();
            }
        });
        bTest.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                String h = inHost.getText().toString().trim();
                String u = inUser.getText().toString().trim();
                int p;
                try {
                    p = Integer.parseInt(inPort.getText().toString().trim());
                } catch (Exception e) {
                    p = DEFAULT_PORT;
                }
                testTarget(h.length() == 0 ? DEFAULT_HOST : h,
                        p <= 0 || p > 65535 ? DEFAULT_PORT : p,
                        u.length() == 0 ? DEFAULT_USER : u);
            }
        });

        dlg.show();
    }

    private void testTarget(final String h, final int p, final String u) {
        final ProgressDialog prog = ProgressDialog.show(this, "", getString(R.string.test) + " ...", true);
        new Thread(new Runnable() {
            public void run() {
                String msg;
                try {
                    SshProbe t = new SshProbe(h, p, u, keyPath, script, svcScript);
                    String json = t.poll();
                    t.close();
                    msg = "OK " + json.length() + " B  " + json.substring(0, Math.min(90, json.length()));
                } catch (Exception e) {
                    msg = "FAILED  " + e.getClass().getSimpleName() + ": " + e.getMessage();
                }
                final String out = msg;
                runOnUiThread(new Runnable() {
                    public void run() {
                        prog.dismiss();
                        Toast.makeText(MainActivity.this, out, Toast.LENGTH_LONG).show();
                    }
                });
            }
        }, "hpscope-test").start();
    }

    private void showPublicKey() {
        String line;
        try {
            line = SshProbe.publicKeyLine(getFilesDir());
        } catch (Exception e) {
            line = null;
        }
        if (line == null) {
            Toast.makeText(this, getString(R.string.key_missing), Toast.LENGTH_LONG).show();
            return;
        }
        final String pub = line;
        TextView tv = new TextView(this);
        int pad = (int) (12 * getResources().getDisplayMetrics().density);
        tv.setPadding(pad, pad, pad, pad);
        tv.setTextSize(11);
        tv.setTextIsSelectable(true);
        tv.setGravity(Gravity.CENTER_HORIZONTAL);
        tv.setText(pub);
        new AlertDialog.Builder(this)
                .setTitle(R.string.key_pub_title)
                .setView(tv)
                .setPositiveButton(R.string.copy, new DialogInterface.OnClickListener() {
                    public void onClick(DialogInterface di, int which) {
                        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                        cm.setPrimaryClip(ClipData.newPlainText("hpscope key", pub));
                        Toast.makeText(MainActivity.this, getString(R.string.copied), Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton(R.string.cancel, null)
                .show();
    }
}