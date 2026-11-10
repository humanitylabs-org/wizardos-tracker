"""0.21 unit tests: Report or request in two steps (lands in wizard-os with label triage, shows as Sorting…), app
switches (wizard.app-switches/1) on Human review cards, and Open <app> in a sheet over the Tracker.
Run: python3 -m unittest discover -s tests"""
import base64
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import S, reset

import report as R

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
RJS = (ROOT / 'web/report.js').read_text()
HTML = (ROOT / 'web/index.html').read_text()
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 32


class Report(unittest.TestCase):
    def setUp(self):
        reset()
        self.saved = (S._create, S._upload_shot, S._ensure_label)
        self.calls, self.shots, self.labels = [], [], []
        S._create = lambda acct, full, title, body, label: (self.calls.append((full, title, body, label)) or
                                                            {'id': 'I1', 'number': 9, 'title': title, 'url': f'https://g/{full}/9', 'labels': list(label), 'labelled': False})
        S._upload_shot = lambda acct, raw, ext: (self.shots.append((raw, ext)) or 'https://github.com/m/blob/main/x.png?raw=true')
        S._ensure_label = lambda acct, full, name, color, desc: self.labels.append((full, name))

    def tearDown(self):
        S._create, S._upload_shot, S._ensure_label = self.saved

    def test_files_in_wizard_os_with_triage(self):
        r = S.report_file('owner', {'kind': 'bug', 'text': 'TEST: Messenger jumps to the top when I react. It should stay put.',
                                    'wizard_version': '0.3.150 (For testers)', 'device': 'Mac · Chrome', 'about': 'app:messenger'})
        full, title, body, labels = self.calls[0]
        self.assertEqual(full, 'humanitylabs-org/wizard-os')
        self.assertEqual(labels, ['bug', 'triage'])
        self.assertEqual(self.labels, [('humanitylabs-org/wizard-os', 'triage')])
        self.assertEqual(title, 'TEST: Messenger jumps to the top when I react')
        self.assertIn('WizardOS 0.3.150 (For testers) · Mac · Chrome', body)
        self.assertIn('label triage', body)
        self.assertEqual(r['sent'], 'Sent. The builder files it in the right place in a minute or two.')
        self.assertEqual(r['view'], 'bugs')
        r = S.report_file('owner', {'kind': 'feature', 'text': 'Pin chats to the top so the ones I use stay handy.'})
        self.assertEqual(self.calls[1][3], ['feature', 'triage'])
        self.assertEqual(r['view'], 'core')

    def test_screenshot(self):
        S.report_file('owner', {'kind': 'bug', 'text': 'It broke when I tapped send.', 'screenshot': {'type': 'image/png', 'data': base64.b64encode(PNG).decode()}})
        self.assertEqual(self.shots, [(PNG, 'png')])
        self.assertIn('![Screenshot](https://github.com/m/blob/main/x.png?raw=true)', self.calls[0][2])
        for bad in ({'type': 'image/svg+xml', 'data': 'eA=='}, {'type': 'image/png', 'data': base64.b64encode(b'not a png').decode()},
                    {'type': 'image/png', 'data': '%%%'}):
            with self.assertRaises(S.Problem) as e:
                S.report_file('owner', {'kind': 'bug', 'text': 'It broke when I tapped send.', 'screenshot': bad})
            self.assertEqual(e.exception.code, 400)
        self.assertEqual(len(self.calls), 1)

    def test_bad_input(self):
        with self.assertRaises(S.Problem):
            S.report_file('owner', {'kind': 'bug', 'text': 'no'})
        with self.assertRaises(S.Problem):
            S.report_file('owner', {'kind': 'x', 'text': 'long enough words here'})
        self.assertEqual(self.calls, [])

    def test_sorting_group(self):
        self.assertEqual(S.item_group('humanitylabs-org/wizard-os', ['bug', 'triage']), 'sorting')
        self.assertEqual(S.item_group('humanitylabs-org/wizard-os', ['feature', 'triage']), 'sorting')
        self.assertEqual(S.item_group('humanitylabs-org/wizard-os', ['feature']), 'james')
        self.assertIn('sorting', S.OPEN_GROUPS)
        self.assertEqual(S.category('humanitylabs-org/wizard-os', ['feature', 'triage']), 'core')   # Core features tab


class Refiled(unittest.TestCase):
    def test_builder_copy_counts_as_the_filer(self):
        d = {'data': {'search': {'nodes': [
            {'number': 1, 'author': {'login': 'wizardosbuilder'}, 'body': 'Text\n\nFiled by @mistermizel with Report or request (moved from humanitylabs-org/wizard-os#504)'},
            {'number': 2, 'author': {'login': 'wizardosbuilder'}, 'body': 'Filed by @mistermizel says a person'},
            {'number': 3, 'author': {'login': 'jdefleur'}, 'body': 'Filed by @mistermizel with Report or request'}]}}}
        n = S.refiled(d)['data']['search']['nodes']
        self.assertEqual([x['author']['login'] for x in n], ['mistermizel', 'wizardosbuilder', 'jdefleur'])


class Form(unittest.TestCase):
    def test_two_steps(self):
        self.assertNotIn('What’s it about?', HTML)
        self.assertNotIn('rr-core', HTML + RJS)
        self.assertNotIn('Not sure', RJS)
        self.assertIn('id="rr-shot"', HTML)
        self.assertIn('Sent. The builder files it in the right place in a minute or two.', RJS)
        self.assertNotIn('confirm(', RJS)

    def test_sorting_on_cards(self):
        self.assertIn("['sorting', 'Sorting…']", JS)
        self.assertIn("if (g === 'sorting') return ['Sorting…", JS)

    def test_app_switch_contract(self):
        self.assertIn("['/api/switches', '/api/view/switches']", JS)
        self.assertIn("'X-Wizard-Switch': '1'", JS)
        self.assertIn("APP_SWITCHES = 'wizard.app-switches/1'", JS)
        self.assertTrue((ROOT / 'docs/app-switches.md').exists())
        i = {'id': 'humanitylabs-org/wizard-messenger#133', 'switch_how': 'Settings › Drafts at top'}
        # the place the Tracker reads for #133
        pl = S.switch_place('Settings › Drafts at top', [], 'humanitylabs-org/wizard-messenger')
        self.assertEqual(pl['kind'], 'app')

    def test_app_modal(self):
        self.assertIn('id="appmodal"', HTML)
        self.assertIn('<iframe id="appmodal-f"', HTML)
        self.assertIn('frame-ancestors', JS)
        self.assertIn("window.open(path, '_blank', 'noopener')", JS)
        self.assertIn("'appmodal'].some", JS)   # counts as an open sheet: no refresh behind it

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_js_parses(self):
        for f in ('web/app.js', 'web/report.js'):
            subprocess.run(['node', '--check', str(ROOT / f)], check=True)

    def test_version(self):
        self.assertTrue(S.VERSION >= '0.22.0')
        self.assertIn("const PAGE_VERSION = '" + S.VERSION + "'", JS)


if __name__ == '__main__':
    unittest.main()
