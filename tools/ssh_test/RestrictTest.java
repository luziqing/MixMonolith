import com.jcraft.jsch.*;

/**
 * Demonstrates what the authorized_keys "restrict" option blocks:
 *   - PTY allocation (interactive terminal)
 *   - TCP port forwarding (direct-tcpip)
 * while still allowing exec of the read-only probe.
 */
public class RestrictTest {
    static final String HOST = "192.168.1.100";
    static final String USER = "jd4090";

    public static void main(String[] a) throws Exception {
        JSch jsch = new JSch();
        jsch.addIdentity(a[0]);
        Session s = jsch.getSession(USER, HOST, 22);
        s.setConfig("StrictHostKeyChecking", "no");
        s.setConfig("PreferredAuthentications", "publickey");
        s.connect(10000);
        System.out.println("connected: " + s.getServerVersion());

        // 1) exec without pty -> allowed (this is what the app does)
        try {
            ChannelExec ch = (ChannelExec) s.openChannel("exec");
            ch.setCommand("echo exec-ok; id -un");
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            ch.setOutputStream(out);
            ch.connect(5000);
            while (!ch.isClosed()) Thread.sleep(10);
            ch.disconnect();
            System.out.println("[exec, no pty]      ALLOWED -> " + new String(out.toByteArray()).trim().replace("\n", " | "));
        } catch (Exception e) {
            System.out.println("[exec, no pty]      BLOCKED -> " + e);
        }

        // 2) interactive shell with pty -> blocked by no-pty
        try {
            ChannelShell sh = (ChannelShell) s.openChannel("shell");
            sh.setPty(true);
            sh.connect(5000);
            sh.disconnect();
            System.out.println("[pty shell]         ALLOWED (unexpected)");
        } catch (Exception e) {
            System.out.println("[pty shell]         BLOCKED -> " + e.getMessage());
        }

        // 3) direct-tcpip channel (what -L/-R/-D would use) -> blocked by no-port-forwarding
        try {
            ChannelDirectTCPIP ch = (ChannelDirectTCPIP) s.openChannel("direct-tcpip");
            ch.setHost("127.0.0.1");
            ch.setPort(22);
            ch.setOrgPort(1234);
            ch.connect(5000);
            ch.disconnect();
            System.out.println("[direct-tcpip -L]   ALLOWED (unexpected)");
        } catch (Exception e) {
            System.out.println("[direct-tcpip -L]   BLOCKED -> " + e.getMessage());
        }

        s.disconnect();
    }
}