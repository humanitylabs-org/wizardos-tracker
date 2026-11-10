"""Tracker screenshots (0.24.x): screenshots that work. Several per report or Doesn't work note (pick, paste, thumbnails); the text
is always filed even when an upload is refused, and refused screenshots wait on the box and are added later."""
import base64
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import report as R  # noqa: E402
import server as S  # noqa: E402

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32
SHOT = {'type': 'image/png', 'data': base64.b64encode(PNG).decode()}
REFUSED = 'Your GitHub token cannot do that here (Resource not accessible by integration)'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (S.PRIVATE, S._create, S._upload_shot, S._ensure_label, S.account_for, S.gh)
        S.PRIVATE = Path(self.tmp) / 'private'
        self.calls, self.ups, self.refuse, self.posts = [], [], True, []
        S._create = lambda acct, repo, title, body, labels: (self.calls.append(body) or {
            'id': repo + '#9', 'number': 9, 'title': title, 'url': 'https://github.com/x/9'})
        S._ensure_label = lambda *a: None
        S.account_for = lambda person=None, agent=False: ('k', {'token': 'ghu_x', 'login': 'me'})

        def up(acct, raw, ext):
            if self.refuse:
                raise S.Problem(403, REFUSED)
            self.ups.append(raw)
            return f'https://github.com/humanitylabs-org/wizard-issue-media/blob/main/reports/{len(self.ups)}.png?raw=true'
        S._upload_shot = up

    def tearDown(self):
        S.PRIVATE, S._create, S._upload_shot, S._ensure_label, S.account_for, S.gh = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)


class Report(Base):
    def test_many_render_with_fetch_hint(self):
        self.refuse = False
        out = S.report_file('o', {'kind': 'bug', 'text': 'It broke when I tapped send.', 'screenshots': [SHOT, SHOT]})
        body = self.calls[0]
        self.assertIn('![Screenshot 1](https://github.com/humanitylabs-org/wizard-issue-media/blob/main/reports/1.png?raw=true)', body)
        self.assertIn('![Screenshot 2](', body)
        self.assertIn('humanitylabs-org/wizard-issue-media:reports/1.png', body)   # the builder can fetch it
        self.assertEqual(out['waiting'], 0)
        self.assertIsNone(out['warning'])

    def test_refused_keeps_text_and_queues(self):
        out = S.report_file('o', {'kind': 'bug', 'text': 'It broke when I tapped send.', 'screenshots': [SHOT, SHOT]})
        self.assertTrue(self.calls[0].startswith('It broke when I tapped send.'))
        self.assertIn('2 screenshots still uploading', self.calls[0])
        self.assertIn('Your text was sent', out['warning'])
        q = list((S.PRIVATE / S.PENDING_DIR).iterdir())
        self.assertEqual(len(q), 1)
        meta = json.loads((q[0] / 'meta.json').read_text())
        self.assertEqual((meta['repo'], meta['number'], len(meta['files'])), ('humanitylabs-org/wizard-os', 9, 2))

    def test_retry_adds_them_later(self):
        S.report_file('o', {'kind': 'bug', 'text': 'It broke when I tapped send.', 'screenshot': SHOT})
        real = S.accounts
        S.accounts = lambda: {'people': {'k': {'token': 'ghu_x'}}}
        try:
            self.assertEqual(S._retry_pending(), 0)   # still refused: kept
            self.refuse = False

            def gh(token, method, path, body=None, **kw):
                if method == 'GET':
                    return {'repository_url': 'https://api.github.com/repos/humanitylabs-org/wizard-ux', 'number': 77}
                self.posts.append((path, body['body']))
                return {}
            S.gh = gh
            self.assertEqual(S._retry_pending(), 1)
        finally:
            S.accounts = real
        self.assertEqual(self.posts[0][0], '/repos/humanitylabs-org/wizard-ux/issues/77/comments')   # followed the move
        self.assertIn('![Screenshot](', self.posts[0][1])
        self.assertEqual(list((S.PRIVATE / S.PENDING_DIR).iterdir()), [])

    def test_limits(self):
        with self.assertRaises(S.Problem):
            S.report_file('o', {'kind': 'bug', 'text': 'It broke when I tapped send.', 'screenshots': [SHOT] * (R.SHOT_COUNT + 1)})
        self.assertGreater(S.SHOTS_BODY, R.SHOT_COUNT * R.SHOT_MAX)


class UI(unittest.TestCase):
    def test_attacher(self):
        js = (ROOT / 'web' / 'report.js').read_text()
        for must in ('function attacher', 'multiple = true', "'paste', 'drop'", 'rr-thumb-x', 'screenshots:'):
            self.assertIn(must, js)
        app = (ROOT / 'web' / 'app.js').read_text()
        self.assertIn('WizardReporter.attacher', app)
        self.assertIn('if (ok === false)', app)   # a failed send keeps the note
        self.assertIn('return false;', app)


if __name__ == '__main__':
    unittest.main()
