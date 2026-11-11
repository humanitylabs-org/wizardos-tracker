"""Tracker 0.27.0 (Miguel, 11 Nov): busy feedback; the '...' menu (Report something else while testing, Drop this
feature / Not a bug, Open on GitHub); no toggle that can never work (wizard-notes#18); Coming in the next release
(wizard-ux#1256). Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

from test_013 import GH, S, reset
from test_017 import people

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import report as R  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome') if shutil.which(b)), None)
CLOSED = []


class Version(unittest.TestCase):
    def test_version(self):
        self.assertEqual(S.VERSION, '0.27.0')
        self.assertIn('version: 0.27.0', (ROOT / 'wizard.md').read_text())
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], '0.27.0')
        self.assertIn("PAGE_VERSION = '0.27.0'", (ROOT / 'web/app.js').read_text())
        self.assertTrue((ROOT / 'web/dist/html2canvas-pro.min.js').is_file())


class Drop(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        CLOSED.clear()
        reset({'core_repos': ['wizard-os']})
        people()
        p = mock.patch.object(S, '_close', lambda acct, full, number, reason='completed': CLOSED.append((number, reason)))
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(S, '_ensure_label', lambda *a, **k: None)
        q.start()
        self.addCleanup(q.stop)

    def tearDown(self):
        reset()

    def test_feature_merged_behind_switch_dropped_with_cleanup(self):
        GH.issues[80] = {'user': 'mistermizel', 'labels': {'feature', 'ready-to-test'},
                         'comments': [('wizardosbuilder', 'What to check: ...\nSwitch: Settings > Poster wall')]}
        r = S.drop_item('j', {'repo': 'wizard-ux', 'number': 80, 'reason': 'Settings already does this'})
        self.assertTrue(r['cleanup'])
        self.assertEqual(r['label'], 'dropped')
        labels = GH.issues[80]['labels']
        self.assertTrue({'dropped', 'switch-cleanup'} <= labels, labels)
        self.assertNotIn('ready-to-test', labels)
        self.assertEqual(CLOSED, [(80, 'not_planned')])
        body = GH.issues[80]['comments'][-1][1]
        self.assertIn('Dropped (not needed)', body)
        self.assertIn('Why: Settings already does this', body)
        self.assertIn('@', body)   # who

    def test_feature_not_built_yet_has_no_cleanup(self):
        GH.issues[81] = {'user': 'mistermizel', 'labels': {'feature'}, 'comments': []}
        r = S.drop_item('j', {'repo': 'wizard-ux', 'number': 81, 'reason': 'Not needed any more'})
        self.assertFalse(r['cleanup'])
        self.assertNotIn('switch-cleanup', GH.issues[81]['labels'])
        self.assertEqual(CLOSED, [(81, 'not_planned')])

    def test_bug_is_wontfix_not_dropped(self):
        GH.issues[82] = {'user': 'mistermizel', 'labels': {'bug', 'ready-to-test'}, 'comments': []}
        r = S.drop_item('j', {'repo': 'wizard-ux', 'number': 82, 'reason': 'Works as designed'})
        self.assertEqual(r['label'], 'wontfix')
        self.assertIn('wontfix', GH.issues[82]['labels'])
        self.assertNotIn('dropped', GH.issues[82]['labels'])
        self.assertIn('Not a bug / won', GH.issues[82]['comments'][-1][1])

    def test_reason_required(self):
        GH.issues[83] = {'user': 'mistermizel', 'labels': {'feature'}, 'comments': []}
        with self.assertRaises(S.Problem) as e:
            S.drop_item('j', {'repo': 'wizard-ux', 'number': 83, 'reason': ' '})
        self.assertEqual(e.exception.code, 400)
        self.assertEqual(CLOSED, [])

    def test_route_and_tool(self):
        src = (ROOT / 'app/server.py').read_text()
        self.assertIn("'/api/drop': lambda: drop_item(who, body)", src)
        self.assertIn("'board_drop'", src)
        self.assertIn('/api/drop', json.loads((ROOT / 'openapi.json').read_text())['paths'])

    def test_cleanup_ai_pass_closes(self):
        GH.issues[84] = {'user': 'wizardosbuilder', 'labels': {'feature', 'switch-remove', 'ai-review'}, 'comments': []}
        r = S.ai_review({'issue': 'humanitylabs-org/wizard-ux#84', 'note': 'Switch and code removed.'}, True)
        self.assertEqual(r['stage'], 'shipping')
        self.assertEqual([n for n, _ in CLOSED], [84])


class FoundWhileTesting(unittest.TestCase):
    def test_context_line_and_marker(self):
        body = R.triage_body('bug', 'The header overlaps the list.', {'context': {
            'repo': 'humanitylabs-org/wizard-notes', 'number': 18, 'title': 'Open an existing folder', 'app': 'wizard-notes',
            'app_name': 'Notes'}})
        self.assertIn('Found while testing [humanitylabs-org/wizard-notes#18](https://github.com/humanitylabs-org/wizard-notes/issues/18)', body)
        self.assertIn('in Notes', body)
        self.assertIn('<!-- found-while-testing: humanitylabs-org/wizard-notes#18 app: wizard-notes -->', body)
        self.assertTrue(body.startswith('The header overlaps the list.'))

    def test_bad_context_ignored(self):
        for c in ({'repo': 'x', 'number': 1}, {'repo': 'a/b', 'number': 'x'}, {'repo': 'a/b c', 'number': 2}, 'nope', {'repo': 'a/b', 'number': True}):
            self.assertNotIn('Found while testing', R.triage_body('bug', 'Something broke here.', {'context': c}))


class NoSwitch(unittest.TestCase):
    def test_wizard_notes_18(self):
        builder = ('Switch: NOTES_VAULT_DIR (+ NOTES_UID / NOTES_GID) env settings, unset (off) by default. This is an '
                   "install-time setting because a runtime toggle can't mount a host folder, so there is no Tracker Try-it toggle for it.")
        oscar = 'No Try it switch for this one: opening an existing host folder is an install-time setting.'
        self.assertTrue(S.no_switch([builder]))
        self.assertTrue(S.no_switch([builder, oscar]))
        self.assertTrue(S.no_switch(['Done.'], oscar))

    def test_later_linked_switch_wins(self):
        self.assertFalse(S.no_switch(['No Try it switch for this one.', 'Switch: wizard-notes:vault-folder']))
        self.assertFalse(S.no_switch(['Switch: miguel/send-and-go']))
        self.assertFalse(S.no_switch(['Switch: none. Plain text fix.']))   # switch_info already handles 'none'


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'fixture_027.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_no_toggle_for_no_switch_and_bugs(self):
        for k in ('noswitch', 'bugfix'):
            self.assertFalse(self.out[k]['toggle'], (k, self.out[k]))
            self.assertFalse(self.out[k]['popupToggle'], (k, self.out[k]))
        self.assertRegex(self.out['noswitch']['howto'], r'^How to check: ')
        self.assertTrue(self.out['withswitch']['toggle'])

    def test_more_menu_everywhere(self):
        for k in ('noswitch', 'withswitch', 'nextrel'):
            self.assertTrue(self.out[k]['more'], k)
            self.assertTrue(self.out[k]['popupMore'], k)
        self.assertEqual(self.out['menu'], ['Report something else', 'Drop this feature (not needed)', 'Open on GitHub ↗'])
        self.assertEqual(self.out['bugmenu'][1], 'Not a bug / won’t fix')
        # the main row stays Try it / Works / Doesn't work: no 'Report' button in the bar itself
        self.assertNotIn('Report', self.out['barButtons'])

    def test_coming_next_release(self):
        n = self.out['nextrel']
        self.assertEqual(n['group'], 'Coming in the next release')
        self.assertFalse(n['waiting'])
        self.assertEqual(n['buttons'], ['⋯'])
        self.assertIn('Merged. Shows up in the next For testers release.', n['text'])
        self.assertLessEqual(n['text'].count('Not released yet'), 1)
        self.assertFalse(self.out['released']['nextrel'])

    def test_busy_and_still_working(self):
        b = self.out['busy']
        self.assertTrue(b['disabled'] and b['spinner'] and b['ariaBusy'], b)
        self.assertTrue(b['still'], b)
        self.assertTrue(b['restored'], b)

    def test_report_on_top_of_popup(self):
        r = self.out['report']
        self.assertTrue(r['bothOpen'])
        self.assertIn('Found while testing', r['ctx'])
        self.assertTrue(r['snapShown'])
        self.assertEqual(r['sentBody']['context']['number'], 18)
        self.assertTrue(r['popupStillOpen'] and not r['reportOpen'])
        self.assertEqual(r['toast'], 'Sent')


if __name__ == '__main__':
    unittest.main()
