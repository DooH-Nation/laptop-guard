package com.laptopguard.companion;

import android.app.*;
import android.bluetooth.*;
import android.bluetooth.le.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class GuardService extends Service {
    static volatile boolean alive=false;
    static final String CONFIRM="com.laptopguard.CONFIRM";
    private final Handler handler=new Handler(Looper.getMainLooper());
    private volatile boolean running=false;
    private volatile HttpURLConnection connection;
    private Thread worker;
    private JSONObject pair;
    private BluetoothLeAdvertiser advertiser;
    private boolean advertising=false;
    private volatile boolean online=false;
    private String bleStatus="신호 준비 중";
    private String lastStatus="";
    private final AdvertiseCallback callback=new AdvertiseCallback(){
        @Override public void onStartSuccess(AdvertiseSettings settings){advertising=true;bleStatus="근접 신호 켜짐";updateStatus();}
        @Override public void onStartFailure(int error){advertising=false;bleStatus="근접 신호 오류 ("+error+") · Bluetooth를 확인해 주세요";updateStatus();advertiser=null;}
    };
    @Override public void onCreate(){super.onCreate();channels();}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent!=null&&CONFIRM.equals(intent.getAction())){
            String event=intent.getStringExtra("event");
            try {JSONObject p=Protocol.load(this);if(p!=null&&event!=null)new Thread(()->{ack(p,"confirmed",event);if(!running)stopSelf(startId);}).start();}catch(Exception ignored){}
            return START_NOT_STICKY;
        }
        if(running)return START_STICKY;
        try{
            pair=Protocol.load(this);if(pair==null){stopSelf();return START_NOT_STICKY;}
            startForeground(1,statusNotification("연결을 준비하고 있어요"),ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
            running=true;alive=true;Protocol.prefs(this).edit().putBoolean("enabled",true).apply();
            handler.post(bluetoothCheck);
            worker=new Thread(this::receive,"LaptopGuard-relay");worker.start();
            return START_STICKY;
        }catch(Exception e){Protocol.prefs(this).edit().putString("status","연결 시작 실패 · 앱을 열어 권한을 확인해 주세요").apply();stopSelf();return START_NOT_STICKY;}
    }
    private final Runnable bluetoothCheck=new Runnable(){public void run(){
        if(!running)return;
        try{
            if(checkSelfPermission(android.Manifest.permission.BLUETOOTH_ADVERTISE)!=android.content.pm.PackageManager.PERMISSION_GRANTED ||
               checkSelfPermission(android.Manifest.permission.BLUETOOTH_CONNECT)!=android.content.pm.PackageManager.PERMISSION_GRANTED){
                advertising=false;bleStatus="근처 기기 권한을 허용해 주세요";updateStatus();handler.postDelayed(this,10000);return;
            }
            BluetoothManager manager=getSystemService(BluetoothManager.class);BluetoothAdapter adapter=manager.getAdapter();
            if(adapter==null||!adapter.isEnabled()){
                if(advertiser!=null && checkSelfPermission(android.Manifest.permission.BLUETOOTH_ADVERTISE)==android.content.pm.PackageManager.PERMISSION_GRANTED)try{advertiser.stopAdvertising(callback);}catch(SecurityException ignored){}
                advertiser=null;advertising=false;bleStatus="Bluetooth가 꺼져 있어요";updateStatus();
            }else if(advertiser==null){
                advertiser=adapter.getBluetoothLeAdvertiser();
                if(advertiser==null){bleStatus="이 폰에서 근접 신호를 켤 수 없어요";updateStatus();}
                else{
                    AdvertiseSettings settings=new AdvertiseSettings.Builder().setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
                        .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM).setConnectable(false).setTimeout(0).build();
                    AdvertiseData data=new AdvertiseData.Builder().addServiceUuid(new ParcelUuid(UUID.fromString(pair.getString("uuid")))).setIncludeDeviceName(false).build();
                    advertiser.startAdvertising(settings,data,callback);
                }
            }
        }catch(Exception e){advertiser=null;advertising=false;bleStatus="근처 기기 권한을 확인해 주세요";updateStatus();}
        handler.postDelayed(this,10000);
    }};
    private void receive(){
        int failures=0;
        while(running){
            try{
                long now=System.currentTimeMillis()/1000;
                long cursor=Protocol.prefs(this).getLong("cursor_time",now-300);
                long since=Math.max(now-3600,cursor-1);
                URL url=new URL("https://ntfy.sh/"+pair.getString("topic")+"/json?since="+since);
                connection=(HttpURLConnection)url.openConnection();connection.setConnectTimeout(10000);connection.setReadTimeout(75000);
                if(connection.getResponseCode()!=200)throw new IOException("relay response");
                online=true;failures=0;updateStatus();
                BufferedReader reader=new BufferedReader(new InputStreamReader(connection.getInputStream(),StandardCharsets.UTF_8));
                String line;
                while(running&&(line=limitedLine(reader))!=null){
                    JSONObject event=new JSONObject(line);
                    if("message".equals(event.optString("event"))){
                        try{JSONObject payload=Protocol.decrypt(pair,event.getString("message"));
                            long timestamp=payload.getLong("time");
                            long current=System.currentTimeMillis()/1000;
                            if(timestamp>current+300||timestamp<current-3600)continue;
                            showAlert(payload);
                            Protocol.prefs(this).edit().putLong("cursor_time",event.optLong("time",System.currentTimeMillis()/1000)).apply();
                        }catch(Exception ignored){} // Unauthenticated or malformed messages never create alerts.
                    }
                }
                if(running)throw new IOException("stream closed");
            }catch(Exception e){online=false;updateStatus();failures++;}
            finally{HttpURLConnection c=connection;if(c!=null)c.disconnect();connection=null;}
            if(running)try{Thread.sleep(Math.min(30000,1000L*(1L<<Math.min(failures,5))));}catch(InterruptedException ignored){}
        }
    }
    private String limitedLine(BufferedReader reader)throws IOException{
        StringBuilder text=new StringBuilder();int c;
        while((c=reader.read())!=-1){if(c=='\n')return text.toString();if(text.length()>32768)throw new IOException("line too large");text.append((char)c);}
        return text.length()==0?null:text.toString();
    }
    private void showAlert(JSONObject payload)throws Exception{
        String kind=payload.getString("kind"),id=payload.getString("id");
        if(!kind.equals("test")&&!kind.equals("alarm"))return;
        if(!id.matches("[a-f0-9]{32}"))return;
        String seen=Protocol.prefs(this).getString("seen","");if(seen.contains(id))return;
        NotificationManager nm=getSystemService(NotificationManager.class);
        NotificationChannel ch=nm.getNotificationChannel("alerts");
        if(!nm.areNotificationsEnabled()||ch==null||ch.getImportance()==NotificationManager.IMPORTANCE_NONE){
            Protocol.prefs(this).edit().putString("status","폰 알림이 차단됐어요 · 앱에서 알림 권한을 켜 주세요").apply();return;
        }
        Intent confirm=new Intent(this,GuardService.class).setAction(CONFIRM).putExtra("event",id);
        PendingIntent confirmation=PendingIntent.getService(this,id.hashCode(),confirm,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        boolean delayed=System.currentTimeMillis()/1000-payload.getLong("time")>60;
        String title=kind.equals("test")?"연결 테스트 · 아래 확인 버튼을 눌러 주세요":"충전선 분리 감지! 노트북을 확인하세요";
        if(delayed)title="늦게 도착한 알림 · "+title;
        String text=payload.optString("text","");if(text.length()>500)text=text.substring(0,500);
        Notification n=new Notification.Builder(this,"alerts").setSmallIcon(com.laptopguard.companion.R.drawable.ic_guard)
            .setContentTitle(title).setContentText(text).setStyle(new Notification.BigTextStyle().bigText(text))
            .setContentIntent(openApp()).setAutoCancel(true).setCategory(Notification.CATEGORY_ALARM)
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .addAction(new Notification.Action.Builder(null,"확인했어요",confirmation).build()).build();
        nm.notify(id.hashCode(),n);
        String[] ids=(seen+","+id).split(",");StringBuilder retained=new StringBuilder();
        for(int i=Math.max(0,ids.length-100);i<ids.length;i++)retained.append(ids[i]).append(',');
        Protocol.prefs(this).edit().putString("seen",retained.toString()).putString("last_alert",title+"\n"+text).apply();
    }
    private void ack(JSONObject p,String kind,String event){
        HttpURLConnection c=null;
        try{
            JSONObject payload=new JSONObject().put("kind",kind).put("id",event).put("time",System.currentTimeMillis()/1000).put("phone",Protocol.phoneName(this));
            byte[] bytes=Protocol.encrypt(p,payload).getBytes(StandardCharsets.UTF_8);
            c=(HttpURLConnection)new URL("https://ntfy.sh/"+p.getString("ack")).openConnection();c.setRequestMethod("POST");c.setDoOutput(true);c.setConnectTimeout(10000);c.setReadTimeout(10000);
            c.setRequestProperty("Content-Type","text/plain; charset=utf-8");try(OutputStream out=c.getOutputStream()){out.write(bytes);}
            if(c.getResponseCode()!=200)throw new IOException("ack failed");
            Protocol.prefs(this).edit().putString("status","확인 응답을 노트북으로 보냈어요").apply();
        }catch(Exception e){Protocol.prefs(this).edit().putString("status","확인 응답 전송 실패 · 인터넷 확인 후 알림의 확인 버튼을 다시 눌러 주세요").apply();}
        finally{if(c!=null)c.disconnect();}
    }
    private void channels(){
        NotificationManager nm=getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("running","연결 상태",NotificationManager.IMPORTANCE_LOW));
        NotificationChannel alert=new NotificationChannel("alerts","노트북 경보와 테스트 알림",NotificationManager.IMPORTANCE_HIGH);alert.enableVibration(true);nm.createNotificationChannel(alert);
    }
    private PendingIntent openApp(){return PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
    private Notification statusNotification(String text){return new Notification.Builder(this,"running").setSmallIcon(com.laptopguard.companion.R.drawable.ic_guard).setContentTitle("LaptopGuard 연결 중")
        .setContentText(text).setContentIntent(openApp()).setOngoing(true).setVisibility(Notification.VISIBILITY_PRIVATE).build();}
    private void updateStatus(){
        String status=bleStatus+" · "+(online?"알림 수신 연결됨":"인터넷 재연결 중");
        if(status.equals(lastStatus))return;lastStatus=status;
        Protocol.prefs(this).edit().putString("status",status).putBoolean("ble_ok",advertising).putBoolean("relay_ok",online).apply();
        if(running)getSystemService(NotificationManager.class).notify(1,statusNotification(status));
    }
    @Override public void onDestroy(){
        running=false;alive=false;online=false;handler.removeCallbacksAndMessages(null);
        if(worker!=null)worker.interrupt();HttpURLConnection c=connection;if(c!=null)c.disconnect();
        if(advertiser!=null && checkSelfPermission(android.Manifest.permission.BLUETOOTH_ADVERTISE)==android.content.pm.PackageManager.PERMISSION_GRANTED)try{advertiser.stopAdvertising(callback);}catch(SecurityException ignored){}
        Protocol.prefs(this).edit().putBoolean("ble_ok",false).putBoolean("relay_ok",false).putString("status","연결이 멈췄어요 · 앱에서 연결 시작을 눌러 주세요").apply();
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent i){return null;}
}
