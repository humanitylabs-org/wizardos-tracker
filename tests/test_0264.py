"""0.26.4 (Miguel, 11 Nov): an approved app feature ships always on. Works on an app feature with a switch adds
approved + switch-default and keeps it open for the builder; the AI review pass after the builder removed the switch
closes it. Run: python3 -m unittest discover -s tests"""
import unittest
from unittest import mock

from test_013 import GH, S, reset
from test_017 import people

APP = {'core_repos': ['wizard-os']}   # treat wizard-ux as an app repo for the mock GitHub


CLOSED = []


def closes(n):
    return [c for c in CLOSED if c == n]


class ApprovedAppFeatureShipsOn(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        CLOSED.clear()
        reset(APP)
        people()
        p = mock.patch.object(S, '_close', lambda acct, full, number, reason='completed': CLOSED.append(number))
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        reset()

    def test_works_with_switch_keeps_it_open_for_the_builder(self):
        GH.issues[70] = {'user': 'mistermizel', 'labels': {'feature', 'ready-to-test'},
                         'comments': [('wizardosbuilder', 'What to check: …\nSwitch: Settings > Drafts at top')]}
        r = S.tested('m', {'repo': 'wizard-ux', 'number': 70}, True)
        self.assertTrue(r['switch_default'])
        self.assertTrue({'approved', 'switch-default'} <= GH.issues[70]['labels'])
        self.assertNotIn('ready-to-test', GH.issues[70]['labels'])
        self.assertIn('Builder: remove the switch', GH.issues[70]['comments'][-1][1])
        self.assertEqual(closes(70), [])

    def test_works_without_switch_closes(self):
        GH.issues[71] = {'user': 'mistermizel', 'labels': {'feature', 'ready-to-test'}, 'comments': []}
        r = S.tested('m', {'repo': 'wizard-ux', 'number': 71}, True)
        self.assertFalse(r['switch_default'])
        self.assertNotIn('switch-default', GH.issues[71]['labels'])
        self.assertEqual(len(closes(71)), 1)

    def test_ai_pass_after_switch_removed_closes(self):
        GH.issues[72] = {'user': 'mistermizel', 'labels': {'feature', 'approved', 'switch-default', 'ai-review'}, 'comments': []}
        r = S.ai_review({'issue': 'humanitylabs-org/wizard-ux#72', 'note': 'Switch removed, always on.'}, True)
        self.assertEqual(r['stage'], 'shipping')
        self.assertFalse({'ai-review', 'switch-default', 'ready-to-test'} & GH.issues[72]['labels'])
        self.assertEqual(len(closes(72)), 1)

    def test_core_feature_still_goes_to_show_and_tell(self):
        reset()
        people()
        GH.issues[73] = {'user': 'mistermizel', 'labels': {'feature', 'james-approved', 'ready-to-test'},
                         'comments': [('wizardosbuilder', 'Switch: wizard/x')]}
        S.tested('m', {'repo': 'wizard-ux', 'number': 73}, True)
        self.assertIn('show-and-tell', GH.issues[73]['labels'])
        self.assertNotIn('switch-default', GH.issues[73]['labels'])


if __name__ == '__main__':
    unittest.main()
