package com.laptopguard.companion;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.UUID;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

final class Protocol {
    static final byte[] AAD="LaptopGuard/2".getBytes(StandardCharsets.UTF_8);
    static final int FLAGS=Base64.URL_SAFE|Base64.NO_PADDING|Base64.NO_WRAP;
    static SharedPreferences prefs(Context c){return c.getSharedPreferences("guard",Context.MODE_PRIVATE);}
    static String b64(byte[] b){return Base64.encodeToString(b,FLAGS);}
    static byte[] unb64(String s){return Base64.decode(s,FLAGS);}
    static JSONObject parse(String text)throws Exception{
        text=text.trim();
        if(!text.startsWith("LG2.")||text.length()>2048)throw new Exception("노트북에서 만든 연결 코드를 사용해 주세요.");
        JSONObject p=new JSONObject(new String(unb64(text.substring(4)),StandardCharsets.UTF_8));
        if(p.getInt("v")!=2||!p.getString("server").equals("https://ntfy.sh"))throw new Exception("지원하지 않는 연결 코드예요.");
        UUID.fromString(p.getString("uuid"));
        if(unb64(p.getString("key")).length!=32)throw new Exception("잘못된 연결 키예요.");
        if(!p.getString("topic").matches("lg-[a-f0-9]{48}")||!p.getString("ack").matches("lg-[a-f0-9]{48}"))throw new Exception("잘못된 알림 주소예요.");
        return p;
    }
    static SecretKey storageKey()throws Exception{
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
        if(!ks.containsAlias("LaptopGuardPair")){
            KeyGenerator gen=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            gen.init(new KeyGenParameterSpec.Builder("LaptopGuardPair",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build());gen.generateKey();
        }
        return ((KeyStore.SecretKeyEntry)ks.getEntry("LaptopGuardPair",null)).getSecretKey();
    }
    static void save(Context c,JSONObject p)throws Exception{
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,storageKey());
        JSONObject box=new JSONObject().put("n",b64(cipher.getIV())).put("c",b64(cipher.doFinal(p.toString().getBytes(StandardCharsets.UTF_8))));
        prefs(c).edit().putString("pair_box",box.toString()).remove("seen").remove("cursor_time").apply();
    }
    static JSONObject load(Context c)throws Exception{
        String saved=prefs(c).getString("pair_box",null);if(saved==null)return null;
        JSONObject box=new JSONObject(saved);
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,storageKey(),new GCMParameterSpec(128,unb64(box.getString("n"))));
        return new JSONObject(new String(cipher.doFinal(unb64(box.getString("c"))),StandardCharsets.UTF_8));
    }
    static String encrypt(JSONObject pair,JSONObject message)throws Exception{
        byte[] nonce=new byte[12];new SecureRandom().nextBytes(nonce);
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(unb64(pair.getString("key")),"AES"),new GCMParameterSpec(128,nonce));cipher.updateAAD(AAD);
        return new JSONObject().put("v",2).put("n",b64(nonce)).put("c",b64(cipher.doFinal(message.toString().getBytes(StandardCharsets.UTF_8)))).toString();
    }
    static JSONObject decrypt(JSONObject pair,String raw)throws Exception{
        if(raw.length()>16384)throw new Exception("too large");JSONObject e=new JSONObject(raw);
        if(e.getInt("v")!=2)throw new Exception("version");
        byte[] nonce=unb64(e.getString("n"));if(nonce.length!=12)throw new Exception("nonce");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,new SecretKeySpec(unb64(pair.getString("key")),"AES"),new GCMParameterSpec(128,nonce));cipher.updateAAD(AAD);
        return new JSONObject(new String(cipher.doFinal(unb64(e.getString("c"))),StandardCharsets.UTF_8));
    }
    static String phoneName(Context c){
        try {String n=android.provider.Settings.Global.getString(c.getContentResolver(),"device_name");if(n!=null&&!n.trim().isEmpty())return n.substring(0,Math.min(60,n.length()));}catch(Exception ignored){}
        return android.os.Build.MANUFACTURER+" "+android.os.Build.MODEL;
    }
}
