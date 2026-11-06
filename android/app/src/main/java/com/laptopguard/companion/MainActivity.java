package com.laptopguard.companion;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.util.*;
import com.google.mlkit.vision.codescanner.*;
import com.google.mlkit.vision.barcode.common.Barcode;

public class MainActivity extends Activity {
    final int BLACK=Color.BLACK,BLUE=Color.rgb(20,87,166),GREEN=Color.rgb(20,108,67),AMBER=Color.rgb(155,82,0),RED=Color.rgb(180,35,24);
    private TextView status,paired,permissions,lastAlert;
    private final Handler handler=new Handler(Looper.getMainLooper());
    @Override public void onCreate(Bundle b){super.onCreate(b);build();}
    private int dp(int n){return (int)(n*getResources().getDisplayMetrics().density);}
    private TextView text(LinearLayout box,String value,int size,int color){
        TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setPadding(0,dp(6),0,dp(6));box.addView(t);return t;
    }
    private void button(LinearLayout box,String label,Runnable action){
        Button b=new Button(this);b.setText(label);b.setTextColor(BLACK);b.setAllCaps(false);box.addView(b,new LinearLayout.LayoutParams(-1,-2));b.setOnClickListener(v->action.run());
    }
    private void build(){
        ScrollView scroll=new ScrollView(this);LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(22),dp(20),dp(22),dp(28));scroll.addView(box);setContentView(scroll);
        text(box,"LaptopGuard",30,BLACK);
        text(box,"내 노트북과 한 번만 연결하세요",18,BLUE);
        paired=text(box,"등록된 노트북 없음",16,BLACK);
        status=text(box,"노트북 화면의 QR 코드를 읽어 주세요.",18,AMBER);
        permissions=text(box,"",14,BLACK);
        button(box,"① 노트북 QR 코드 읽기",this::scan);
        button(box,"QR을 읽을 수 없나요? 연결 코드 붙여넣기",this::paste);
        button(box,"② 권한 허용하고 연결 시작",this::startConnection);
        text(box,"연결 후에는 이 앱 하나만 켜 두면 돼요.\n근접 신호와 노트북 경보 수신을 함께 처리합니다.",15,BLACK);
        text(box,"처음 한 번 확인해 주세요",18,BLUE);
        text(box,"1. 노트북에서 ‘폰에 테스트 알림 보내기’를 누르세요.\n2. 폰 알림을 펼쳐 ‘확인했어요’를 누르세요.\n3. 노트북에서 ‘이 휴대폰으로 연결 완료’를 누르세요.",16,BLACK);
        lastAlert=text(box,"아직 받은 알림이 없어요.",14,BLACK);
        text(box,"화면이 꺼져도 연결을 유지하려면",18,BLUE);
        text(box,"갤럭시 설정에서 이 앱의 배터리를 ‘제한 없음’으로 설정하고, 절전 앱 목록에 넣지 마세요. 연결 중에는 상태 알림이 계속 표시됩니다.",15,AMBER);
        button(box,"앱 배터리 설정 열기",()->startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName()))));
        button(box,"폰 알림 설정 열기",()->startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE,getPackageName())));
        button(box,"연결 멈추기",()->new AlertDialog.Builder(this).setTitle("연결을 멈출까요?").setMessage("근접 신호와 노트북 알림 수신이 멈춥니다. 노트북 보호를 해제하는 기능은 아닙니다.")
            .setPositiveButton("멈추기",(d,w)->{Protocol.prefs(this).edit().putBoolean("enabled",false).apply();stopService(new Intent(this,GuardService.class));refresh();}).setNegativeButton("취소",null).show());
        text(box,"인터넷이나 폰의 절전 정책 때문에 알림이 늦어질 수 있어요. 재부팅·강제 종료 후에는 연결 상태를 확인하세요.\n\n알림 내용은 노트북과 폰 사이에서 암호화되며 ntfy.sh 서버로 전달됩니다. 연결 QR과 코드는 다른 사람에게 공유하지 마세요.",14,BLACK);
    }
    private void scan(){
        GmsBarcodeScannerOptions options=new GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).enableAutoZoom().build();
        GmsBarcodeScanning.getClient(this,options).startScan().addOnSuccessListener(barcode->{if(barcode.getRawValue()!=null)accept(barcode.getRawValue());})
            .addOnFailureListener(e->new AlertDialog.Builder(this).setTitle("QR을 읽지 못했어요").setMessage("인터넷과 Google Play 서비스 상태를 확인해 주세요. 노트북의 ‘연결 코드 복사’를 이용해 붙여넣을 수도 있어요.").setPositiveButton("확인",null).show());
    }
    private void paste(){
        EditText input=new EditText(this);input.setTextColor(BLACK);input.setHint("LG2.로 시작하는 코드");input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        new AlertDialog.Builder(this).setTitle("노트북 연결 코드").setView(input).setPositiveButton("등록",(d,w)->accept(input.getText().toString())).setNegativeButton("취소",null).show();
    }
    private void accept(String code){
        try{
            JSONObject next=Protocol.parse(code);
            Runnable replace=()->{
                try{
                    Protocol.prefs(this).edit().putBoolean("enabled",false).apply();stopService(new Intent(this,GuardService.class));
                    Protocol.save(this,next);status.setText("등록했어요. 아래 권한 허용 버튼을 눌러 주세요.");startConnection();
                }catch(Exception e){showError("등록 정보를 저장하지 못했어요. 다시 시도해 주세요.");}
            };
            JSONObject old=Protocol.load(this);
            if(old!=null&&!old.optString("uuid").equals(next.optString("uuid")))new AlertDialog.Builder(this).setTitle("새 노트북 연결로 바꿀까요?").setMessage("기존 연결 대신 새 연결을 사용합니다.").setPositiveButton("바꾸기",(d,w)->replace.run()).setNegativeButton("취소",null).show();
            else if(old!=null){startConnection();} else replace.run();
        }catch(Exception e){showError("연결 코드가 맞지 않아요. 노트북의 ‘휴대폰 연결’에서 새로 읽어 주세요.");}
    }
    private void startConnection(){
        try{if(Protocol.load(this)==null){showError("먼저 노트북의 QR 코드를 읽어 주세요.");return;}}catch(Exception e){showError("등록 정보를 읽지 못했어요. 다시 등록해 주세요.");return;}
        ArrayList<String> needed=new ArrayList<>();
        for(String p:new String[]{Manifest.permission.BLUETOOTH_ADVERTISE,Manifest.permission.BLUETOOTH_CONNECT})if(checkSelfPermission(p)!=PackageManager.PERMISSION_GRANTED)needed.add(p);
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)needed.add(Manifest.permission.POST_NOTIFICATIONS);
        if(!needed.isEmpty()){requestPermissions(needed.toArray(new String[0]),7);return;}
        if(!getSystemService(NotificationManager.class).areNotificationsEnabled()){showError("알림이 꺼져 있어요. ‘폰 알림 설정 열기’에서 알림을 켜 주세요.");return;}
        try{startForegroundService(new Intent(this,GuardService.class));refresh();}catch(Exception e){showError("연결을 시작하지 못했어요. Bluetooth를 켜고 다시 눌러 주세요.");}
    }
    @Override public void onRequestPermissionsResult(int request,String[] p,int[] r){super.onRequestPermissionsResult(request,p,r);if(request==7){for(int grant:r)if(grant!=PackageManager.PERMISSION_GRANTED){showError("근처 기기와 알림 권한이 모두 필요해요. 앱 설정에서 허용한 뒤 다시 눌러 주세요.");refresh();return;}startConnection();}}
    private void showError(String message){new AlertDialog.Builder(this).setTitle("연결 확인").setMessage(message).setPositiveButton("확인",null).show();}
    private void refresh(){
        try{JSONObject p=Protocol.load(this);paired.setText(p==null?"등록된 노트북 없음":"등록된 노트북: "+p.optString("name","내 노트북"));}catch(Exception e){paired.setText("다시 등록이 필요해요");}
        boolean enabled=Protocol.prefs(this).getBoolean("enabled",false),ble=Protocol.prefs(this).getBoolean("ble_ok",false),relay=Protocol.prefs(this).getBoolean("relay_ok",false);
        status.setText(enabled&&!GuardService.alive?"연결이 멈췄어요. ‘연결 시작’을 눌러 주세요.":Protocol.prefs(this).getString("status","노트북 화면의 QR 코드를 읽어 주세요."));status.setTextColor(enabled&&GuardService.alive&&ble&&relay?GREEN:AMBER);
        NotificationManager manager=getSystemService(NotificationManager.class);
        NotificationChannel channel=manager.getNotificationChannel("alerts");
        boolean notifications=manager.areNotificationsEnabled()&&(channel==null||channel.getImportance()!=NotificationManager.IMPORTANCE_NONE);
        permissions.setText(getString(R.string.permission_status,notifications?"허용됨":"꺼짐",checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE)==PackageManager.PERMISSION_GRANTED?"허용됨":"허용 필요"));
        permissions.setTextColor(notifications?BLACK:RED);lastAlert.setText(Protocol.prefs(this).getString("last_alert","아직 받은 알림이 없어요."));
    }
    private final Runnable update=new Runnable(){public void run(){refresh();handler.postDelayed(this,1000);}};
    @Override public void onResume(){super.onResume();handler.post(update);}
    @Override public void onPause(){handler.removeCallbacks(update);super.onPause();}
}
