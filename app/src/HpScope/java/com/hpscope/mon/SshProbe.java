package com.hpscope.mon;

import com.jcraft.jsch.ChannelExec;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.KeyPair;
import com.jcraft.jsch.Session;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

/**
 * Read-only SSH probe transport.
 *
 * Holds one JSch session to the monitored server and, on every poll, sends the
 * embedded probe script as `python3 - <<'HPSCOPE_PY' ... HPSCOPE_PY` inside an
 * exec channel. Standard output is the raw metric JSON.
 *
 * Nothing is installed on the server: no files are written, no daemon runs.
 * The only server-side footprint is one line in ~/.ssh/authorized_keys.
 */
final class SshProbe {

    static final int CONNECT_TIMEOUT_MS = 10000;
    static final int POLL_TIMEOUT_MS = 20000;

    private final String host;
    private final int port;
    private final String user;
    private final String keyPath;
    private final String script;
    private final String svcScript;

    private Session session;

    SshProbe(String host, int port, String user, String keyPath, String script, String svcScript) {
        this.host = host;
        this.port = port;
        this.user = user;
        this.keyPath = keyPath;
        this.script = script;
        this.svcScript = svcScript;
    }

    /**
     * Installs the shipped identity (assets/hpscope_key, already authorised on
     * the server) into app-private storage; falls back to on-device generation
     * when the asset is missing.
     */
    static String installKey(Context ctx, File dir) throws Exception {
        File key = new File(dir, "hpscope_key");
        if (key.exists() && key.length() > 0) {
            return key.getAbsolutePath();
        }
        InputStream in = null;
        FileOutputStream out = null;
        try {
            in = ctx.getAssets().open("hpscope_key");
            out = new FileOutputStream(key);
            byte[] buf = new byte[2048];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
        } catch (Exception missing) {
            key.delete();
        } finally {
            try { if (in != null) in.close(); } catch (Exception ignored) { }
            try { if (out != null) out.close(); } catch (Exception ignored) { }
        }
        if (key.exists() && key.length() > 0) {
            return key.getAbsolutePath();
        }
        return ensureKey(dir);
    }

    /** Generates an RSA-3072 key on first use (old ROMs lack EC AlgorithmParameters). */
    static String ensureKey(File dir) throws Exception {
        File key = new File(dir, "hpscope_key");
        if (key.exists() && key.length() > 0) {
            return key.getAbsolutePath();
        }
        JSch jsch = new JSch();
        KeyPair kp = KeyPair.genKeyPair(jsch, KeyPair.RSA, 3072);
        kp.writePrivateKey(key.getAbsolutePath());
        kp.dispose();
        if (!key.exists() || key.length() == 0) {
            throw new Exception("key generation produced no file");
        }
        return key.getAbsolutePath();
    }

    /** authorized_keys line for the generated key. */
    static String publicKeyLine(File dir) throws Exception {
        File key = new File(dir, "hpscope_key");
        if (!key.exists()) {
            return null;
        }
        JSch jsch = new JSch();
        KeyPair kp = KeyPair.load(jsch, key.getAbsolutePath());
        if (kp == null) {
            return null;
        }
        byte[] blob = kp.getPublicKeyBlob();
        kp.dispose();
        if (blob == null || blob.length < 4) {
            return null;
        }
        // SSH wire format: uint32 length + type name ("ssh-rsa", "ecdsa-sha2-nistp256", ...)
        int len = ((blob[0] & 0xff) << 24) | ((blob[1] & 0xff) << 16)
                | ((blob[2] & 0xff) << 8) | (blob[3] & 0xff);
        if (len <= 0 || len > blob.length - 4) {
            return null;
        }
        String type = new String(blob, 4, len, "UTF-8");
        return type + " "
                + android.util.Base64.encodeToString(blob, android.util.Base64.NO_WRAP)
                + " hpscope-touchpad";
    }

    synchronized void close() {
        if (session != null) {
            try {
                session.disconnect();
            } catch (Exception ignored) {
            }
            session = null;
        }
    }

    private Session session() throws Exception {
        if (session != null && session.isConnected()) {
            return session;
        }
        close();
        JSch jsch = new JSch();
        jsch.addIdentity(keyPath);
        Session s = jsch.getSession(user, host, port);
        s.setConfig("StrictHostKeyChecking", "no");
        s.setConfig("PreferredAuthentications", "publickey");
        // Old Android JCEs (e.g. Evervolv 7.1) lack EC AlgorithmParameters, so stay
        // away from ECDH/ECDSA entirely; the server accepts rsa-sha2 + group14.
        s.setConfig("kex", "diffie-hellman-group14-sha256,diffie-hellman-group-exchange-sha256");
        s.setConfig("server_host_key", "rsa-sha2-256,rsa-sha2-512,ssh-rsa");
        s.setServerAliveInterval(15000);
        s.setServerAliveCountMax(3);
        s.connect(CONNECT_TIMEOUT_MS);
        session = s;
        return s;
    }

    /** One read-only poll. Returns the raw JSON string produced by the script. */
    synchronized String poll() throws Exception {
        return exec(script, "", 20000);
    }

    /** Runs the whitelisted service-control script: action = start|stop|stopall, id = service id. */
    synchronized String svc(String action, String id) throws Exception {
        // a 27B/30B teardown (pidfile -> port -> SIGKILL) can take a while; keep
        // the channel open long enough that stopall never gets cut mid-way
        return exec(svcScript, " " + action + " " + id, 90000);
    }

    /** Executes a script piped into `python3 -`, optionally with argv. */
    private String exec(String py, String argv, int timeoutMs) throws Exception {
        Session s = session();
        ChannelExec ch = null;
        long deadline = System.currentTimeMillis() + timeoutMs;
        try {
            ch = (ChannelExec) s.openChannel("exec");
            ch.setCommand("python3 -" + argv + " <<'HPSCOPE_PY'\n" + py + "\nHPSCOPE_PY");
            ByteArrayOutputStream out = new ByteArrayOutputStream(8192);
            ByteArrayOutputStream err = new ByteArrayOutputStream(2048);
            ch.setOutputStream(out);
            ch.setErrStream(err);
            ch.connect(CONNECT_TIMEOUT_MS);
            while (!ch.isClosed()) {
                if (System.currentTimeMillis() > deadline) {
                    throw new Exception("timeout");
                }
                Thread.sleep(15);
            }
            String json = new String(out.toByteArray(), "UTF-8").trim();
            if (json.length() == 0) {
                String e = new String(err.toByteArray(), "UTF-8").trim();
                throw new Exception("empty reply " + (e.length() > 0 ? e : "(no stderr)"));
            }
            if (json.charAt(0) != '{') {
                throw new Exception("non-json reply: " + json.substring(0, Math.min(120, json.length())));
            }
            return json;
        } catch (Exception e) {
            // a broken channel usually means the whole session is suspect
            close();
            throw e;
        } finally {
            if (ch != null) {
                try {
                    ch.disconnect();
                } catch (Exception ignored) {
                }
            }
        }
    }
}