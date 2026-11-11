"""Tracker 0.30.1 (wizardos-tracker#65): a brief GitHub 5xx after Report or request filed the ticket no longer shows as
"GitHub answered 502." Reads (GET/GraphQL) are retried once on 500/502/503/504, and once the issue is created a failed
read-back falls back to the card from GitHub's answer to the create, so the form says Sent (and nobody files it twice).
Run: python3 -m unittest tests.test_0301 (from the repo root) or python3 -m unittest discover -s tests"""
import io
import json
import unittest
import urllib.error

from test_013 import S, reset

import report as R

CREATED = {'number': 544, 'title': 'It broke when I tapped send.', 'html_url': 'https://github.com/humanitylabs-org/wizard-os/issues/544',
           'state': 'open', 'user': {'login': 'JanMesaric'}, 'labels': [{'name': 'bug'}, {'name': 'triage'}],
           'created_at': '2026-11-11T06:00:00Z', 'updated_at': '2026-11-11T06:00:00Z', 'body': 'x', 'comments': 0}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeGitHub:
    """Answers urlopen like api.github.com: `script` maps (method, path) -> list of status codes, used in order."""

    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, req, timeout=None):
        path = req.full_url.replace(S.GITHUB, '')
        method = req.get_method()
        self.calls.append((method, path))
        codes = self.script.get((method, path)) or [200]
        code = codes.pop(0) if len(codes) > 1 else codes[0]
        if code >= 400:
            raise urllib.error.HTTPError(req.full_url, code, 'err', {}, io.BytesIO(b'{"message": "Server Error"}'))
        if path.endswith('/issues') and method == 'POST':
            return Resp(json.dumps(CREATED).encode())
        if path == '/graphql':
            return Resp(json.dumps({'data': {'repository': {'issue': None}}}).encode())
        return Resp(b'{}')


class Flaky(unittest.TestCase):
    def setUp(self):
        reset()
        self.saved = (S.urllib.request.urlopen, getattr(S, 'GH_RETRY_PAUSE', 0), S._upload_shot, S._ensure_label)
        S.GH_RETRY_PAUSE = 0
        S._ensure_label = lambda *a: None

    def tearDown(self):
        S.urllib.request.urlopen, S.GH_RETRY_PAUSE, S._upload_shot, S._ensure_label = self.saved

    def fake(self, script):
        f = FakeGitHub(script)
        S.urllib.request.urlopen = f
        return f

    def test_read_retried_once_on_5xx(self):
        f = self.fake({('GET', '/repos/o/r/issues/1'): [502, 200]})
        self.assertEqual(S.gh('tok_x' * 5, 'GET', '/repos/o/r/issues/1', cache=False), {})
        self.assertEqual(len(f.calls), 2)

    def test_read_gives_up_after_one_retry(self):
        f = self.fake({('GET', '/repos/o/r/issues/1'): [503]})
        with self.assertRaises(S.Problem) as e:
            S.gh('tok_x' * 5, 'GET', '/repos/o/r/issues/1', cache=False)
        self.assertEqual(e.exception.code, 502)
        self.assertEqual(len(f.calls), 2)

    def test_writes_never_retried(self):
        f = self.fake({('POST', '/repos/o/r/issues'): [502]})
        with self.assertRaises(S.Problem):
            S.gh('tok_x' * 5, 'POST', '/repos/o/r/issues', {'title': 't'})
        self.assertEqual(len(f.calls), 1)   # a retried create could file the issue twice

    def test_report_sent_although_read_back_fails(self):
        where = R.triage_where(S.settings()['org'])['repo']
        f = self.fake({('POST', '/graphql'): [502]})   # every read-back answers 502 (also the one retry)
        out = S.report_file('owner', {'kind': 'bug', 'text': 'It broke when I tapped send. It should send.'})
        self.assertEqual(out['sent'], R.SENT)
        self.assertEqual(out['item']['number'], 544)
        self.assertEqual(out['item']['repo'], where)
        self.assertEqual(out['url'], CREATED['html_url'])
        self.assertIsNone(out['warning'])
        self.assertEqual(sum(1 for c in f.calls if c == ('POST', f'/repos/{where}/issues')), 1)   # filed exactly once


if __name__ == '__main__':
    unittest.main()
