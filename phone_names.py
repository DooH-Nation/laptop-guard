"""Display names are separate from BLE addresses used for matching."""
class PhoneNames:
    def __init__(self, aliases=None):
        self.aliases = dict(aliases or {})
        self.names = {}
        self.numbers = {}

    def remember(self, address, name):
        if address not in self.numbers:
            self.numbers[address] = len(self.numbers) + 1
        if name and name.strip() and name != '이름 없음':
            self.names[address] = name.strip().replace('\n', ' ')[:60]

    def choices(self, addresses, selected=''):
        addresses = list(dict.fromkeys([*addresses, *([selected] if selected else [])]))
        for address in addresses:
            self.remember(address, '')
        bases = {a: self.aliases.get(a) or self.names.get(a) or f'이름 없는 기기 {self.numbers[a]}' for a in addresses}
        labels = {}
        used = set()
        for a in addresses:
            base = bases[a]
            label = base
            if list(bases.values()).count(base) > 1:
                label = f'{base} · 기기 {self.numbers[a]}'
            while label in used:
                label += ' ·'
            labels[a] = label
            used.add(label)
        return labels
