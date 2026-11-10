"""Tracker 0.24.2: Try it is ALWAYS on a Human review item that has a switch (core or app), on the card and in the app
pop-up's bar; when it can't be flipped right now it is greyed with the reason next to it, never hidden (Miguel).
Root cause of 0.24.1's missing toggle: the app-switch read skipped `X-Wizard-Switch: 1`, so Calendar answered 403 and
the card dropped the toggle. The UI test renders real cards in headless Chromium.
Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)


def fn(name):
    m = re.search(r'^(?:async )?function ' + name + r'\(.*?^}', JS, re.S | re.M)
    return m.group(0)


class Version(unittest.TestCase):
    def test_version(self):
        self.assertTrue(S.VERSION >= '0.24.2')
        self.assertIn("PAGE_VERSION = '" + S.VERSION + "'", JS)
        self.assertIn("version: '" + S.VERSION + "'", JS)
        self.assertIn('version: ' + S.VERSION, (ROOT / 'wizard.md').read_text())
        self.assertEqual(json.loads((ROOT / 'runtipi' / 'config.json').read_text())['version'], S.VERSION)


class Source(unittest.TestCase):
    def test_switch_read_sends_the_switch_header(self):
        api = fn('appSwitchApi')
        first = api[api.index('const init'):api.index('\n', api.index('const init'))]
        self.assertIn("'X-Wizard-Switch': '1'", first)   # the GET too, not only the POST

    def test_toggle_never_dropped_for_wait_or_missing_hit(self):
        tt = fn('tryToggle')
        self.assertNotIn('if (t.wait) return null', tt)
        self.assertIn('if (!t.has) return null', tt)
        self.assertIn('greyTry(', tt)

    def test_card_and_popup_use_tryToggle_and_show_why(self):
        self.assertIn('const tg = tryToggle(i);', fn('actionArea'))
        mb = fn('modalBar')
        self.assertIn('tryToggle(it)', mb)
        self.assertIn('bd-try-why', mb)


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class RenderedToggle(unittest.TestCase):
    """Renders the Human review card and the pop-up bar in the real page and asserts a toggle exists in all cases."""

    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'try_toggle_fixture.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_every_item_with_a_switch_has_a_toggle_on_card_and_popup(self):
        for k in ('core', 'app', 'app_catalog', 'needs_update', 'app_unreachable'):
            with self.subTest(k):
                self.assertTrue(self.out[k]['card'], (k, self.out[k]))
                self.assertTrue(self.out[k]['popup'], (k, self.out[k]))

    def test_flippable_ones_are_live(self):
        self.assertFalse(self.out['core']['cardGrey'])
        self.assertEqual(self.out['core']['coreSwitch'], 'miguel/send-and-go')
        self.assertFalse(self.out['app']['cardGrey'])
        self.assertEqual(self.out['app']['appSwitch'], 'wizard-calendar:compact-header')
        self.assertFalse(self.out['app_catalog']['cardGrey'])
        self.assertEqual(self.out['app_catalog']['coreSwitch'], 'messenger:drafts-first')   # adopted from the box catalog

    def test_unflippable_ones_are_grey_with_the_reason(self):
        u = self.out['needs_update']
        self.assertTrue(u['cardGrey'] and u['popupGrey'])
        self.assertEqual(u['popupWhy'], 'Update Movies first')
        self.assertIn('Update Movies first', u['cardWhy'])
        x = self.out['app_unreachable']
        self.assertTrue(x['cardGrey'] and x['popupGrey'])
        self.assertTrue(x['popupWhy'])


if __name__ == '__main__':
    unittest.main()
