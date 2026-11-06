"""LaptopGuard companion v2: shared pairing format and encrypted relay messages."""
import base64
import json
import secrets
import time
import uuid
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b'LaptopGuard/2'

def b64(data): return base64.urlsafe_b64encode(data).decode().rstrip('=')
def unb64(text): return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))

def new_pairing(name='내 노트북'):
    return {'v': 2, 'server': 'https://ntfy.sh', 'topic': 'lg-' + secrets.token_hex(24),
            'ack': 'lg-' + secrets.token_hex(24), 'uuid': str(uuid.uuid4()),
            'key': b64(secrets.token_bytes(32)), 'name': name[:40]}

def pairing_code(pair):
    return 'LG2.' + b64(json.dumps(pair, ensure_ascii=False, separators=(',', ':')).encode())

def parse_pairing(code):
    if not code.startswith('LG2.') or len(code) > 2048: raise ValueError('연결 코드 형식이 올바르지 않습니다.')
    pair = json.loads(unb64(code[4:]))
    if pair.get('v') != 2 or pair.get('server') != 'https://ntfy.sh': raise ValueError('지원하지 않는 연결 코드입니다.')
    uuid.UUID(pair['uuid'])
    if len(unb64(pair['key'])) != 32: raise ValueError('암호화 키가 잘못되었습니다.')
    for field in ('topic', 'ack'):
        if not isinstance(pair.get(field), str) or not pair[field].startswith('lg-') or len(pair[field]) != 51:
            raise ValueError('알림 주소가 잘못되었습니다.')
        int(pair[field][3:], 16)
    return pair

def seal(pair, payload):
    nonce = secrets.token_bytes(12)
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    ciphertext = AESGCM(unb64(pair['key'])).encrypt(nonce, data, AAD)
    return json.dumps({'v': 2, 'n': b64(nonce), 'c': b64(ciphertext)}, separators=(',', ':')).encode()

def open_message(pair, raw):
    if len(raw) > 16384: raise ValueError('Message too large')
    envelope = json.loads(raw)
    if envelope.get('v') != 2: raise ValueError('Unsupported envelope')
    nonce = unb64(envelope['n'])
    if len(nonce) != 12: raise ValueError('Invalid nonce')
    data = AESGCM(unb64(pair['key'])).decrypt(nonce, unb64(envelope['c']), AAD)
    return json.loads(data)

def message(kind, text):
    return {'kind': kind, 'id': secrets.token_hex(16), 'time': int(time.time()), 'text': text}

# Per-user Windows encryption for the pairing secret at rest.
def protect_pair(pair):
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    raw = json.dumps(pair, ensure_ascii=False).encode()
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError()
    try: return b64(ctypes.string_at(target.data, target.size))
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)

def unprotect_pair(stored):
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    raw = unb64(stored); buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError()
    try: return parse_pairing('LG2.' + b64(ctypes.string_at(target.data, target.size)))
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)
