"""Tracker 0.26.5: Pending approval (the Feedback app's inbox through the Feedback relay).
Run: python3 -m unittest discover -s tests"""
import io
import json
import re
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import feedback_inbox as F  # noqa: E402
import server as S  # noqa: E402


class _Resp(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(script):
    """script: list of (status, body); records each request."""
    calls = []

    def go(req, timeout=None):
        calls.append({'url': req.full_url, 'method': req.get_method(), 'auth': req.get_header('Authorization'),
                      'body': json.loads(req.data) if req.data else None})
        status, body = script.pop(0)
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, 'x', {}, io.BytesIO(json.dumps(body).encode()))
        return _Resp(status, body)
    go.calls = calls
    return go


ACCT = {'token': 'ghu_secret', 'login': 'Oscar'}
ITEM = {'number': 2, 'kind': 'bug', 'title': 'Blank screen', 'text': 'It is blank.\nReally.', 'submitter': 'anonymous',
        'created': '2026-11-11T02:35:16Z', 'screenshots': ['https://github.com/humanitylabs-org/wizard-issue-media/blob/main/feedback/2026/x-1.png?raw=true',
                                                          'javascript:alert(1)']}


class Pending(unittest.TestCase):
    def setUp(self):
        F._cache.clear()

    def test_lists_and_cleans(self):
        o = opener([(200, {'items': [ITEM, {'number': 3, 'kind': 'feature', 'title': 'Dark', 'text': 'pls', 'submitter': '@jan<b>', 'created': None}, {'bad': 1}]})])
        out = F.pending(ACCT, opener=o)
        self.assertEqual(out['count'], 2)
        a, b = out['items']
        self.assertEqual((a['kind_word'], a['submitter_word'], a['text']), ('Bug', 'Anonymous', 'It is blank.\nReally.'))
        self.assertEqual(a['screenshots'], [ITEM['screenshots'][0]], 'only https links survive')
        self.assertEqual((b['kind_word'], b['submitter']), ('Idea', 'anonymous'), 'odd submitter text falls back')
        c = o.calls[0]
        self.assertEqual((c['method'], c['auth']), ('GET', 'Bearer ghu_secret'))
        self.assertTrue(c['url'].endswith('/v1/pending'))
        self.assertNotIn('ghu_secret', c['url'], 'the token rides in the header, never the URL')
        self.assertNotIn('ghu_secret', json.dumps(out), 'the token never reaches the page')

    def test_cached_then_refresh(self):
        o = opener([(200, {'items': [ITEM]}), (200, {'items': []})])
        F.pending(ACCT, opener=o)
        self.assertEqual(F.pending(ACCT, opener=o)['count'], 1)
        self.assertEqual(len(o.calls), 1)
        self.assertEqual(F.pending(ACCT, refresh=True, opener=o)['count'], 0)

    def test_errors_map(self):
        for status, code in ((401, 401), (403, 403), (500, 502), (429, 429)):
            F._cache.clear()
            with self.assertRaises(F.RelayError) as e:
                F.pending(ACCT, opener=opener([(status, {'error': 'x', 'message': 'nope'})]))
            self.assertEqual(e.exception.code, code)

    def test_relay_down(self):
        def down(req, timeout=None):
            raise urllib.error.URLError('dns')
        with self.assertRaises(F.RelayError) as e:
            F.pending(ACCT, opener=down)
        self.assertEqual((e.exception.code, e.exception.reason), (502, 'relay_down'))


class Review(unittest.TestCase):
    def test_approve(self):
        F._cache['oscar'] = (9e18, {'items': [ITEM]})
        o = opener([(200, {'ok': True, 'already': False, 'result': 'approved', 'issue': 2,
                           'twin': {'repo': 'wizard-os', 'number': 900, 'url': 'https://github.com/humanitylabs-org/wizard-os/issues/900'}})])
        out = F.review(ACCT, {'number': 2, 'action': 'approve'}, opener=o)
        self.assertEqual(o.calls[0]['body'], {'issue': 2, 'action': 'approve'})
        self.assertEqual(o.calls[0]['method'], 'POST')
        self.assertEqual(o.calls[0]['auth'], 'Bearer ghu_secret')
        self.assertEqual((out['result'], out['twin']['number']), ('approved', 900))
        self.assertIn('builder queue', out['message'])
        self.assertEqual(F._cache, {}, 'every list is stale after a review')

    def test_reject_already(self):
        o = opener([(200, {'ok': True, 'already': True, 'result': 'rejected', 'issue': 5})])
        out = F.review(ACCT, {'number': '5', 'action': 'reject'}, opener=o)
        self.assertEqual((out['result'], out['already'], out['twin']), ('rejected', True, None))
        self.assertIn('already handled', out['message'])

    def test_bad_input_never_calls(self):
        o = opener([])
        for args in ({'number': 2, 'action': 'merge'}, {'number': 0, 'action': 'approve'}, {'number': True, 'action': 'approve'}, {'action': 'reject'}):
            with self.assertRaises(F.RelayError) as e:
                F.review(ACCT, args, opener=o)
            self.assertEqual(e.exception.code, 400)
        self.assertEqual(o.calls, [])

    def test_forbidden(self):
        with self.assertRaises(F.RelayError) as e:
            F.review(ACCT, {'number': 2, 'action': 'approve'}, opener=opener([(403, {'error': 'forbidden', 'message': 'Only WizardOS team members can review feedback'})]))
        self.assertEqual(e.exception.code, 403)


class Hooks(unittest.TestCase):
    def test_card_chip_flag(self):
        node = {'number': 7, 'title': 't', 'url': 'u', 'repository': {'nameWithOwner': 'humanitylabs-org/wizard-os'},
                'labels': {'nodes': [{'name': 'triage'}, {'name': 'From-Feedback'}]}, 'author': {'login': 'x'}, 'body': ''}
        self.assertTrue(S._card(node, 'issues')['from_feedback'])
        node['labels']['nodes'] = [{'name': 'triage'}]
        self.assertFalse(S._card(node, 'issues')['from_feedback'])

    def test_routes_and_relay_url(self):
        src = (ROOT / 'app' / 'server.py').read_text()
        self.assertIn("'/api/feedback/pending'", src)
        self.assertIn("'/api/feedback/review'", src)
        self.assertTrue(F.RELAY_URL.startswith('https://'))

    def test_server_maps_relay_errors(self):
        orig_gate, orig_pending = S.gate, F.pending
        try:
            S.gate = lambda person: ('k', ACCT)

            def boom(acct, refresh=False, opener=None):
                raise F.RelayError(403, 'Only team', 'relay_forbidden')
            F.pending = boom
            with self.assertRaises(S.Problem) as e:
                S.feedback_pending('p')
            self.assertEqual((e.exception.code, e.exception.reason), (403, 'relay_forbidden'))
        finally:
            S.gate, F.pending = orig_gate, orig_pending

    def test_page_wiring(self):
        html = (ROOT / 'web' / 'index.html').read_text()
        self.assertLess(html.index('feedback-stage.js'), html.index('src="app.js"'))
        self.assertIn('feedback-stage.css', html)
        js = (ROOT / 'web' / 'feedback-stage.js').read_text()
        self.assertNotIn('alert(', js)
        self.assertNotIn('confirm(', js.replace('askPop', ''))
        self.assertIn("'From Feedback app'", js)
        self.assertIn("'Pending approval'", js)
        self.assertNotRegex(js, re.compile(r'innerHTML'))

    def test_js_parses(self):
        for f in ('feedback-stage.js', 'app.js'):
            r = subprocess.run(['node', '--check', str(ROOT / 'web' / f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
