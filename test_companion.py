import json,os,sys,time,unittest,tempfile,urllib.request,urllib.error
from pathlib import Path
from cryptography.exceptions import InvalidTag
import companion
from provisioning import InstallServer

class ProtocolTests(unittest.TestCase):
    def test_pairing_round_trip(self):
        p=companion.new_pairing('한글 노트북');self.assertEqual(companion.parse_pairing(companion.pairing_code(p)),p)
    def test_wrong_server_is_rejected(self):
        p=companion.new_pairing();p['server']='http://attacker.test'
        with self.assertRaises(ValueError):companion.parse_pairing(companion.pairing_code(p))
    def test_wrong_key_length_is_rejected(self):
        p=companion.new_pairing();p['key']='AA'
        with self.assertRaises(ValueError):companion.parse_pairing(companion.pairing_code(p))
    def test_encrypt_round_trip(self):
        p=companion.new_pairing();m=companion.message('alarm','충전선 분리')
        encrypted=companion.seal(p,m)
        self.assertNotIn('충전선'.encode(),encrypted)
        self.assertEqual(companion.open_message(p,encrypted),m)
    def test_wrong_key_cannot_read(self):
        with self.assertRaises(InvalidTag):companion.open_message(companion.new_pairing(),companion.seal(companion.new_pairing(),{'x':1}))
    def test_tamper_is_rejected(self):
        p=companion.new_pairing();e=json.loads(companion.seal(p,{'x':1}));data=bytearray(companion.unb64(e['c']));data[0]^=1;e['c']=companion.b64(data)
        with self.assertRaises(InvalidTag):companion.open_message(p,json.dumps(e))
    def test_each_message_has_fresh_nonce(self):
        p=companion.new_pairing();self.assertNotEqual(companion.seal(p,{'x':1}),companion.seal(p,{'x':1}))
    @unittest.skipUnless(sys.platform=='win32','Windows only')
    def test_windows_at_rest_protection(self):
        p=companion.new_pairing();box=companion.protect_pair(p)
        self.assertNotIn(p['key'],box);self.assertEqual(companion.unprotect_pair(box),p)
    def test_pairings_are_independent(self):
        a,b=companion.new_pairing(),companion.new_pairing()
        for f in ('uuid','key','topic','ack'):self.assertNotEqual(a[f],b[f])
    def test_invalid_topic_rejected(self):
        p=companion.new_pairing();p['topic']='../../private'
        with self.assertRaises(ValueError):companion.parse_pairing(companion.pairing_code(p))

class InstallServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.apk=Path(self.tmp.name)/'test.apk';self.apk.write_bytes(b'test-apk')
        self.server=InstallServer(self.apk,host='127.0.0.1',ttl=60)
    def tearDown(self):self.server.close();self.tmp.cleanup()
    def test_apk_download(self):
        with urllib.request.urlopen(self.server.url+'/app.apk') as r:self.assertEqual(r.read(),b'test-apk')
    def test_only_exact_paths_served(self):
        for path in ('/../app.py','/app.apk?path=secret','/secret'):
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.server.url+path)
    def test_page_never_contains_pairing_secrets(self):
        with urllib.request.urlopen(self.server.url) as r:
            body=r.read();self.assertNotIn(b'LG2.',body);self.assertEqual(r.headers['Cache-Control'],'no-store')
    def test_expired_server_rejects_download(self):
        self.server.deadline=time.monotonic()-1
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(self.server.url+'/app.apk')
        self.assertEqual(caught.exception.code,410)
if __name__=='__main__':unittest.main()
