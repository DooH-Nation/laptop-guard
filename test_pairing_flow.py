import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import tkinter as tk
os.environ.setdefault('LAPTOPGUARD_DATA',str(Path('work/v2-unit-data').resolve()))
import app
import companion

class PairingFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.file=Path(self.tmp.name)/'settings.json'
        self.old={'topic':'legacy-topic','phone':'OLD-ADDRESS','auto':False,'phone_names':{'OLD-ADDRESS':'내 갤럭시'}}
        self.file.write_text(json.dumps(self.old),encoding='utf-8')
        self.patches=[patch.object(app,'CONFIG',self.file),patch.object(app.App,'scan_thread',lambda _:None),
            patch.object(app.App,'sound_thread',lambda _:None),patch.object(app.App,'start_tray',lambda _:None),
            patch.object(app,'SessionEvents',lambda *_:SimpleNamespace(close=lambda:None)),patch.object(app,'power',lambda:True)]
        for p in self.patches:p.start()
        self.root=tk.Tk();self.root.withdraw();self.a=app.App(self.root)
    def tearDown(self):
        if not self.a.shutting_down:self.a.shutdown()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def pending(self):
        self.a.open_pairing();self.a.pair_window.withdraw();self.a.scanner_ok=True
        return self.a.pending_pair
    def beacon(self,pair,rssi=-60):
        self.a.events.put(('beacon',([pair['uuid']],rssi)));self.a.tick()
    def acknowledge(self,pair,request_id='1'*32):
        self.a.test_requests[request_id]=(pair['uuid'],time.monotonic())
        self.a.events.put(('companion_ack',(request_id,'Galaxy S24 Ultra')));self.a.tick()
    def test_legacy_config_survives_open_and_cancel(self):
        self.pending();self.a.close_pairing()
        self.assertEqual(self.a.config['phone'],'OLD-ADDRESS');self.assertNotIn('companion_secret',self.a.config)
        self.assertEqual(json.loads(self.file.read_text(encoding='utf-8')),self.old)
    def test_cannot_finish_without_phone_confirmation(self):
        p=self.pending();self.beacon(p);self.a.finish_pairing()
        self.assertIsNone(self.a.active_pair)
    def test_cannot_finish_without_recent_beacon(self):
        p=self.pending();self.acknowledge(p);self.a.finish_pairing()
        self.assertIsNone(self.a.active_pair)
    def test_unknown_ack_is_ignored(self):
        self.pending();self.a.events.put(('companion_ack',('unknown','Wrong phone')));self.a.tick()
        self.assertFalse(self.a.pending_confirmed)
    def test_ack_from_old_pair_does_not_confirm_new_pair(self):
        self.pending();self.acknowledge(companion.new_pairing())
        self.assertFalse(self.a.pending_confirmed)
    def test_confirmed_pair_is_saved_encrypted(self):
        p=self.pending();self.beacon(p);self.acknowledge(p);self.a.finish_pairing()
        self.assertEqual(self.a.active_pair,p);self.assertEqual(self.a.config['companion_name'],'Galaxy S24 Ultra')
        saved=json.loads(self.file.read_text(encoding='utf-8'));self.assertNotIn(p['key'],json.dumps(saved));self.assertEqual(companion.unprotect_pair(saved['companion_secret']),p)
        self.assertEqual(saved['phone'],'')
    def test_save_failure_keeps_legacy_pair(self):
        p=self.pending();self.beacon(p);self.acknowledge(p)
        with patch.object(self.a,'save',side_effect=OSError('test')),patch.object(app.messagebox,'showerror'):
            self.a.finish_pairing()
        self.assertIsNone(self.a.active_pair);self.assertEqual(self.a.config['phone'],'OLD-ADDRESS')
        self.assertNotIn('companion_secret',self.a.config)
    def test_uuid_receives_even_when_mac_address_changes(self):
        p=companion.new_pairing();self.a.active_pair=p;self.a.scanner_ok=True
        for address in ('RANDOM-A','RANDOM-B'):
            self.a.last_seen=0;self.a.events.put(('ble',(address,'',-60)));self.beacon(p)
            self.assertGreater(self.a.last_seen,0)
    def test_wrong_uuid_and_weak_signal_never_grant_near(self):
        p=companion.new_pairing();self.a.active_pair=p;self.a.scanner_ok=True
        self.beacon(companion.new_pairing());self.assertEqual(self.a.last_seen,0)
        self.beacon(p,-95);self.assertEqual(self.a.last_seen,0)
    def test_hidden_window_keeps_processing_phone_events(self):
        p=companion.new_pairing();self.a.active_pair=p;self.a.scanner_ok=True
        self.a.tray=SimpleNamespace(notify=lambda *_:None,stop=lambda:None)
        self.a.tray_ready=True;self.a.close();self.beacon(p)
        self.assertEqual(self.root.state(),'withdrawn');self.assertGreater(self.a.last_seen,0)
        self.assertFalse(self.a.stop.is_set())
    def test_default_text_is_black(self):
        self.assertEqual(app.ttk.Style().lookup('TLabel','foreground'),'#000000')
    def test_failed_scanner_prevents_pair_completion(self):
        p=self.pending();self.beacon(p);self.acknowledge(p);self.a.scanner_ok=False;self.a.finish_pairing()
        self.assertIsNone(self.a.active_pair)

if __name__=='__main__':unittest.main()
