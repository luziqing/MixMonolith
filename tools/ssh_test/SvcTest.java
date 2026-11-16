import com.jcraft.jsch.ChannelExec;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.Session;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * Exercises the exact command SshProbe.svc() sends:
 *   python3 - <action> <id> <<'HPSCOPE_PY' ... HPSCOPE_PY
 * against the shipped svc_ctl.py, then verifies the port state.
 *
 *   java SvcTest <key> <svc_ctl.py> <id>
 */
public class SvcTest {
    static final String HOST = "192.168.1.100";
    static final String USER = "jd4090";

    public static void main(String[] a) throws Exception {
        String key = a[0];
        String py = new String(Files.readAllBytes(Paths.get(a[1])), StandardCharsets.UTF_8);
        String id = a[2];

        JSch jsch = new JSch();
        jsch.addIdentity(key);
        Session s = jsch.getSession(USER, HOST, 22);
        s.setConfig("StrictHostKeyChecking", "no");
        s.setConfig("PreferredAuthentications", "publickey");
        s.setConfig("kex", "diffie-hellman-group14-sha256,diffie-hellman-group-exchange-sha256");
        s.setConfig("server_host_key", "rsa-sha2-256,rsa-sha2-512,ssh-rsa");
        s.connect(15000);
        System.out.println("connected " + s.getServerVersion());

        System.out.println("status  -> " + run(s, py, "status " + id));
        System.out.println("start   -> " + run(s, py, "start " + id));

        for (int i = 0; i < 30; i++) {
            Thread.sleep(2000);
            String st = run(s, py, "status " + id);
            if (st.contains("\"up\": true")) {
                System.out.println("up after " + ((i + 1) * 2) + "s: " + st);
                break;
            }
            if (i == 29) {
                System.out.println("still down after 60s: " + st);
            }
        }

        System.out.println("stop    -> " + run(s, py, "stop " + id));
        System.out.println("status  -> " + run(s, py, "status " + id));
        s.disconnect();
    }

    private static String run(Session s, String py, String argv) throws Exception {
        long t0 = System.nanoTime();
        ChannelExec ch = (ChannelExec) s.openChannel("exec");
        ch.setCommand("python3 - " + argv + " <<'HPSCOPE_PY'\n" + py + "\nHPSCOPE_PY");
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteArrayOutputStream err = new ByteArrayOutputStream();
        ch.setOutputStream(out);
        ch.setErrStream(err);
        ch.connect(10000);
        long deadline = System.currentTimeMillis() + 25000;
        while (!ch.isClosed() && System.currentTimeMillis() < deadline) {
            Thread.sleep(15);
        }
        ch.disconnect();
        String json = new String(out.toByteArray(), StandardCharsets.UTF_8).trim();
        String e = new String(err.toByteArray(), StandardCharsets.UTF_8).trim();
        long ms = (System.nanoTime() - t0) / 1_000_000;
        return json + "  [" + ms + " ms]" + (e.isEmpty() ? "" : " stderr=" + e);
    }
}