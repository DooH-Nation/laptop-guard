import unittest
from guard_core import Guard

class GuardTests(unittest.TestCase):
    def test_far_unplug_locks_and_alarms(self):
        g = Guard(); g.arm(True)
        self.assertEqual(g.tick(1, False, False), ['lock', 'alarm'])
        self.assertEqual(g.tick(2, False, False), [])
    def test_near_gets_grace_but_replug_does_not_cancel(self):
        g = Guard(); g.arm(True)
        self.assertEqual(g.tick(1, False, True, scanner_ok=True), ['lock', 'confirm'])
        self.assertEqual(g.tick(15, True, True, scanner_ok=True), [])
        self.assertEqual(g.tick(16, True, True, scanner_ok=True), ['alarm'])
    def test_unlock_or_password_disarms(self):
        g = Guard(); g.arm(True); g.tick(1, False, False)
        self.assertEqual(g.disarm(2), ['disarmed'])
        self.assertEqual(g.state, 'idle')
    def test_auto_needs_seen_phone_and_twenty_seconds(self):
        g = Guard()
        self.assertEqual(g.tick(1, True, False, True, True), [])
        g.tick(2, True, True, True, True)
        g.tick(3, True, False, True, True)
        self.assertEqual(g.tick(22, True, False, True, True), [])
        self.assertEqual(g.tick(23, True, False, True, True), ['armed'])
    def test_unknown_power_does_not_hide_unplug(self):
        g = Guard(); g.arm(True)
        self.assertEqual(g.tick(1, None, False), [])
        self.assertEqual(g.tick(2, False, False), ['lock', 'alarm'])
    def test_scanner_failure_never_grants_grace_or_auto_arms(self):
        g = Guard(); g.tick(1, True, True, True, True)
        self.assertEqual(g.tick(100, True, False, True, False), [])
        g.arm(True)
        self.assertEqual(g.tick(101, False, True, True, False), ['lock', 'alarm'])
    def test_arm_requires_ac(self):
        for ac in (False, None):
            with self.assertRaises(ValueError): Guard().arm(ac)
    def test_disarm_requires_new_phone_observation(self):
        g = Guard(); g.arm(True); g.disarm(1)
        self.assertEqual(g.tick(100, True, False, True, True), [])

if __name__ == '__main__': unittest.main()
