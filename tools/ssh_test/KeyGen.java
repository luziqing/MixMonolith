import com.jcraft.jsch.JSch;
import com.jcraft.jsch.KeyPair;

import java.util.Base64;

/**
 * Generates the identity that ships inside the APK (assets/hpscope_ecdsa).
 *
 *   java KeyGen <outfile> <comment> [rsa|ecdsa] [bits]
 *
 * RSA is used for devices whose JCE lacks EC AlgorithmParameters (old ROMs):
 * the server accepts rsa-sha2-256, so no ssh-rsa/SHA-1 fallback is needed.
 */
public class KeyGen {
    public static void main(String[] a) throws Exception {
        String out = a[0];
        String comment = a.length > 1 ? a[1] : "hpscope-touchpad";
        String type = a.length > 2 ? a[2] : "rsa";
        int bits = a.length > 3 ? Integer.parseInt(a[3]) : (type.equals("rsa") ? 3072 : 256);

        JSch jsch = new JSch();
        int jtype = type.equals("rsa") ? KeyPair.RSA : KeyPair.ECDSA;
        KeyPair kp = KeyPair.genKeyPair(jsch, jtype, bits);
        kp.writePrivateKey(out);

        byte[] blob = kp.getPublicKeyBlob();
        String b64 = Base64.getEncoder().encodeToString(blob);
        String kind;
        if (type.equals("rsa")) {
            kind = "ssh-rsa";
        } else {
            kind = "ecdsa-sha2-nistp256";
        }
        System.out.println(kind + " " + b64 + " " + comment);
        kp.dispose();
    }
}