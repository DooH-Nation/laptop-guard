import unittest
from phone_names import PhoneNames
class PhoneNamesTests(unittest.TestCase):
    def test_names_replace_addresses(self):
        n=PhoneNames(); n.remember('AA:BB','Galaxy S25')
        self.assertEqual(n.choices(['AA:BB']),{'AA:BB':'Galaxy S25'})
    def test_unknowns_are_distinct(self):
        n=PhoneNames(); labels=n.choices(['a','b'])
        self.assertEqual(len(set(labels.values())),2)
        self.assertTrue(all(s.startswith('이름 없는 기기') for s in labels.values()))
    def test_duplicate_names_keep_identity(self):
        n=PhoneNames(); n.remember('a','Galaxy'); n.remember('b','Galaxy')
        self.assertEqual(len(set(n.choices(['a','b']).values())),2)
    def test_last_known_name_survives_nameless_packet(self):
        n=PhoneNames(); n.remember('a','Galaxy'); n.remember('a','')
        self.assertEqual(n.choices(['a'])['a'],'Galaxy')
    def test_alias_persists_while_offline(self):
        n=PhoneNames({'a':'내 갤럭시'})
        self.assertEqual(n.choices([], 'a'),{'a':'내 갤럭시'})
    def test_alias_matching_another_label_cannot_overwrite(self):
        n=PhoneNames({'a':'Galaxy · 기기 2'})
        n.remember('a',''); n.remember('b','Galaxy'); n.remember('c','Galaxy')
        self.assertEqual(len(set(n.choices(['a','b','c']).values())),3)
if __name__=='__main__': unittest.main()
