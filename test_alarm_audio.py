import tempfile,unittest,wave
from pathlib import Path
from alarm_audio import AlarmPlayer,write_siren
class FakeAudio:
    def __init__(self):self.muted=True;self.volume=0;self.closed=False
    def ensure_loud(self,minimum):self.muted=False;self.volume=max(self.volume,minimum)
    def close(self):self.muted=True;self.volume=0;self.closed=True
class AudioTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'siren.wav';self.audio=FakeAudio();self.calls=[];self.logs=[]
    def tearDown(self):self.tmp.cleanup()
    def player(self,play=None,factory=None):return AlarmPlayer(self.path,self.logs.append,audio_factory=factory or (lambda:self.audio),play_sound=play or (lambda *args:self.calls.append(args)))
    def test_siren_is_valid_non_silent_pcm(self):
        write_siren(self.path)
        with wave.open(str(self.path),'rb') as w:
            self.assertEqual(w.getnchannels(),1);self.assertEqual(w.getsampwidth(),2)
            self.assertGreater(w.getnframes(),22050);self.assertNotEqual(set(w.readframes(w.getnframes())),{0})
    def test_alarm_unmutes_and_restores(self):
        p=self.player();p.start();self.assertFalse(self.audio.muted);self.assertGreaterEqual(self.audio.volume,0.8)
        p.close();self.assertTrue(self.audio.muted);self.assertEqual(self.audio.volume,0);self.assertEqual(self.calls[-1],(None,0))
    def test_muting_during_alarm_is_overridden(self):
        p=self.player();p.start();self.audio.muted=True;self.audio.volume=0;p.enforce()
        self.assertFalse(self.audio.muted);self.assertGreaterEqual(self.audio.volume,0.8);p.close()
    def test_volume_above_minimum_is_not_lowered(self):
        self.audio.volume=0.95;p=self.player();p.start();self.assertEqual(self.audio.volume,0.95);p.close()
    def test_playback_failure_still_restores_audio(self):
        def fail(*_):raise RuntimeError('test')
        p=self.player(play=fail)
        with self.assertRaises(RuntimeError):p.start()
        p.close();self.assertTrue(self.audio.closed);self.assertTrue(self.audio.muted)
    def test_audio_control_failure_retries_without_false_success(self):
        state=[0]
        def factory():
            state[0]+=1
            if state[0]==1:raise OSError('temporarily unavailable')
            return self.audio
        p=self.player(factory=factory);p.start()
        self.assertTrue(any('재시도' in m for m in self.logs));self.assertTrue(p.enforce());p.close();self.assertTrue(self.audio.closed)
    def test_stop_playback_failure_does_not_skip_restoration(self):
        def play(path,flags):
            if path is None:raise RuntimeError('test stop failure')
        p=self.player(play=play);p.start();p.close();self.assertTrue(self.audio.closed)
if __name__=='__main__':unittest.main()
