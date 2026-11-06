package com.laptopguard.companion;

import android.app.*;
import android.content.*;
import android.service.notification.StatusBarNotification;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;
import org.json.JSONObject;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

@RunWith(AndroidJUnit4.class)
public class CompanionInstrumentedTest {
    private JSONObject vector()throws Exception{
        try(InputStream in=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open("vector.json")){
            return new JSONObject(new String(in.readAllBytes(),StandardCharsets.UTF_8));
        }
    }
    private Context context(){return InstrumentationRegistry.getInstrumentation().getTargetContext();}
    @Test public void pythonCiphertextDecryptsOnAndroid()throws Exception{
        JSONObject v=vector();JSONObject pair=Protocol.parse(v.getString("code"));
        JSONObject decoded=Protocol.decrypt(pair,v.getString("envelope"));
        assertEquals(v.getJSONObject("message").getString("text"),decoded.getString("text"));
        JSONObject reply=new JSONObject().put("kind","confirmed").put("id",decoded.getString("id")).put("time",System.currentTimeMillis()/1000).put("phone","Android test device");
        try(OutputStream out=context().openFileOutput("interop_reply.json",Context.MODE_PRIVATE)){out.write(Protocol.encrypt(pair,reply).getBytes(StandardCharsets.UTF_8));}
    }
    @Test public void pairingIsProtectedByAndroidKeyStore()throws Exception{
        JSONObject pair=Protocol.parse(vector().getString("code"));Protocol.save(context(),pair);
        assertEquals(pair.getString("key"),Protocol.load(context()).getString("key"));
        assertFalse(Protocol.prefs(context()).getString("pair_box","").contains(pair.getString("key")));
    }
    @Test public void changedCiphertextIsRejected()throws Exception{
        JSONObject v=vector();JSONObject envelope=new JSONObject(v.getString("envelope"));byte[] bytes=Protocol.unb64(envelope.getString("c"));bytes[0]^=1;envelope.put("c",Protocol.b64(bytes));
        try{Protocol.decrypt(v.getJSONObject("pair"),envelope.toString());fail("tampered ciphertext accepted");}catch(javax.crypto.AEADBadTagException expected){}
    }
    @Test public void encryptedRelayMessageCreatesNotificationAndConfirmation()throws Exception{
        Context c=context();JSONObject v=vector();JSONObject pair=v.getJSONObject("pair");Protocol.save(c,pair);
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->c.startActivity(new Intent(c,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)));
        InstrumentationRegistry.getInstrumentation().waitForIdleSync();Thread.sleep(1000);
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->c.startForegroundService(new Intent(c,GuardService.class)));
        try{
            long deadline=System.currentTimeMillis()+35000;
            while(System.currentTimeMillis()<deadline&&!Protocol.prefs(c).getBoolean("relay_ok",false))Thread.sleep(300);
            assertTrue("relay did not connect",Protocol.prefs(c).getBoolean("relay_ok",false));
            HttpURLConnection conn=(HttpURLConnection)new URL("https://ntfy.sh/"+pair.getString("topic")).openConnection();
            conn.setRequestMethod("POST");conn.setDoOutput(true);conn.setConnectTimeout(10000);conn.setReadTimeout(10000);conn.setRequestProperty("Content-Type","text/plain; charset=utf-8");
            try(OutputStream out=conn.getOutputStream()){out.write(v.getString("envelope").getBytes(StandardCharsets.UTF_8));}assertEquals(200,conn.getResponseCode());conn.disconnect();
            String id=v.getJSONObject("message").getString("id");Notification received=null;deadline=System.currentTimeMillis()+35000;
            while(System.currentTimeMillis()<deadline&&received==null){
                for(StatusBarNotification n:c.getSystemService(NotificationManager.class).getActiveNotifications())if(n.getId()==id.hashCode())received=n.getNotification();
                if(received==null)Thread.sleep(300);
            }
            assertNotNull("encrypted test notification not posted",received);assertTrue(received.actions.length>0);
            received.actions[0].actionIntent.send();deadline=System.currentTimeMillis()+20000;
            while(System.currentTimeMillis()<deadline&&!Protocol.prefs(c).getString("status","").contains("확인 응답을 노트북으로 보냈어요"))Thread.sleep(300);
            assertTrue("confirmation response failed",Protocol.prefs(c).getString("status","").contains("확인 응답을 노트북으로 보냈어요"));
        }finally{c.stopService(new Intent(c,GuardService.class));Protocol.prefs(c).edit().putBoolean("enabled",false).apply();}
    }
}
