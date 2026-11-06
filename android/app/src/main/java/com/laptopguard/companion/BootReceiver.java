package com.laptopguard.companion;
import android.content.*;
public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context c,Intent i){
        if(Intent.ACTION_BOOT_COMPLETED.equals(i.getAction())&&Protocol.prefs(c).getBoolean("enabled",false)){
            try{c.startForegroundService(new Intent(c,GuardService.class));}
            catch(Exception e){Protocol.prefs(c).edit().putString("status","재부팅 후 앱에서 연결 시작을 눌러 주세요").apply();}
        }
    }
}
