"""Tracker 0.28.1 (Miguel, 11 Nov): Pending approval — approve as the other kind, decline with a reason the sender sees.
Run: python3 -m unittest discover -s tests"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tests'))
import feedback_inbox as F  # noqa: E402
import server as S  # noqa: E402
from test_0265 import ACCT, opener  # noqa: E402

JS = (ROOT / 'web' / 'feedback-stage.js').read_text()
APP = (ROOT / 'web' / 'app.js').read_text()


class Version(unittest.TestCase):
    def test_bumped_everywhere(self):
        v = S.VERSION
        self.assertGreaterEqual(tuple(map(int, v.split('.'))), (0, 28, 1))
        self.assertIn(f'version: {v}', (ROOT / 'wizard.md').read_text())
        self.assertIn(f'version: {v}', (ROOT / 'skill/SKILL.md').read_text())
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], v)
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], v)
        self.assertIn(f"const PAGE_VERSION = '{v}'", APP)
        self.assertIn('**0.28.1**', (ROOT / 'wizard.md').read_text())


class ApproveAsKind(unittest.TestCase):
    def test_kind_is_forwarded_and_message_says_it(self):
        o = opener([(200, {'ok': True, 'already': False, 'result': 'approved', 'issue': 2, 'kind': 'feature', 'changed_from': 'bug',
                           'twin': {'repo': 'wizard-os', 'number': 901, 'url': 'https://github.com/humanitylabs-org/wizard-os/issues/901'}})])
        out = F.review(ACCT, {'number': 2, 'action': 'approve', 'kind': 'feature', 'reason': 'ignored on approve'}, opener=o)
        self.assertEqual(o.calls[0]['body'], {'issue': 2, 'action': 'approve', 'kind': 'feature'})
        self.assertEqual((out['kind'], out['changed_from']), ('feature', 'bug'))
        self.assertIn('as an idea', out['message'])
        self.assertIn('Changed from bug', out['message'])

    def test_same_kind_and_no_kind(self):
        o = opener([(200, {'ok': True, 'result': 'approved', 'kind': 'bug'}), (200, {'ok': True, 'result': 'approved'})])
        out = F.review(ACCT, {'number': 3, 'action': 'approve', 'kind': 'bug'}, opener=o)
        self.assertNotIn('Changed', out['message'])
        self.assertIn('as a bug', out['message'])
        F.review(ACCT, {'number': 3, 'action': 'approve', 'kind': ''}, opener=o)
        self.assertEqual(o.calls[1]['body'], {'issue': 3, 'action': 'approve'}, 'no kind: the relay keeps what was sent')

    def test_bad_kind_never_calls(self):
        o = opener([])
        for k in ('idea', 'Bug', 5):
            with self.assertRaises(F.RelayError) as e:
                F.review(ACCT, {'number': 2, 'action': 'approve', 'kind': k}, opener=o)
            self.assertEqual(e.exception.code, 400)
        self.assertEqual(o.calls, [])


class DeclineWithReason(unittest.TestCase):
    def test_reason_cleaned_and_forwarded(self):
        o = opener([(200, {'ok': True, 'already': False, 'result': 'rejected', 'issue': 4, 'reason': 'x'})])
        out = F.review(ACCT, {'number': 4, 'action': 'reject', 'reason': '  Works already\u0007 in 0.3.170.\r\nUpdate first.  ', 'kind': 'feature'}, opener=o)
        self.assertEqual(o.calls[0]['body'], {'issue': 4, 'action': 'reject', 'reason': 'Works already in 0.3.170.\nUpdate first.'})
        self.assertEqual(out['result'], 'rejected')
        self.assertIn('sees your reason', out['message'])

    def test_no_reason_is_plain_decline(self):
        o = opener([(200, {'ok': True, 'result': 'rejected'})])
        out = F.review(ACCT, {'number': 4, 'action': 'reject', 'reason': '   '}, opener=o)
        self.assertEqual(o.calls[0]['body'], {'issue': 4, 'action': 'reject'})
        self.assertEqual(out['message'], 'Declined.')

    def test_too_long_or_not_text(self):
        o = opener([])
        for r in ('y' * 501, ['a'], 7):
            with self.assertRaises(F.RelayError) as e:
                F.review(ACCT, {'number': 4, 'action': 'reject', 'reason': r}, opener=o)
            self.assertEqual(e.exception.code, 400)
        self.assertEqual(o.calls, [])
        self.assertEqual(len(F.clean_reason('z' * 500)), 500)


class Page(unittest.TestCase):
    def test_three_actions(self):
        self.assertIn("'Approve as ' + WORD[sent]", JS)
        self.assertIn('`Approve as ${WORD[other]} instead`', JS)
        self.assertIn("smallBtn('Decline'", JS)
        self.assertNotIn("smallBtn('Reject'", JS)
        self.assertIn("{ kind: sent }", JS)
        self.assertIn("{ kind: other }", JS)
        self.assertIn("'Reason (the sender sees this)'", JS)
        self.assertIn('ta.maxLength = REASON_MAX', JS)
        self.assertIn('const REASON_MAX = 500', JS)
        self.assertNotRegex(JS, re.compile(r'innerHTML'))

    def test_tap_before_io(self):
        act = JS[JS.index('async function act('):]
        self.assertLess(act.index("c.classList.add('busy')"), act.index("await api('api/feedback/review'"))
        self.assertLess(act.index("status.textContent ="), act.index("await api("))
        self.assertIn("c.classList.add('leaving')", act)
        self.assertIn('toast(', act)

    def test_reason_box_survives_keyboard(self):
        self.assertIn("/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)", APP)

    def test_primary_secondary_quiet(self):
        css = (ROOT / 'web' / 'feedback-stage.css').read_text()
        self.assertIn('.bd-fbact .bd-fbyes:not(:disabled) { background: var(--accent)', css)
        self.assertIn('.bd-fbact .bd-fbno:not(:disabled) { border-color: var(--line-2)', css)
        self.assertNotIn('bd-fbswap:not(:disabled) { background', css)

    def test_js_parses(self):
        for f in ('feedback-stage.js', 'app.js'):
            r = subprocess.run(['node', '--check', str(ROOT / 'web' / f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_openapi_documents_kind_and_reason(self):
        props = json.loads((ROOT / 'openapi.json').read_text())['paths']['/api/feedback/review']['post']['requestBody']['content']['application/json']['schema']['properties']
        self.assertEqual(props['kind']['enum'], ['bug', 'feature'])
        self.assertEqual(props['reason']['maxLength'], 500)


if __name__ == '__main__':
    unittest.main()
