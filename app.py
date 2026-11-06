import asyncio
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import queue
import secrets
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import urllib.request
import urllib.parse
import winsound
import companion
from provisioning import InstallServer
from PIL import ImageTk
import qrcode
from guard_core import Guard
from alarm_audio import AlarmPlayer
from phone_names import PhoneNames
from make_icon import icon as draw_icon
import sys

DATA = Path(os.environ.get('LAPTOPGUARD_DATA', str(Path(os.environ.get('LOCALAPPDATA', '.')) / 'LaptopGuard')))
DATA.mkdir(parents=True, exist_ok=True)
CONFIG = DATA / 'settings.json'
DEFAULT = {'topic': 'laptopguard-' + secrets.token_hex(24), 'phone': '', 'auto': False, 'rssi': -75}

class Power(ctypes.Structure):
    _fields_ = [('ACLineStatus', wintypes.BYTE), ('BatteryFlag', wintypes.BYTE),
                ('BatteryLifePercent', wintypes.BYTE), ('SystemStatusFlag', wintypes.BYTE),
                ('BatteryLifeTime', wintypes.DWORD), ('BatteryFullLifeTime', wintypes.DWORD)]

def power():
    p = Power()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p)):
        return None
    return {0: False, 1: True}.get(p.ACLineStatus)

def derive(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()

class SessionEvents:
    """Receive this Windows session's lock/unlock notifications."""
    def __init__(self, root, events):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.wts = ctypes.WinDLL('wtsapi32', use_last_error=True)
        self.hwnd = root.winfo_id()
        ptr = ctypes.c_ssize_t
        self.proc_type = ctypes.WINFUNCTYPE(ptr, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        self.setter = self.user.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else self.user.SetWindowLongW
        self.setter.argtypes = [wintypes.HWND, ctypes.c_int, ptr]
        self.setter.restype = ptr
        self.user.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.CallWindowProcW.restype = ptr
        self.wts.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.wts.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
        self.callback = self.proc_type(lambda hwnd, msg, wp, lp: self.dispatch(events, hwnd, msg, wp, lp))
        self.old = self.setter(self.hwnd, -4, ctypes.cast(self.callback, ctypes.c_void_p).value)
        if not self.old:
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.wts.WTSRegisterSessionNotification(self.hwnd, 0):
            self.setter(self.hwnd, -4, self.old)
            raise ctypes.WinError(ctypes.get_last_error())

    def dispatch(self, events, hwnd, msg, wp, lp):
        if msg == 0x2B1 and wp in (7, 8):
            events.put(('session', wp))
        return self.user.CallWindowProcW(self.old, hwnd, msg, wp, lp)

    def close(self):
        self.wts.WTSUnRegisterSessionNotification(self.hwnd)
        self.setter(self.hwnd, -4, self.old)

EASY_GUIDE = '■ 처음 한 번: 휴대폰 연결\n① ‘휴대폰 연결 / 새 폰 등록’을 눌러요.\n② 설치 QR을 갤럭시 카메라로 읽고 LaptopGuard 앱을 설치해요.\n   폰과 노트북을 같은 Wi-Fi에 연결하면 설치파일을 받을 수 있어요.\n   이미 설치했다면 설치 과정은 건너뛰어요.\n③ 노트북에서 ‘등록 QR 보기’를 눌러요.\n④ 폰의 LaptopGuard 앱에서 ‘노트북 QR 코드 읽기’를 눌러요.\n⑤ 폰에서 근처 기기·알림 권한을 허용하고 연결을 시작해요.\n⑥ 노트북에서 테스트 알림을 보내요. 폰 알림의 ‘확인했어요’를 눌러요.\n⑦ 노트북에 두 가지 확인이 뜨면 ‘이 휴대폰으로 연결 완료’를 눌러요.\n안심: 새 연결이 끝나기 전에는 기존에 쓰던 연결을 유지해요.\n꼭: 연결 QR과 코드는 비밀이에요. 다른 사람에게 공유하지 마세요.\n\n■ 자리 비울 때\n① 충전기를 꽂아요. ② ‘보호 시작’을 눌러요. ③ 폰을 가지고 나가요.\n누가 충전선을 뽑으면 화면이 잠기고 경보와 폰 알림이 나와요.\n폰이 근처에 있으면 작은 확인음 후 15초 동안 주인 확인을 기다려요.\n폰을 등록하지 않아도 수동 보호와 노트북 경보는 사용할 수 있어요.\n\n■ 자동 보호\n휴대폰의 근처 신호를 확인한 뒤 신호가 8초 끊기고,\n멀어진 상태가 20초 더 이어지면 충전기 연결 중에 보호를 켜요.\n멀어지는 것만으로 경보나 폰 알림이 울리는 것은 아니에요.\n꼭: 충전선을 미리 뽑아 두면 자동 보호는 시작되지 않아요.\n\n■ 돌아왔을 때\n지문·PIN 등으로 Windows 잠금을 풀거나 앱 비밀번호로 경보를 끝내요.\n자동 보호는 60초 유예 뒤 다시 준비돼요. 원하지 않으면 체크도 꺼요.\n\n■ 창을 닫아도 실행돼요\n안심: X는 창만 숨겨요. 시계 옆 방패 아이콘에서 다시 열어요.\n완전 종료는 방패 아이콘 우클릭 → ‘프로그램 완전히 종료’예요.\n꼭: PC 종료·절전·작업 관리자 강제 종료 상태에서는 감지할 수 없어요.\n재부팅 뒤에는 PC 앱을 다시 실행해 주세요.\n\n■ 폰 연결을 유지하려면\n갤럭시 배터리 설정에서 LaptopGuard를 ‘제한 없음’으로 설정해요.\n절전 앱 목록에 넣지 말고, 폰의 연결 상태 알림을 유지해요.\n강제 종료나 권한 취소 후에는 폰 앱에서 연결 시작을 다시 눌러요.\n꼭: 폰이 꺼지거나 인터넷이 없으면 알림이 늦거나 오지 않을 수 있어요.\n경보 시 음소거를 해제하고 음량을 최소 80%로 높여요. 종료하면 이전 설정으로 돌아가요.\n폰 알림은 ntfy.sh 서버를 통해 암호화하여 전달해요. 별도 ntfy 앱은 필요 없어요.\n기존 연결을 쓰는 동안에는 이전 nRF Connect·ntfy를 계속 켜 두세요.\n새 연결을 완료하고 테스트한 뒤 이전 앱의 송출·구독을 중지하면 돼요.\n'

class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.config = DEFAULT.copy()
        try:
            self.config.update(json.loads(CONFIG.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
        self.active_pair = None
        self.pair_error = None
        if self.config.get('companion_secret'):
            try: self.active_pair = companion.unprotect_pair(self.config['companion_secret'])
            except Exception: self.pair_error = '휴대폰 등록 정보를 읽지 못했어요. 다시 연결해 주세요.'
        self.pending_pair = None
        self.pending_seen = 0
        self.pending_confirmed = False
        self.pending_phone_name = ''
        self.pair_window = None
        self.install_server = None
        self.test_requests = {}
        self.latest_test_id = None
        self.received_confirmations = set()
        self.guard = Guard()
        self.devices = {}
        self.selected_phone = self.config['phone']
        self.phone_names = PhoneNames(self.config.get('phone_aliases'))
        self.phone_names.names.update(self.config.get('phone_names', {}))
        self.phone_choices = {}
        self.tray = None
        self.tray_ready = False
        self.tray_state = None
        self.shutting_down = False
        self.last_seen = 0
        self.last_rssi = -127
        self.scanner_ok = False
        self.stop = threading.Event()
        self.alarm = threading.Event()
        self.lock_seen = False
        self.failures = 0
        self.retry_at = 0
        root.title('LaptopGuard 2 · 노트북 지킴이')
        root.geometry('860x820')
        root.minsize(780, 700)
        asset = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'LaptopGuard.ico'
        if asset.exists():
            root.iconbitmap(str(asset))
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', foreground='#000000')
        style.configure('TLabel', font=('맑은 고딕', 10), foreground='#000000')
        style.configure('TButton', font=('맑은 고딕', 10), padding=8, foreground='#000000')
        style.configure('TCheckbutton', foreground='#000000')
        self.topic = tk.StringVar(value=self.config['topic'])
        self.phone = tk.StringVar(value='')
        self.phone_hint = tk.StringVar()
        self.auto = tk.BooleanVar(value=self.config['auto'])
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='LaptopGuard', font=('맑은 고딕', 24, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='충전선을 뽑으면 잠금 + 경보 + 휴대폰 알림').pack(anchor='w', pady=(0, 10))
        self.status = tk.StringVar(value='대기 중')
        self.status_label = ttk.Label(frame, textvariable=self.status, font=('맑은 고딕', 18, 'bold'))
        self.status_label.pack(anchor='w')
        self.hardware = tk.StringVar()
        ttk.Label(frame, textvariable=self.hardware).pack(anchor='w', pady=8)
        buttons = ttk.Frame(frame); buttons.pack(fill='x')
        ttk.Button(buttons, text='보호 시작', command=self.arm).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='비밀번호로 보호 / 경보 종료', command=self.disarm).pack(side='left')
        ttk.Button(buttons, text='비밀번호 설정', command=self.password).pack(side='right')
        ttk.Label(frame, text='① 충전기 꽂기 → ② 보호 시작 → ③ 휴대폰 가지고 이동하기',
                  foreground='#1457a6', font=('맑은 고딕', 11, 'bold')).pack(anchor='w', pady=(12, 4))
        ttk.Label(frame,text='경보는 무음이어도 소리 나게 해요. 종료하면 원래 음량으로 돌아가요.',foreground='#9b5200').pack(anchor='w',pady=(0,3))
        ttk.Label(frame, text='창을 X로 닫아도 감시는 계속돼요. 시계 옆 방패 아이콘에서 다시 열어요.',
                  foreground='#146c43').pack(anchor='w')
        tabs = ttk.Notebook(frame); tabs.pack(fill='both', expand=True, pady=12)
        phonepage = ttk.Frame(tabs, padding=16); guide = ttk.Frame(tabs, padding=16)
        tabs.add(phonepage, text='휴대폰 연결'); tabs.add(guide, text='쉬운 사용 방법')
        ttk.Label(phonepage, text='휴대폰 앱은 이제 하나만 쓰세요', font=('맑은 고딕', 15, 'bold'), foreground='#1457a6').pack(anchor='w')
        ttk.Label(phonepage, text='LaptopGuard 전용 앱에서 근접 신호와 알림을 함께 연결해요.\n주변 기기 목록에서 내 폰을 찾거나 알림 주소를 옮겨 적을 필요가 없어요.',
                  wraplength=740).pack(anchor='w', pady=8)
        self.connection_summary = tk.StringVar()
        self.connection_label = ttk.Label(phonepage, textvariable=self.connection_summary, font=('맑은 고딕', 12, 'bold'), wraplength=740)
        self.connection_label.pack(anchor='w', pady=10)
        row=ttk.Frame(phonepage);row.pack(fill='x')
        ttk.Button(row, text='휴대폰 연결 / 새 폰 등록', command=self.open_pairing).pack(side='left')
        ttk.Button(row, text='폰에 테스트 알림 보내기', command=self.test_phone).pack(side='left', padx=6)
        ttk.Button(row, text='연결 해제', command=self.remove_pairing).pack(side='left')
        self.test_status=tk.StringVar(value='처음에는 테스트 알림을 보내고, 폰에서 ‘확인했어요’를 눌러 주세요.')
        self.test_label=ttk.Label(phonepage,textvariable=self.test_status,wraplength=740,foreground='#9b5200')
        self.test_label.pack(anchor='w',pady=10)
        ttk.Separator(phonepage).pack(fill='x',pady=8)
        ttk.Checkbutton(phonepage, text='내가 휴대폰을 가지고 멀어지면, 알아서 보호 시작', variable=self.auto,
                        command=self.save_settings).pack(anchor='w', pady=4)
        ttk.Label(phonepage, text='휴대폰이 멀어지면 먼저 보호를 켜요. 충전선을 뽑을 때 경보가 울려요.\n충전기를 미리 뽑아 두면 자동 보호는 시작되지 않아요.',
                  wraplength=740).pack(anchor='w', pady=5)
        ttk.Label(phonepage,text='설치 → QR 등록 → 테스트 확인, 처음 한 번이면 끝나요.', foreground='#1457a6', font=('맑은 고딕', 11, 'bold')).pack(anchor='w',pady=(14,4))
        ttk.Label(phonepage,text='폰에서 근처 기기·알림 권한은 직접 허용해 주세요.\n갤럭시 배터리는 ‘제한 없음’으로 설정하고 연결 상태 알림을 켜 두세요.',
                  foreground='#9b5200',wraplength=740).pack(anchor='w')
        helptext=tk.Text(guide,wrap='word',font=('맑은 고딕',11),foreground='#000000',background='#ffffff',borderwidth=0,height=16)
        scroll=ttk.Scrollbar(guide,command=helptext.yview);scroll.pack(side='right',fill='y')
        helptext.configure(yscrollcommand=scroll.set);helptext.pack(fill='both',expand=True)
        helptext.tag_configure('heading',foreground='#1457a6',font=('맑은 고딕',12,'bold'))
        helptext.tag_configure('important',foreground='#9b5200')
        helptext.tag_configure('safe',foreground='#146c43')
        helptext.insert('1.0',EASY_GUIDE)
        for number,line in enumerate(EASY_GUIDE.splitlines(),1):
            if line.startswith('■'):helptext.tag_add('heading',f'{number}.0',f'{number}.end')
            elif line.startswith('꼭:'):helptext.tag_add('important',f'{number}.0',f'{number}.end')
            elif line.startswith('안심:'):helptext.tag_add('safe',f'{number}.0',f'{number}.end')
        helptext.configure(state='disabled')
        self.logbox=tk.Text(frame,height=4,state='disabled',font=('맑은 고딕',9),foreground='#000000',background='#ffffff')
        self.logbox.tag_configure('error',foreground='#b42318');self.logbox.tag_configure('success',foreground='#146c43')
        self.logbox.pack(fill='x',pady=(8,0))
        root.update_idletasks()
        try:
            self.session = SessionEvents(root, self.events)
            self.log('Windows 잠금 해제 감지 연결됨')
        except Exception as e:
            self.session = None
            self.log('잠금 해제 감지 실패: ' + str(e))
        if self.pair_error: self.log(self.pair_error)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.start_tray()
        self.sync_awake()
        threading.Thread(target=self.scan_thread, daemon=True).start()
        self.sound_worker=threading.Thread(target=self.sound_thread, daemon=True)
        self.sound_worker.start()
        root.after(250, self.tick)

    def log(self, text):
        self.logbox.configure(state='normal')
        tag = 'error' if any(w in text for w in ('실패','경보!','오류')) else 'success' if any(w in text for w in ('완료','성공','확인 응답')) else ''
        self.logbox.insert('end', time.strftime('%H:%M:%S ') + text + '\n', tag)
        self.logbox.see('end')
        self.logbox.configure(state='disabled')

    def save(self):
        temp = CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(CONFIG)

    def save_settings(self):
        topic = self.topic.get().strip()
        if not topic or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in topic):
            messagebox.showerror('설정', '주제에는 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.')
            return False
        if self.guard.state != 'idle':
            messagebox.showinfo('설정', '보호 종료 후 설정을 변경하세요.')
            self.auto.set(self.config['auto'])
            return False
        selected = self.selected_phone
        if self.auto.get() and ((not selected and not self.active_pair) or not self.config.get('hash')):
            self.auto.set(self.config['auto'])
            messagebox.showinfo('자동 보호 준비', '먼저 비밀번호를 설정하고, 휴대폰 연결을 완료해 주세요.')
            return False
        if selected != self.config['phone']:
            self.last_seen = 0
            self.guard.seen_phone = False
            self.guard.away_since = None
        self.config.update(topic=topic, phone=selected, auto=self.auto.get(),
                           phone_aliases=self.phone_names.aliases, phone_names=self.phone_names.names)
        self.save()
        self.sync_awake()
        self.log('설정 저장됨')
        return True

    def authenticate(self):
        if time.monotonic() < self.retry_at:
            messagebox.showinfo('잠시 대기', '비밀번호 오류가 반복되었습니다. 30초 후 다시 시도하세요.')
            return False
        pw = simpledialog.askstring('본인 확인', '앱 비밀번호', show='*', parent=self.root)
        if pw is None:
            return False
        valid = bool(self.config.get('hash')) and hmac.compare_digest(derive(pw, self.config['salt']), self.config['hash'])
        if not valid:
            self.failures += 1
            if self.failures >= 5:
                self.retry_at = time.monotonic() + 30
                self.failures = 0
            messagebox.showerror('본인 확인', '비밀번호가 일치하지 않습니다.')
        else:
            self.failures = 0
        return valid

    def password(self):
        if self.config.get('hash') and not self.authenticate():
            return
        pw = simpledialog.askstring('비밀번호 설정', '새 비밀번호 (8자 이상)', show='*', parent=self.root)
        if pw is None:
            return
        if len(pw) < 8:
            messagebox.showerror('설정', '8자 이상 입력하세요.')
            return
        if pw != simpledialog.askstring('비밀번호 확인', '다시 입력', show='*', parent=self.root):
            messagebox.showerror('설정', '입력이 다릅니다.')
            return
        salt = secrets.token_hex(16)
        self.config.update(salt=salt, hash=derive(pw, salt))
        self.save()
        self.log('비밀번호 설정 완료')

    def arm(self):
        if self.guard.state != 'idle':
            return
        if not self.config.get('hash'):
            self.password()
        if not self.config.get('hash'):
            return
        if not self.save_settings():
            return
        try:
            self.handle(self.guard.arm(power()))
        except ValueError as e:
            messagebox.showerror('보호 시작', str(e))

    def disarm(self):
        if self.authenticate():
            self.handle(self.guard.disarm(time.monotonic()))

    def notify(self, message, test=False):
        if self.active_pair:
            return self.send_companion(self.active_pair, 'test' if test else 'alarm', message)
        if test and not self.save_settings():
            return
        topic = self.config['topic']
        def send():
            for attempt in range(3):
                try:
                    req = urllib.request.Request('https://ntfy.sh/' + urllib.parse.quote(topic, safe=''),
                        data=message.encode('utf-8'), headers={'Title': 'LaptopGuard', 'Priority': '5', 'Tags': 'warning'})
                    with urllib.request.urlopen(req, timeout=8) as response:
                        response.read(1024)
                    self.events.put(('log', '알림 서버 전송 성공 (휴대폰 수신 여부는 폰에서 확인)'))
                    return
                except Exception as e:
                    if attempt == 2:
                        self.events.put(('log', '휴대폰 알림 전송 실패: ' + str(e)))
                    else:
                        self.stop.wait(2 ** attempt)
        threading.Thread(target=send, daemon=True).start()

    def handle(self, events):
        for event in events:
            if event == 'armed':
                self.log('보호 시작: 충전선 분리를 감시합니다.')
                self.sync_awake()
            elif event == 'lock':
                self.lock_seen = False
                if not ctypes.windll.user32.LockWorkStation():
                    self.log('화면 잠금 요청 실패. Windows 상태를 확인하세요.')
            elif event == 'confirm':
                self.log('휴대폰 근처: 15초 안에 Windows 잠금을 해제하세요.')
                threading.Thread(target=lambda: (winsound.Beep(880, 120), winsound.Beep(1175, 160)), daemon=True).start()
            elif event == 'alarm':
                self.log('경보! 충전선이 분리되었습니다.')
                self.alarm.set()
                self.notify('충전선 분리 감지! 노트북을 확인하세요.')
            elif event == 'disarmed':
                self.alarm.clear()
                self.sync_awake()
                self.log('보호 / 경보 종료. 자동 보호 재진입은 60초 후 가능합니다.')

    def scan_thread(self):
        try:
            from bleak import BleakScanner
            def detected(device, advertisement):
                self.events.put(('ble', (device.address, advertisement.local_name or device.name or '', advertisement.rssi)))
                self.events.put(('beacon', (tuple(u.lower() for u in advertisement.service_uuids), advertisement.rssi)))
            async def run():
                async with BleakScanner(detection_callback=detected):
                    self.events.put(('scanner', True))
                    while not self.stop.is_set():
                        await asyncio.sleep(0.5)
            asyncio.run(run())
        except Exception as e:
            self.events.put(('scanner', False))
            self.events.put(('log', 'BLE 감지 사용 불가: ' + str(e) + ' (수동 보호는 사용 가능)'))

    def sound_thread(self):
        while not self.stop.is_set():
            if not self.alarm.wait(0.2):
                continue
            player=AlarmPlayer(DATA/'alarm-siren.wav',lambda message:self.events.put(('log',message)))
            try:
                player.start()
                while self.alarm.is_set() and not self.stop.is_set():
                    player.enforce()
                    self.stop.wait(0.25)
            except Exception as error:
                self.events.put(('log','경보음 재생 실패: '+str(error)))
                self.stop.wait(1)
            finally:
                player.close()

    def tick(self):
        now = time.monotonic()
        for _ in range(500):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                self.log(value)
            elif kind == 'tray':
                if value == 'ready':
                    self.tray_ready = True
                    self.log('시계 옆 방패 아이콘 준비 완료 · 창을 닫아도 실행됩니다.')
                elif value == 'open':
                    self.show_window()
                elif value == 'disarm':
                    self.show_window()
                    self.disarm()
                elif value == 'exit':
                    self.request_exit()
                    if self.shutting_down:
                        return
            elif kind == 'tray_error':
                self.tray_ready = False
                self.show_window()
                self.log('트레이 아이콘 오류: ' + value)
            elif kind == 'scanner':
                self.scanner_ok = value
            elif kind == 'ble':
                address, name, rssi = value
                self.phone_names.remember(address, name)
                self.devices[address] = (name, rssi, now)
                if not self.active_pair and address == self.config['phone']:
                    self.last_rssi = rssi
                    if rssi >= self.config['rssi']:
                        self.last_seen = now
            elif kind == 'beacon':
                uuids, rssi = value
                if self.active_pair and self.active_pair['uuid'].lower() in uuids:
                    self.last_rssi = rssi
                    if rssi >= self.config['rssi']: self.last_seen = now
                if self.pending_pair and self.pending_pair['uuid'].lower() in uuids and rssi >= self.config['rssi']:
                    self.pending_seen = now
            elif kind == 'companion_ack':
                request_id, phone_name = value
                if request_id in self.test_requests:
                    pair_id = self.test_requests[request_id][0]
                    self.received_confirmations.add(request_id)
                    if self.pending_pair and pair_id == self.pending_pair['uuid']:
                        self.pending_confirmed = True
                        self.pending_phone_name = phone_name
                    if self.active_pair and pair_id == self.active_pair['uuid']:
                        self.test_status.set('마지막 테스트: 폰에서 알림을 확인했어요. 연결 확인 완료!')
                        self.test_label.configure(foreground='#146c43')
                    self.log('휴대폰에서 확인 응답을 받았어요.')
            elif kind == 'test_timeout':
                pair_id = self.test_requests.get(value, (None,))[0]
                relevant = (self.pending_pair and pair_id == self.pending_pair['uuid']) or (self.active_pair and pair_id == self.active_pair['uuid'])
                if value == self.latest_test_id and relevant and value not in self.received_confirmations:
                    self.test_status.set('아직 폰 확인 응답이 없어요. 폰 인터넷·알림 권한을 확인하고 다시 테스트해 주세요.')
                    self.test_label.configure(foreground='#9b5200')
            elif kind == 'session':
                if value == 7:
                    self.lock_seen = True
                elif value == 8 and self.lock_seen:
                    self.lock_seen = False
                    if self.guard.state != 'idle':
                        self.handle(self.guard.disarm(now))
        self.refresh_phones(now)
        self.update_tray()
        ac = power()
        near = self.last_seen > 0 and now - self.last_seen < 8
        auto = self.config['auto'] and bool(self.config.get('hash')) and bool(self.config['phone'] or self.active_pair)
        self.handle(self.guard.tick(now, ac, near, auto, self.scanner_ok))
        labels = {'idle': '대기 중', 'armed': '보호 중 · 충전선 감시', 'confirm': f'본인 확인 대기 · {max(0, int(self.guard.deadline-now))}초', 'alarm': '경보 발생 · 본인 인증으로 종료'}
        self.status.set(labels[self.guard.state])
        self.status_label.configure(foreground={'idle':'#000000','armed':'#146c43','confirm':'#9b5200','alarm':'#b42318'}[self.guard.state])
        self.update_pairing_ui(now)
        self.hardware.set(f"전원: { {True:'연결됨',False:'배터리',None:'확인 불가'}[ac]}  |  휴대폰: {'근처' if near else '미감지 / 멀리 있음'}  |  BLE: {'스캔 중' if self.scanner_ok else '사용 불가'}")
        self.root.after(250, self.tick)

    def test_phone(self):
        if self.active_pair:
            self.send_companion(self.active_pair, 'test', 'LaptopGuard 연결 테스트입니다. 아래 ‘확인했어요’를 눌러 주세요.')
        else:
            self.notify('LaptopGuard 테스트 알림', True)
            self.test_status.set('기존 방식으로 보냈어요. 새 전용 앱은 ‘휴대폰 연결’에서 등록하세요.')

    def send_companion(self, pair, kind, text):
        payload = companion.message(kind, text)
        if kind == 'test':
            self.latest_test_id = payload['id']
            if len(self.test_requests) >= 32:
                oldest = next(iter(self.test_requests)); self.test_requests.pop(oldest, None); self.received_confirmations.discard(oldest)
            self.test_requests[payload['id']] = (pair['uuid'], time.monotonic())
            self.test_status.set('테스트 전송 중 · 폰 알림을 펼쳐 ‘확인했어요’를 눌러 주세요.')
            self.test_label.configure(foreground='#9b5200')
        def send():
            for attempt in range(3):
                if self.stop.is_set(): return
                try:
                    req = urllib.request.Request(pair['server'] + '/' + pair['topic'], data=companion.seal(pair, payload),
                        headers={'Content-Type':'text/plain; charset=utf-8','Title':'LaptopGuard','Priority':'5'})
                    with urllib.request.urlopen(req, timeout=8) as response: response.read(1024)
                    self.events.put(('log', '암호화 알림 서버 전송 성공 · 실제 수신은 폰에서 확인하세요.'))
                    if kind == 'test': self.watch_confirmation(pair, payload['id'])
                    return
                except Exception:
                    if attempt == 2:
                        self.events.put(('log', '휴대폰 알림 전송 실패 · 노트북 인터넷을 확인하세요.'))
                        if kind == 'test': self.events.put(('test_timeout', payload['id']))
                    else: self.stop.wait(2 ** attempt)
        threading.Thread(target=send, daemon=True).start()

    def watch_confirmation(self, pair, request_id):
        deadline = time.monotonic() + 150
        since = int(time.time()) - 10
        url = pair['server'] + '/' + pair['ack'] + '/json?poll=1&since=' + str(since)
        while time.monotonic() < deadline and not self.stop.is_set():
            try:
                with urllib.request.urlopen(url, timeout=8) as response: data = response.read(65536)
                for line in data.splitlines():
                    try:
                        event = json.loads(line)
                        if event.get('event') != 'message': continue
                        payload = companion.open_message(pair, event['message'])
                        if payload.get('kind') != 'confirmed' or payload.get('id') != request_id: continue
                        if abs(time.time() - float(payload['time'])) > 600: continue
                        name = ' '.join(str(payload.get('phone','내 갤럭시')).split())[:60]
                        self.events.put(('companion_ack', (request_id, name)))
                        return
                    except Exception: continue
            except Exception: pass
            self.stop.wait(3)
        self.events.put(('test_timeout', request_id))

    def update_pairing_ui(self, now):
        if self.active_pair:
            name = self.config.get('companion_name', '내 갤럭시')
            near = self.last_seen > 0 and now - self.last_seen < 8
            self.connection_summary.set(name + (' · 근처 신호 확인됨' if near else ' · 지금은 근처 신호가 안 보여요'))
            self.connection_label.configure(foreground='#146c43' if near and self.scanner_ok else '#9b5200')
        elif self.config.get('phone'):
            name = self.phone_names.aliases.get(self.config['phone']) or self.phone_names.names.get(self.config['phone']) or '등록한 휴대폰'
            self.connection_summary.set(name + ' · 기존 연결 사용 중 (전용 앱 연결 후 전환)')
            self.connection_label.configure(foreground='#9b5200')
        else:
            self.connection_summary.set('아직 휴대폰을 연결하지 않았어요. 아래 연결 버튼을 눌러 주세요.')
            self.connection_label.configure(foreground='#9b5200')
        if self.pair_window is not None and self.pending_pair:
            near = self.pending_seen > 0 and now - self.pending_seen < 8 and self.scanner_ok
            self.pair_beacon_label.configure(text='① 근접 신호: ' + ('확인 완료' if near else '폰에서 연결 시작 후 노트북 가까이에 두세요'), foreground='#146c43' if near else '#9b5200')
            self.pair_test_label.configure(text='② 폰 알림: ' + ('직접 확인 완료' if self.pending_confirmed else '테스트 알림의 ‘확인했어요’를 눌러 주세요'),foreground='#146c43' if self.pending_confirmed else '#9b5200')
            self.pair_finish_button.configure(state='normal' if near and self.pending_confirmed else 'disabled')

    def open_pairing(self):
        if self.guard.state != 'idle':
            messagebox.showinfo('휴대폰 연결', '먼저 보호를 끝낸 뒤 휴대폰을 연결해 주세요.'); return
        if self.pair_window is not None:
            self.pair_window.lift(); return
        self.pending_pair = companion.new_pairing()
        self.pending_seen = 0; self.pending_confirmed = False; self.pending_phone_name = ''
        window = tk.Toplevel(self.root); self.pair_window = window
        window.title('LaptopGuard · 휴대폰 한 번 연결하기'); window.geometry('720x820');window.minsize(660,740)
        box=ttk.Frame(window,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='앱 하나로, 한 번만 연결해요',foreground='#1457a6',font=('맑은 고딕',16,'bold')).pack(anchor='w')
        ttk.Label(box,text='① 폰 앱 설치 → ② 등록 QR 읽기 → ③ 테스트 확인',foreground='#1457a6').pack(anchor='w',pady=6)
        row=ttk.Frame(box);row.pack(fill='x')
        ttk.Button(row,text='1. 앱 설치 QR 보기',command=self.show_install_qr).pack(side='left')
        ttk.Button(row,text='2. 등록 QR 보기',command=self.show_registration_qr).pack(side='left',padx=5)
        ttk.Button(row,text='설치파일 폴더 열기',command=self.open_apk_folder).pack(side='left')
        self.qr_instructions=tk.StringVar()
        ttk.Label(box,textvariable=self.qr_instructions,wraplength=650).pack(anchor='w',pady=8)
        self.qr_label=ttk.Label(box,anchor='center');self.qr_label.pack(fill='x')
        ttk.Label(box,text='등록 QR과 연결 코드는 다른 사람에게 공유하지 마세요.',foreground='#9b5200').pack(anchor='w',pady=6)
        row=ttk.Frame(box);row.pack(fill='x')
        ttk.Button(row,text='QR 대신 연결 코드 복사',command=self.copy_pairing_code).pack(side='left')
        ttk.Button(row,text='3. 폰에 테스트 알림 보내기',command=self.test_pending_phone).pack(side='left',padx=5)
        self.pair_beacon_label=ttk.Label(box,text='① 근접 신호 확인 대기',wraplength=650);self.pair_beacon_label.pack(anchor='w',pady=(10,4))
        self.pair_test_label=ttk.Label(box,text='② 폰 알림 확인 대기',wraplength=650);self.pair_test_label.pack(anchor='w',pady=4)
        self.pair_finish_button=ttk.Button(box,text='이 휴대폰으로 연결 완료',command=self.finish_pairing,state='disabled');self.pair_finish_button.pack(anchor='w',pady=8)
        ttk.Label(box,text='설치 QR은 같은 Wi-Fi에서 10분만 열려요. 연결이 안 되면 APK를 USB나 Quick Share로 폰에 옮겨 설치할 수 있어요. Windows 방화벽 설정을 자동으로 바꾸지 않습니다.',
                  wraplength=650).pack(anchor='w')
        window.protocol('WM_DELETE_WINDOW',self.close_pairing)
        self.show_registration_qr()

    def set_qr(self, value):
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=6,border=4);qr.add_data(value);qr.make(fit=True)
        qr.box_size=max(3,330 // (qr.modules_count + 8))
        picture=qr.make_image(fill_color='black',back_color='white').convert('RGB')
        self.qr_image=ImageTk.PhotoImage(picture)
        self.qr_label.configure(image=self.qr_image)

    def show_registration_qr(self):
        if not self.pending_pair:return
        self.qr_instructions.set('폰에 LaptopGuard를 설치했다면 앱의 ‘노트북 QR 코드 읽기’로 아래 코드를 읽으세요. 근처 기기·알림 권한을 허용하고 연결을 시작해 주세요.')
        self.set_qr(companion.pairing_code(self.pending_pair))

    def apk_path(self):
        folder=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
        return folder / 'LaptopGuard-Phone.apk'

    def show_install_qr(self):
        try:
            if self.install_server is None or self.install_server.closed:
                self.install_server=InstallServer(self.apk_path())
            self.qr_instructions.set('폰과 노트북을 같은 Wi-Fi에 연결한 뒤, 갤럭시 기본 카메라로 읽어 설치파일을 받으세요. 설치 후 위의 ‘2. 등록 QR 보기’를 누르세요. 테스트용 APK이며 스토어 배포판이 아닙니다.')
            self.set_qr(self.install_server.url)
        except Exception:
            messagebox.showinfo('설치파일 전달','같은 Wi-Fi 다운로드를 준비하지 못했어요. ‘설치파일 폴더 열기’를 눌러 APK를 USB나 Quick Share로 폰에 옮겨 주세요.',parent=self.pair_window)

    def open_apk_folder(self):
        os.startfile(str(self.apk_path().parent))

    def copy_pairing_code(self):
        if self.pending_pair:
            self.root.clipboard_clear();self.root.clipboard_append(companion.pairing_code(self.pending_pair))
            self.log('연결 코드를 복사했어요. 폰 앱의 ‘연결 코드 붙여넣기’에 넣으세요. 코드는 비밀로 보관하세요.')

    def test_pending_phone(self):
        if not self.pending_pair:return
        self.pending_confirmed=False
        self.send_companion(self.pending_pair,'test','새 노트북 연결 테스트입니다. 이 알림의 ‘확인했어요’를 눌러 주세요.')

    def finish_pairing(self):
        if self.guard.state!='idle':
            messagebox.showinfo('휴대폰 연결','먼저 보호를 끝내 주세요.',parent=self.pair_window);return
        if not self.pending_pair or not self.pending_confirmed or time.monotonic()-self.pending_seen>=8 or not self.scanner_ok:return
        pair=self.pending_pair
        try: secret=companion.protect_pair(pair)
        except Exception:
            messagebox.showerror('연결 저장','Windows 보안 저장소에 연결 정보를 저장하지 못했어요. 기존 연결을 유지합니다.',parent=self.pair_window);return
        previous=self.config.copy()
        self.config.update(companion_secret=secret,companion_name=self.pending_phone_name or '내 갤럭시',phone='')
        try: self.save()
        except OSError:
            self.config=previous
            messagebox.showerror('연결 저장','설정을 저장하지 못했어요. 기존 연결을 유지합니다.',parent=self.pair_window);return
        self.active_pair=pair;self.selected_phone='';self.last_seen=self.pending_seen;self.guard.seen_phone=True;self.guard.away_since=None
        self.close_pairing()
        self.test_status.set('새 휴대폰 연결 완료! 이제 이전 nRF Connect·ntfy 앱은 사용하지 않아도 됩니다.')
        self.test_label.configure(foreground='#146c43');self.log('전용 휴대폰 연결 완료 · 근접 신호와 알림 수신을 모두 확인했어요.')

    def close_pairing(self):
        if self.install_server:
            self.install_server.close();self.install_server=None
        if self.pair_window is not None:self.pair_window.destroy()
        self.pair_window=None;self.pending_pair=None;self.pending_seen=0;self.pending_confirmed=False

    def remove_pairing(self):
        if self.guard.state!='idle':messagebox.showinfo('연결 해제','먼저 보호를 끝내 주세요.');return
        if self.config.get('hash') and not self.authenticate():return
        if not messagebox.askyesno('휴대폰 연결 해제','자동 보호와 폰 알림 연결을 해제할까요? 노트북 수동 경보는 계속 사용할 수 있어요.'):return
        self.active_pair=None;self.config.pop('companion_secret',None);self.config.pop('companion_name',None)
        self.config.update(phone='',auto=False,topic='laptopguard-'+secrets.token_hex(24))
        self.selected_phone='';self.last_seen=0;self.auto.set(False);self.topic.set(self.config['topic']);self.guard.seen_phone=False
        self.save();self.sync_awake();self.test_status.set('휴대폰 연결을 해제했어요. 폰 앱에서도 연결을 멈춰 주세요.')

    def select_phone(self, event=None):
        self.selected_phone = self.phone_choices.get(self.phone.get(), self.selected_phone)

    def refresh_phones(self, now):
        # Legacy identity is retained until a verified companion pairing replaces it.
        pass

    def rename_phone(self):
        if self.guard.state != 'idle':
            messagebox.showinfo('이름 변경', '먼저 보호를 끝내 주세요.')
            return
        if not self.selected_phone:
            messagebox.showinfo('휴대폰 선택', '목록에서 내 휴대폰을 먼저 골라 주세요.')
            return
        name = simpledialog.askstring('휴대폰 이름',
            '내 폰인지 확인한 기기에만 이름을 붙여 주세요.\n예: 내 갤럭시, 현철이 폰\n(이름을 바꿔도 기기의 주인이 확인되는 것은 아니에요.)',
            initialvalue=self.phone_names.aliases.get(self.selected_phone, ''), parent=self.root)
        if name is None:
            return
        name = ' '.join(name.split())[:40]
        if not name:
            return
        self.phone_names.aliases[self.selected_phone] = name
        self.config['phone_aliases'] = dict(self.phone_names.aliases)
        self.save()
        self.refresh_phones(time.monotonic())
        self.log('목록에 표시할 이름을 저장했어요: ' + name)

    def copy_topic(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.topic.get().strip())
        self.log('알림 주소를 복사했어요. 폰의 ntfy에 같은 주소를 넣어 주세요.')

    def sync_awake(self):
        watching = self.guard.state != 'idle' or self.config.get('auto', False)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001 if watching else 0x80000000)

    def start_tray(self):
        try:
            import pystray
            self.tray = pystray.Icon('LaptopGuard', draw_icon('#51dbc0'), 'LaptopGuard · 시작 중',
                pystray.Menu(
                    pystray.MenuItem('창 열기', lambda *_: self.events.put(('tray', 'open')), default=True),
                    pystray.MenuItem('보호 / 경보 해제…', lambda *_: self.events.put(('tray', 'disarm'))),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem('프로그램 완전히 종료…', lambda *_: self.events.put(('tray', 'exit')))))
            def setup(tray):
                tray.visible = True
                self.events.put(('tray', 'ready'))
            def run():
                try:
                    self.tray.run(setup=setup)
                except Exception as e:
                    self.events.put(('tray_error', str(e)))
            threading.Thread(target=run, daemon=True).start()
        except Exception as e:
            self.log('트레이 아이콘을 만들지 못했어요: ' + str(e))

    def update_tray(self):
        state = self.guard.state
        if state == 'idle' and self.config.get('auto'):
            state = 'auto'
        if self.tray_ready and self.tray and state != self.tray_state:
            titles = {'idle': '대기 중', 'armed': '보호 중', 'confirm': '주인 확인 중', 'alarm': '경보 발생', 'auto': '휴대폰 이탈 감시 중'}
            colors = {'idle': '#72b8ff', 'armed': '#51dbc0', 'confirm': '#ffc65c', 'alarm': '#ff657a', 'auto': '#a89cff'}
            try:
                self.tray.title = 'LaptopGuard · ' + titles[state]
                self.tray.icon = draw_icon(colors[state])
                self.tray_state = state
            except Exception as e:
                self.tray_ready = False
                self.root.deiconify()
                self.log('트레이 연결이 끊겼어요: ' + str(e))

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def close(self):
        if not self.tray_ready:
            messagebox.showinfo('창 닫기', '시계 옆 아이콘이 아직 준비되지 않았어요.\n감시가 꺼지지 않도록 창을 열어 둘게요.')
            return
        self.log('창을 숨겼어요. 시계 옆 방패 아이콘에서 다시 열 수 있어요.')
        self.root.withdraw()
        try:
            self.tray.notify('계속 실행 중이에요. 방패 아이콘을 눌러 다시 여세요.', 'LaptopGuard')
        except Exception:
            pass

    def request_exit(self):
        self.show_window()
        if (self.guard.state != 'idle' or self.config.get('auto')) and not self.authenticate():
            return
        if messagebox.askyesno('프로그램 종료', '완전히 종료하면 노트북을 지켜보지 않아요.\n종료할까요?', parent=self.root):
            self.shutdown()

    def shutdown(self):
        self.shutting_down = True
        self.alarm.clear()
        self.stop.set()
        worker=getattr(self,'sound_worker',None)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=3)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        if self.install_server: self.install_server.close()
        if self.tray:
            self.tray.stop()
        if self.session:
            self.session.close()
        self.root.destroy()

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        def finish():
            result = {'session_hook': bool(app.session), 'ac': power(), 'ble_scanner': app.scanner_ok,
                      'tray_ready': app.tray_ready, 'log': app.logbox.get('1.0', 'end')}
            Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            app.shutdown()
        root.after(3000, finish)
        root.mainloop()
    else:
        App(tk.Tk()).root.mainloop()
