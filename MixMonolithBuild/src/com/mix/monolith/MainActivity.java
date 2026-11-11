package com.mix.monolith;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import com.jcraft.jsch.ChannelExec;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.Session;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.Properties;

public class MainActivity extends Activity {

    private WebView webView;
    private volatile boolean isRunning = true;
    private Handler mainHandler = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;

    private static final String PREF_HOST = "ssh_host";
    private static final String PREF_PORT = "ssh_port";
    private static final String PREF_USER = "ssh_user";
    private static final String DEFAULT_HOST = "10.0.0.252";
    private static final int DEFAULT_PORT = 22;
    private static final String DEFAULT_USER = "R7000laptop";

    private static final String PROBE_COMMAND = 
        "powershell -NoProfile -Command \"& { " +
        "$p = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor; " +
        "$total = ($p | ? Name -eq '_Total').PercentProcessorTime; " +
        "$cores = ($p | ? Name -ne '_Total' | sort { [int]$_.Name }).PercentProcessorTime -join ','; " +
        "$os = Get-CimInstance Win32_OperatingSystem; " +
        "$sec = [int]((Get-Date) - $os.LastBootUpTime).TotalSeconds; " +
        "$gpu = (nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits); " +
        "Write-Output ('{0}|{1}|{2}|{3}|{4}|{5}' -f $total, $cores, $os.FreePhysicalMemory, $os.TotalVisibleMemorySize, $gpu, $sec) }\"";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("mix_prefs", Context.MODE_PRIVATE);

        // Fullscreen immersive
        hideSystemUI();

        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);

        webView.setWebViewClient(new WebViewClient());
        webView.addJavascriptInterface(new WebBridge(), "AndroidBridge");
        webView.loadUrl("file:///android_asset/index.html");

        setContentView(webView);

        startSshPollerThread();
    }

    private void hideSystemUI() {
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_FULLSCREEN
        );
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemUI();
        }
    }

    private void startSshPollerThread() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                while (isRunning) {
                    Session session = null;
                    try {
                        String host = prefs.getString(PREF_HOST, DEFAULT_HOST);
                        int port = prefs.getInt(PREF_PORT, DEFAULT_PORT);
                        String user = prefs.getString(PREF_USER, DEFAULT_USER);
                        if ("lzq".equalsIgnoreCase(user)) {
                            user = DEFAULT_USER;
                        }

                        android.util.Log.i("MixMonolith", "Attempting SSH connection to " + user + "@" + host + ":" + port);

                        JSch jsch = new JSch();

                        // Read packaged private key from assets
                        InputStream keyStream = getAssets().open("mix_rsa");
                        ByteArrayOutputStream baos = new ByteArrayOutputStream();
                        byte[] buffer = new byte[1024];
                        int len;
                        while ((len = keyStream.read(buffer)) != -1) {
                            baos.write(buffer, 0, len);
                        }
                        keyStream.close();
                        byte[] keyBytes = baos.toByteArray();

                        jsch.addIdentity("mix_rsa", keyBytes, null, null);

                        session = jsch.getSession(user, host, port);
                        Properties config = new Properties();
                        config.put("StrictHostKeyChecking", "no");
                        session.setConfig(config);
                        session.setTimeout(4000);
                        session.connect(5000);
                        android.util.Log.i("MixMonolith", "SSH Connected successfully!");

                        while (isRunning && session.isConnected()) {
                            ChannelExec channel = (ChannelExec) session.openChannel("exec");
                            channel.setCommand(PROBE_COMMAND);
                            InputStream in = channel.getInputStream();
                            channel.connect(4000);

                            ByteArrayOutputStream out = new ByteArrayOutputStream();
                            byte[] tmp = new byte[512];
                            while (true) {
                                while (in.available() > 0) {
                                    int i = in.read(tmp, 0, 512);
                                    if (i < 0) break;
                                    out.write(tmp, 0, i);
                                }
                                if (channel.isClosed()) {
                                    if (in.available() > 0) continue;
                                    break;
                                }
                                try { Thread.sleep(50); } catch (Exception ee) {}
                            }
                            channel.disconnect();

                            final String output = out.toString("UTF-8").trim();
                            if (output.contains("|")) {
                                mainHandler.post(new Runnable() {
                                    @Override
                                    public void run() {
                                        String clean = output.replace("\r", "").replace("\n", "").replace("'", "\\'");
                                        webView.evaluateJavascript("window.updateFromAndroid && window.updateFromAndroid('" + clean + "')", null);
                                    }
                                });
                            }

                            Thread.sleep(1500);
                        }
                    } catch (Exception e) {
                        android.util.Log.e("MixMonolith", "SSH loop exception: " + e.getMessage());
                        // Sleep and retry connection gracefully
                        try {
                            Thread.sleep(3000);
                        } catch (InterruptedException ie) {}
                    } finally {
                        if (session != null && session.isConnected()) {
                            session.disconnect();
                        }
                    }
                }
            }
        }).start();
    }

    public class WebBridge {
        @JavascriptInterface
        public String getHost() {
            return prefs.getString(PREF_HOST, DEFAULT_HOST);
        }

        @JavascriptInterface
        public void setHost(String ip) {
            prefs.edit().putString(PREF_HOST, ip).apply();
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        isRunning = false;
        if (webView != null) {
            webView.destroy();
        }
    }
}
