"""Tracker 0.33.0 (Miguel, 13 Nov 2026): trying a change is one tap on the Human review card for everything (never 'go
to the app's Settings and flip a toggle'); an item with nothing to switch on says so ('Already on for you — just try
it'); nothing spills out of a chip or bubble; a calm top with secondary controls in a ⋯ menu.
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
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome') if shutil.which(b)), None)
HTML = (ROOT / 'web/index.html').read_text()
CSS = (ROOT / 'web/styles.css').read_text()
JS = (ROOT / 'web/app.js').read_text()


class Version(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 33, 0))
        self.assertIn(f"PAGE_VERSION = '{S.VERSION}'", JS)
        self.assertIn(f"version: '{S.VERSION}'", JS)
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], S.VERSION)
        self.assertIn('version: ' + S.VERSION, (ROOT / 'skill/SKILL.md').read_text())


class Top(unittest.TestCase):
    def test_more_menu_in_header(self):
        bar = HTML[HTML.index('<header class="bd-hbar" id="bar">'):HTML.index('</header>')]
        self.assertIn('id="top-more"', bar)
        self.assertLess(bar.index('id="report-open"'), bar.index('id="top-more"'))
        self.assertRegex(bar, r'id="settings-btn"[^>]*hidden')

    def test_quiet_tools_row(self):
        self.assertIn('.bd-tools #stats-btn[aria-expanded="false"] { display: none; }', CSS)

    def test_no_colour_literals_in_new_css(self):
        new = CSS[CSS.index('0.33 (Miguel, 13 Nov)'):]
        self.assertNotRegex(new, r'#[0-9a-fA-F]{3,8}\b|rgba?\(')


class Overflow(unittest.TestCase):
    def test_strip_labels_stay_in_their_tile(self):
        new = CSS[CSS.index('0.33 (Miguel, 13 Nov)'):]
        self.assertRegex(new, r'\.bd-strip \.bd-binx \{[^}]*overflow: hidden')
        self.assertRegex(new, r'\.bd-strip \.bd-bin-w \{[^}]*-webkit-line-clamp: 2')
        self.assertRegex(new, r'\.bd-card \{ overflow-wrap: anywhere; \}')


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'fixture_033.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_switch_named_in_the_steps_is_a_real_toggle(self):
        c = self.out['calendar']
        self.assertTrue(c['toggle'] and not c['grey'], c)
        self.assertNotIn('Settings', c['text'])
        self.assertTrue(c['steps'].startswith('To test: Switch on Try it, then: in Week'), c['steps'])
        self.assertIn('Drag to move and resize', c['detailSwitch'])
        self.assertNotIn('A setting inside the app', c['detailSwitch'])

    def test_settings_line_is_a_real_toggle(self):
        c = self.out['settings']
        self.assertTrue(c['toggle'] and not c['grey'], c)
        self.assertIn('LINE photo groups', c['detailSwitch'])
        self.assertNotIn('A setting inside the app', c['detailSwitch'])
        self.assertIn('Switch on Try it, then: open a LINE chat', c['steps'])

    def test_switch_in_a_newer_app_build_says_update(self):
        c = self.out['implied']
        self.assertTrue(c['toggle'] and c['grey'], c)
        self.assertIn('Update Notes first', c['text'])
        self.assertIn('Update', c['buttons'])

    def test_core_switch_named_in_words(self):
        c = self.out['corenamed']
        self.assertEqual(c['switch'], 'miguel/send-and-go')
        self.assertTrue(c['toggle'])

    def test_nothing_to_switch_says_so(self):
        self.assertEqual(self.out['live']['live'], '✓Already on for you — just try it')
        self.assertEqual(self.out['noswitch']['live'], '✓No switch needed — just try it')
        self.assertEqual(self.out['said']['live'], '→Nothing to switch on — follow the steps')
        self.assertEqual(self.out['missing']['live'], '→Needs Recorder installed first')
        for k in ('live', 'noswitch', 'said', 'missing'):
            self.assertFalse(self.out[k]['toggle'], k)

    def test_top(self):
        self.assertTrue(self.out['builderRunningHidden'])
        self.assertTrue(self.out['builderPausedShown'])
        self.assertEqual(self.out['topMenu'], ['Builder', 'Show stats', 'Refresh now', 'Settings'])


if __name__ == '__main__':
    unittest.main()
