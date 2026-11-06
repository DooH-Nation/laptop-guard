"""Pure, clock-injected protection state machine."""
from dataclasses import dataclass

@dataclass
class Guard:
    state: str = 'idle'
    grace: float = 15
    deadline: float = 0
    cooldown: float = 0
    previous_ac: object = None
    seen_phone: bool = False
    away_since: object = None

    def arm(self, ac):
        if ac is not True:
            raise ValueError('충전기를 연결하고 전원 상태가 확인된 뒤 켜 주세요.')
        self.state = 'armed'
        self.previous_ac = True
        return ['armed']

    def disarm(self, now):
        self.state = 'idle'
        self.cooldown = now + 60
        self.seen_phone = False
        self.away_since = None
        return ['disarmed']

    def tick(self, now, ac, near, auto=False, scanner_ok=False):
        events = []
        if near and scanner_ok:
            self.seen_phone = True
            self.away_since = None
        if self.state == 'idle' and auto and scanner_ok and self.seen_phone and now >= self.cooldown:
            if not near:
                if self.away_since is None:
                    self.away_since = now
                if now - self.away_since >= 20 and ac is True:
                    events += self.arm(ac)
        if self.state == 'armed' and self.previous_ac is True and ac is False:
            self.state = 'confirm' if near and scanner_ok else 'alarm'
            self.deadline = now + self.grace
            events += ['lock', 'confirm' if self.state == 'confirm' else 'alarm']
        if self.state == 'confirm' and now >= self.deadline:
            self.state = 'alarm'
            events += ['alarm']
        if ac is not None:
            self.previous_ac = ac
        return events
