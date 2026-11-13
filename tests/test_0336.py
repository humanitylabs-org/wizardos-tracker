"""0.33.6 (wizard-notes#33): a change not on the box is never offered as a live Try it."""
import pathlib, sys, unittest
from unittest import mock
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import server  # noqa: E402


class NotOnBoxWins(unittest.TestCase):
    def test_page_blocks_even_when_switch_found(self):
        js = (ROOT / 'web' / 'app.js').read_text()
        self.assertNotIn("ob.state === 'no' && !hit) wait", js)
        self.assertIn("else if (ob && ob.state === 'no') wait =", js)

    def test_same_store_version_is_not_released(self):
        app = {'id': 'wizard-notes', 'name': 'Wizard Notes', 'version': '0.1.0-alpha.8', 'commit': 'a' * 40}
        box = {'release': None, 'channel': 'latest', 'apps': {'wizard-notes': '0.1.0-alpha.8'}, 'mac': None}
        with mock.patch.object(server, 'store_listing', return_value=app), \
             mock.patch.object(server, 'version_commit', return_value='b' * 40), \
             mock.patch.object(server, 'in_build', side_effect=lambda t, r, sha, ref: ref == 'a' * 40):
            v = server.verdict('t', [{'repo': 'humanitylabs-org/wizard-notes', 'number': 41, 'sha': 'c' * 40}], 0, box)
        self.assertEqual(v['state'], 'no')
        self.assertEqual(v['fix'], 'Not released yet')

    def test_newer_store_version_offers_update(self):
        app = {'id': 'wizard-notes', 'name': 'Wizard Notes', 'version': '0.1.0-alpha.9', 'commit': 'a' * 40}
        box = {'release': None, 'channel': 'latest', 'apps': {'wizard-notes': '0.1.0-alpha.8'}, 'mac': None}
        with mock.patch.object(server, 'store_listing', return_value=app), \
             mock.patch.object(server, 'version_commit', return_value='b' * 40), \
             mock.patch.object(server, 'in_build', side_effect=lambda t, r, sha, ref: ref == 'a' * 40):
            v = server.verdict('t', [{'repo': 'humanitylabs-org/wizard-notes', 'number': 41, 'sha': 'c' * 40}], 0, box)
        self.assertEqual(v['fix'], 'Update Wizard Notes')


if __name__ == '__main__':
    unittest.main()
