"""Temporary LAN download of the APK only. Never serves pairing secrets or arbitrary files."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import ipaddress
from pathlib import Path
import secrets
import socket
import threading
import time

class InstallServer:
    def __init__(self, apk, host=None, ttl=600):
        self.apk = Path(apk).resolve()
        if not self.apk.is_file(): raise FileNotFoundError('휴대폰 설치파일을 찾지 못했어요.')
        if host is None:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('192.0.2.1', 9)); host = s.getsockname()[0]
            if not ipaddress.ip_address(host).is_private: raise ValueError('같은 Wi-Fi 연결이 필요해요.')
        self.token = secrets.token_urlsafe(24)
        self.deadline = time.monotonic() + ttl
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if time.monotonic() > owner.deadline or not ipaddress.ip_address(self.client_address[0]).is_private:
                    self.send_error(410); return
                root = '/' + owner.token
                if self.path == root or self.path == root + '/':
                    content = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                        '<title>LaptopGuard 설치</title><style>body{font-family:sans-serif;color:#000;background:#f5f7fa;padding:26px;line-height:1.8}'
                        'a{display:block;background:#146c59;color:white;padding:16px;border-radius:12px;text-align:center;text-decoration:none}'
                        'strong{color:#1457a6}</style><h1>LaptopGuard</h1><p><strong>이 앱 하나로 근접 신호와 노트북 알림을 함께 연결해요.</strong></p>'
                        '<a href="' + root + '/app.apk">휴대폰 앱 내려받기</a><p>1. 내려받은 APK 파일을 열어 설치하세요.<br>'
                        '2. 노트북에서 ‘등록 QR 보기’를 누르세요.<br>3. 설치한 LaptopGuard 앱의 QR 읽기로 등록하세요.</p>'
                        '<p>현재 설치파일은 테스트 버전입니다. 이 링크는 10분 동안만 열립니다. 별도 ntfy·nRF 앱은 필요하지 않습니다.</p>').encode()
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(content)))
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(content)
                elif self.path == root + '/app.apk':
                    self.send_response(200);self.send_header('Content-Type','application/vnd.android.package-archive');self.send_header('Content-Length',str(owner.apk.stat().st_size))
                    self.send_header('Content-Disposition','attachment; filename="LaptopGuard-Phone.apk"');self.send_header('Cache-Control','no-store');self.end_headers()
                    try:
                        with owner.apk.open('rb') as f:
                            while block:=f.read(65536): self.wfile.write(block)
                    except (BrokenPipeError, ConnectionResetError): pass
                else: self.send_error(404)
        self.server = ThreadingHTTPServer((host, 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://{host}:{self.server.server_port}/{self.token}'
        self.closed = False
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.timer = threading.Timer(ttl, self.close); self.timer.daemon = True; self.timer.start()
    def close(self):
        if self.closed:return
        self.closed=True
        self.timer.cancel()
        self.server.shutdown();self.server.server_close()
