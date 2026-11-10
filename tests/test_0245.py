"""Tracker 0.24.5: when an update is what blocks a Human review item, the Update button sits right next to that blocker
text on EVERY card (also cards someone else reviews, and the app pop-up's bar), and turns into the progress panel while
it runs. 'Switch: <app>:<id>' lines count from any comment, not only the builder's.
Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome') if shutil.which(b)), None)


class AppSwitchLine(unittest.TestCase):
    def test_any_comment(self):
        self.assertEqual(S.app_switch_line(['Ready.', 'Switch: wizard-notes:friendly-phone']), 'wizard-notes:friendly-phone')
        self.assertEqual(S.app_switch_line(['Switch: movies:a', 'Switch: Movies:B (off by default)']), 'movies:b')
        self.assertIsNone(S.app_switch_line(['Switch: miguel/send-and-go', 'Switch: none']))


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'blocker_fixture.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_update_beside_blocker_everywhere(self):
        for k in ('onbox_no', 'app_newer', 'other_reviewer'):
            o = self.out[k]
            self.assertTrue(o['blocker'], (k, o))
            self.assertEqual(o['btn'], 'Update', (k, o))
            self.assertRegex(o['text'], r'^Update ', (k, o))
            self.assertTrue(o['popup'], (k, o))
        self.assertTrue(self.out['other_reviewer']['toggle'])

    def test_no_button_when_not_blocked_and_progress_while_running(self):
        self.assertFalse(self.out['not_blocked']['blocker'])
        self.assertTrue(self.out['running']['panel'])
        self.assertFalse(self.out['running']['blocker'])
