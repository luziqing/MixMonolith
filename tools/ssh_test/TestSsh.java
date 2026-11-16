import com.jcraft.jsch.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

/**
 * Desktop de-risk harness for the SSH probe path.
 *
 *   java TestSsh <privkey> <script.py>
 *
 * Connects with the ECDSA key, sends the script as
 *   python3 - <<'HPSCOPE_PY' ... HPSCOPE_PY
 * and prints timing + payload size + the JSON that came back.
 */
public class TestSsh {
    static final String HOST = "192.168.1.100";
    static final String USER = "jd4090";

    public static void main(String[] a) throws Exception {
        String keyPath = a[0];
        String script = new String(Files.readAllBytes(Paths.get(a[1])), StandardCharsets.UTF_8);

        JSch jsch = new JSch();
        jsch.addIdentity(keyPath);
        Session s = jsch.getSession(USER, HOST, 22);
        s.setConfig("StrictHostKeyChecking", "no");
        s.setConfig("PreferredAuthentications", "publickey");
        // old Android JCEs lack EC AlgorithmParameters -> stay on non-EC algorithms
        s.setConfig("kex", "diffie-hellman-group14-sha256,diffie-hellman-group-exchange-sha256");
        s.setConfig("server_host_key", "rsa-sha2-256,rsa-sha2-512,ssh-rsa");
        long t0 = System.nanoTime();
        s.connect(15000);
        System.out.println("CONNECT ms : " + ((System.nanoTime() - t0) / 1_000_000));
        System.out.println("SERVER     : " + s.getServerVersion());
        System.out.println("HOSTKEY    : " + s.getHostKey().getType());
        System.out.println("SCRIPT     : " + script.length() + " chars");

        for (int i = 0; i < 3; i++) {
            long a0 = System.nanoTime();
            ChannelExec ch = (ChannelExec) s.openChannel("exec");
            ch.setCommand("python3 - <<'HPSCOPE_PY'\n" + script + "\nHPSCOPE_PY");
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            ByteArrayOutputStream err = new ByteArrayOutputStream();
            ch.setOutputStream(out);
            ch.setErrStream(err);
            ch.connect(15000);
            while (!ch.isClosed()) Thread.sleep(10);
            ch.disconnect();
            long ms = (System.nanoTime() - a0) / 1_000_000;
            String json = new String(out.toByteArray(), StandardCharsets.UTF_8);
            String e = new String(err.toByteArray(), StandardCharsets.UTF_8).trim();
            if (a.length > 2) {
                Files.write(Paths.get(a[2] + "-" + (i + 1) + ".json"), json.getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("POLL " + (i + 1) + " ms=" + ms + " bytes=" + json.length()
                    + (e.isEmpty() ? "" : " STDERR=" + e.substring(0, Math.min(200, e.length()))));
            if (i == 0) {
                System.out.println("HAS KEYS   : cpu=" + json.contains("\"cpu\":")
                        + " cores=" + json.contains("\"cores\":")
                        + " mem=" + json.contains("\"mem\":")
                        + " top=" + json.contains("\"top\":")
                        + " gpu=" + json.contains("\"gpu\":")
                        + " temp=" + json.contains("\"temp\":"));
                System.out.println("HEAD       : " + json.substring(0, Math.min(260, json.length())));
            }
        }
        s.disconnect();
    }
}