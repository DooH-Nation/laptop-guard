"""Siren playback with temporary, enforced Windows audio settings."""
import array
import math
from pathlib import Path
import wave
import winsound
from windows_audio import WindowsAudio

def write_siren(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    sample_rate=22050;duration=1.4
    samples=array.array('h')
    for i in range(int(sample_rate*duration)):
        t=i/sample_rate;segment=t%0.175
        frequency=1100 if int(t/0.175)%2==0 else 1700
        envelope=min(1.0,segment/0.005,(0.175-segment)/0.005)
        samples.append(int(0.72*32767*envelope*math.sin(2*math.pi*frequency*t)))
    temporary=path.with_suffix('.tmp.wav')
    with wave.open(str(temporary),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(sample_rate);output.writeframes(samples.tobytes())
    temporary.replace(path)
    return path

class AlarmPlayer:
    def __init__(self,path,report,audio_factory=WindowsAudio,play_sound=winsound.PlaySound):
        self.path=Path(path);self.report=report;self.audio_factory=audio_factory;self.play_sound=play_sound
        self.audio=None;self.playing=False;self.last_error=None
    def enforce(self):
        try:
            if self.audio is None:self.audio=self.audio_factory()
            self.audio.ensure_loud(0.8)
            self.last_error=None
            return True
        except Exception as error:
            message='경보 음소거 해제 / 음량 조절 실패: '+str(error)
            if message!=self.last_error:self.report(message);self.last_error=message
            return False
    def start(self):
        write_siren(self.path)
        ready=self.enforce()
        self.play_sound(str(self.path),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_LOOP|winsound.SND_NODEFAULT)
        self.playing=True
        self.report('경보음 반복 재생 시작 · 음소거 해제 및 최소 음량 80% 유지' if ready else '경보음 재생 요청 · 음소거 해제는 재시도 중입니다.')
    def close(self):
        try:
            if self.playing:self.play_sound(None,0)
        except Exception as error:
            self.report('경보음 중지 오류: '+str(error))
        finally:
            self.playing=False
            if self.audio is not None:
                audio,self.audio=self.audio,None
                try:
                    audio.close();self.report('경보 종료 · 이전 음량과 음소거 상태 복원 완료')
                except Exception as error:self.report('이전 음량 복원 실패: '+str(error))
