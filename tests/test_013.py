"""0.13 unit tests: two-step review line, review rules, AI review tools, second human review and the
GitHub device-flow sign-in, all against a mocked GitHub (no network). Run: python3 -m unittest discover -s tests"""
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

DATA = tempfile.mkdtemp(prefix='tracker-test-')


class GH(BaseHTTPRequestHandler):
    """github.com (device flow) and api.github.com in one mock."""
    users = {'tok_miguel_aaaaaaaaaaaaaaaaaaaaaa': 'mistermizel', 'tok_james_aaaaaaaaaaaaaaaaaaaaaaa': 'jdefleur',
             'tok_jan_aaaaaaaaaaaaaaaaaaaaaaaaa': 'JanMesaric', 'gho_agent_aaaaaaaaaaaaaaaaaaaaaaa': 'defleur-agents',
             'gho_good_aaaaaaaaaaaaaaaaaaaaaaaa': 'hacalastudio'}
    token_answers = []   # queue of access_token responses
    device_answer = None
    issues = {}          # number -> {'user', 'labels': set, 'assignees', 'comments': [(login, body)]}
    calls = []

    def log_message(self, *a):
        pass

    def _send(self, code, body=None):
        b = b'' if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _login(self):
        return self.users.get((self.headers.get('Authorization') or '').replace('Bearer ', ''))

    def _body(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        if 'form' in (self.headers.get('Content-Type') or ''):
            return {k: v[0] for k, v in parse_qs(raw.decode()).items()}
        return json.loads(raw or b'{}')

    def _issue(self, n):
        it = self.issues[n]
        return {'number': n, 'state': 'open', 'user': {'login': it['user']}, 'labels': [{'name': l} for l in sorted(it['labels'])],
                'assignees': [{'login': a} for a in it.get('assignees', [])], 'comments': len(it['comments'])}

    def do_GET(self):
        login = self._login()
        GH.calls.append(('GET', self.path, login))
        if not login:
            return self._send(401, {'message': 'Bad credentials'})
        if self.path == '/user':
            return self._send(200, {'login': login, 'name': login})
        if self.path == '/user/memberships/orgs/humanitylabs-org':
            return self._send(200, {'state': 'active', 'user': {'login': login}})
        m = re.match(r'^/repos/humanitylabs-org/wizard-ux/issues/(\d+)$', self.path)
        if m:
            return self._send(200, self._issue(int(m.group(1))))
        m = re.match(r'^/repos/humanitylabs-org/wizard-ux/issues/(\d+)/comments', self.path)
        if m:
            return self._send(200, [{'user': {'login': w}, 'body': b} for w, b in self.issues[int(m.group(1))]['comments']])
        return self._send(200, {})

    def do_POST(self):
        login = self._login()
        body = self._body()
        GH.calls.append(('POST', self.path, login))
        if self.path == '/login/device/code':
            return self._send(200, GH.device_answer or {'device_code': 'dev123', 'user_code': 'ABCD-1234', 'verification_uri': 'https://github.com/login/device',
                                                        'expires_in': 900, 'interval': 5})
        if self.path == '/login/oauth/access_token':
            assert body.get('grant_type') == 'urn:ietf:params:oauth:grant-type:device_code', body
            return self._send(200, GH.token_answers.pop(0) if GH.token_answers else {'error': 'authorization_pending'})
        if self.path == '/graphql':
            return self._send(200, {'data': {'organization': {'viewerIsAMember': True}}})
        m = re.match(r'^/repos/humanitylabs-org/wizard-ux/issues/(\d+)/(labels|comments)$', self.path)
        if m:
            it = self.issues[int(m.group(1))]
            if m.group(2) == 'labels':
                it['labels'] |= set(body['labels'])
                return self._send(200, [])
            it['comments'].append((login, body['body']))
            return self._send(201, {'id': 1})
        return self._send(404, {'message': 'nope'})

    def do_DELETE(self):
        GH.calls.append(('DELETE', self.path, self._login()))
        m = re.match(r'^/repos/humanitylabs-org/wizard-ux/issues/(\d+)/labels/(.+)$', self.path)
        if m:
            self.issues[int(m.group(1))]['labels'].discard(m.group(2))
            return self._send(200, [])
        return self._send(404, {})


SRV = ThreadingHTTPServer(('127.0.0.1', 0), GH)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{SRV.server_address[1]}'
os.environ.update(DATA_DIR=DATA, GITHUB_API=BASE, GITHUB_WEB=BASE)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import server as S  # noqa: E402

E = lambda t, k, l='': (t, k, l)  # noqa: E731


def reset(policy=None, default='tok_miguel_aaaaaaaaaaaaaaaaaaaaaa', login='mistermizel'):
    S._members.clear()
    S._cache.clear()
    S._device.clear()
    (Path(DATA) / 'policy.json').write_text(json.dumps(policy or {}))
    S._write('accounts.json', {'people': {'owner': {'token': default, 'login': login}}, 'default': 'owner'})


class Line(unittest.TestCase):
    def test_two_step_line(self):
        ev = [E(10, 'LabeledEvent', 'building'), E(100, 'LabeledEvent', 'ai-review'),
              E(400, 'LabeledEvent', 'ready-to-test'), E(401, 'UnlabeledEvent', 'ai-review'),
              E(2000, 'UnlabeledEvent', 'ready-to-test'), E(2001, 'LabeledEvent', 'approved'), E(2100, 'ClosedEvent')]
        h = S.history_of(ev, 0, '1970-01-01T00:35:00Z', 'closed', now=5000)
        self.assertEqual(h['build'], 90)            # building -> first hand-off (ai-review)
        self.assertEqual(h['ai_rounds'], [300])
        self.assertEqual(h['review_rounds'], [1700])
        self.assertEqual((h['kicks'], h['ai_kicks']), (0, 0))
        self.assertEqual(h['spent']['ai'], 300)
        self.assertEqual(h['stage'], 'done')

    def test_ai_fail_and_human_fail_are_separate_loops(self):
        ev = [E(10, 'LabeledEvent', 'building'), E(100, 'LabeledEvent', 'ai-review'), E(200, 'UnlabeledEvent', 'ai-review'),
              E(1000, 'LabeledEvent', 'ai-review'), E(1100, 'LabeledEvent', 'ready-to-test'), E(1100, 'UnlabeledEvent', 'ai-review'),
              E(3000, 'UnlabeledEvent', 'ready-to-test')]
        h = S.history_of(ev, 0, None, 'open', now=4000)
        self.assertEqual((h['ai_kicks'], h['kicks'], h['ai_tries'], h['tries']), (1, 1, 2, 1))
        self.assertEqual(h['ai_rounds'], [100, 100])
        self.assertEqual(h['stage'], 'building')     # still labelled building: back with the builder
        ls = S.line_stats([{**h, 'state': 'open'}])
        self.assertEqual(ls['ai_kick']['rate'], 1.0)
        self.assertEqual(ls['kick']['kicked'], 1)
        self.assertEqual(ls['ai']['n'], 2)

    def test_legacy_ready_to_test_is_human_review(self):
        ev = [E(10, 'LabeledEvent', 'building'), E(50, 'LabeledEvent', 'ready-to-test')]
        h = S.history_of(ev, 0, None, 'open', now=100)
        self.assertEqual((h['stage'], h['build'], h['ai_tries'], h['spent']['review']), ('review', 40, 0, 50))

    def test_targets_defaults_and_keys(self):
        reset()
        t = S.policy_base()['targets']
        self.assertEqual((t['bugs']['ai'], t['goals']['ai'], t['bugs']['review'], t['goals']['review']), (1800, 1800, 86400, 86400))
        self.assertEqual(S.TARGET_KEYS['ai-review'], 'ai')
        self.assertEqual(S.policy_base()['human_reviews'], 1)
        reset({'human_reviews': 2})
        self.assertEqual(S.policy_base()['human_reviews'], 2)
        reset({'human_reviews': 7})
        self.assertEqual(S.policy_base()['human_reviews'], 1)


class Rules(unittest.TestCase):
    def setUp(self):
        reset()

    def test_human_rules(self):
        self.assertEqual(S.human_rule('bug', 'oscarhenrycollins', [], 'mistermizel'), (False, 'Someone else reviews this — you opened it.'))
        self.assertTrue(S.human_rule('bug', 'jdefleur', [], 'mistermizel')[0])
        ok, rule = S.human_rule('goal', 'jdefleur', ['JanMesaric'], 'mistermizel')
        self.assertFalse(ok)
        self.assertEqual(rule, 'Only Jan or James review this goal.')
        self.assertTrue(S.human_rule('goal', 'jdefleur', ['JanMesaric'], 'JanMesaric')[0])
        self.assertTrue(S.human_rule('goal', 'jdefleur', [], 'jdefleur')[0])  # James reviews goals

    def test_ai_reviewers(self):
        self.assertEqual(S.ai_reviewers('bug', 'mistermizel', []), ({'miguel'}, 'Oscar'))
        self.assertEqual(S.ai_reviewers('bug', 'jdefleur', []), ({'james'}, 'Archimedes'))
        self.assertEqual(S.ai_reviewers('bug', 'JanMesaric', []), (None, 'any team agent'))
        self.assertEqual(S.ai_reviewers('bug', 'stranger', []), (None, 'any team agent'))
        self.assertEqual(S.ai_reviewers('goal', 'jdefleur', ['mistermizel'])[1], 'Oscar')

    def test_review_progress(self):
        rows = [{'user': {'login': 'jdefleur'}, 'body': 'Tested: works — @jdefleur'},
                {'user': {'login': 'x'}, 'body': "Tested: doesn't work — @x\n\nbroken"},
                {'user': {'login': 'defleur-agents'}, 'body': 'AI review: pass — Archimedes'},
                {'author': {'login': 'JanMesaric'}, 'body': 'Tested: works — @JanMesaric (1 of 2 reviews)'},
                {'author': {'login': 'JanMesaric'}, 'body': 'Tested: works — @JanMesaric'}]
        reset({'human_reviews': 2})
        self.assertEqual(S.review_progress(rows), {'done': 1, 'need': 2, 'by': ['Jan']})


class Reviews(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()

    def test_ai_pass_moves_to_human_review(self):
        reset()  # box account = Miguel, so its agent is Oscar
        GH.issues[5] = {'user': 'mistermizel', 'labels': {'bug', 'ai-review', 'building'}, 'comments': []}
        r = S.rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'ai_review_pass', 'arguments': {'issue': 'humanitylabs-org/wizard-ux#5', 'note': 'Matches the scope.'}}})
        self.assertFalse(r['result']['isError'], r)
        self.assertIn('ready-to-test', GH.issues[5]['labels'])
        self.assertNotIn('ai-review', GH.issues[5]['labels'])
        self.assertTrue(GH.issues[5]['comments'][-1][1].startswith('AI review: pass — Oscar (agent of Miguel)'))

    def test_ai_fail_back_to_building_and_wrong_agent_refused(self):
        reset()
        GH.issues[6] = {'user': 'stranger', 'labels': {'bug', 'ai-review'}, 'comments': []}
        r = S.rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'ai_review_fail', 'arguments': {'repo': 'wizard-ux', 'number': 6, 'note': 'Missing the phone layout.'}}})
        self.assertFalse(r['result']['isError'], r)  # opener outside the roster: any team agent
        self.assertEqual(GH.issues[6]['labels'], {'bug', 'building'})
        GH.issues[7] = {'user': 'jdefleur', 'labels': {'bug', 'ai-review'}, 'comments': []}
        r = S.rpc({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'ai_review_pass', 'arguments': {'repo': 'wizard-ux', 'number': 7, 'note': 'ok fine'}}})
        self.assertTrue(r['result']['isError'])
        self.assertIn('Archimedes', r['result']['content'][0]['text'])
        r = S.rpc({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'ai_review_pass', 'arguments': {'repo': 'wizard-ux', 'number': 7}}})
        self.assertTrue(r['result']['isError'])  # a note is required
        with self.assertRaises(S.Problem) as e:
            S.ai_review_human()
        self.assertEqual(e.exception.reason, 'agents_only')

    def test_two_human_reviews(self):
        reset({'human_reviews': 2})
        S._write('accounts.json', {'people': {'j': {'token': 'tok_james_aaaaaaaaaaaaaaaaaaaaaaa', 'login': 'jdefleur'},
                                              'n': {'token': 'tok_jan_aaaaaaaaaaaaaaaaaaaaaaaaa', 'login': 'JanMesaric'}}, 'default': 'j'})
        GH.issues[8] = {'user': 'mistermizel', 'labels': {'bug', 'ready-to-test'}, 'comments': [('defleur-agents', 'AI review: pass — x')]}
        r = S.tested('j', {'repo': 'wizard-ux', 'number': 8}, True)
        self.assertEqual((r['final'], r['reviews']), (False, {'done': 1, 'need': 2}))
        self.assertIn('ready-to-test', GH.issues[8]['labels'])
        with self.assertRaises(S.Problem) as e:
            S.tested('j', {'repo': 'wizard-ux', 'number': 8}, True)
        self.assertEqual(e.exception.reason, 'already_reviewed')
        r = S.tested('n', {'repo': 'wizard-ux', 'number': 8}, True)
        self.assertTrue(r['final'])
        self.assertEqual(GH.issues[8]['labels'], {'bug', 'approved'})

    def test_human_fail_back_to_building(self):
        reset()
        S._write('accounts.json', {'people': {'j': {'token': 'tok_james_aaaaaaaaaaaaaaaaaaaaaaa', 'login': 'jdefleur'}}, 'default': 'j'})
        GH.issues[9] = {'user': 'mistermizel', 'labels': {'bug', 'ready-to-test'}, 'comments': []}
        S.tested('j', {'repo': 'wizard-ux', 'number': 9, 'note': 'Button missing'}, False)
        self.assertEqual(GH.issues[9]['labels'], {'bug', 'building'})
        GH.issues[10] = {'user': 'mistermizel', 'labels': {'bug', 'ai-review'}, 'comments': []}
        with self.assertRaises(S.Problem) as e:
            S.tested('j', {'repo': 'wizard-ux', 'number': 10}, True)
        self.assertEqual(e.exception.reason, 'ai_review')


class Device(unittest.TestCase):
    def setUp(self):
        reset({'github_client_id': 'Ov23liTESTCLIENT01'})
        S._write('accounts.json', {'people': {}})
        GH.token_answers[:] = []
        GH.device_answer = None

    def start(self, person='p@x'):
        orig = S.device_run
        S.device_run = lambda flow: None  # the background poller does nothing; the test drives the poll by hand
        try:
            out = S.device_start(person)
        finally:
            S.device_run = orig
        return out, S._device[S.person_key(person)]

    def test_start_hides_device_code(self):
        out, flow = self.start()
        self.assertEqual((out['user_code'], out['verification_uri'], out['state']), ('ABCD-1234', 'https://github.com/login/device', 'pending'))
        self.assertNotIn('device_code', json.dumps(out))
        self.assertEqual(flow['device_code'], 'dev123')

    def test_polling_respects_pending_slow_down_then_signs_in(self):
        GH.token_answers[:] = [{'error': 'authorization_pending'}, {'error': 'slow_down', 'interval': 10},
                               {'error': 'authorization_pending'}, {'access_token': 'gho_good_aaaaaaaaaaaaaaaaaaaaaaaa', 'token_type': 'bearer', 'scope': 'repo,read:org'}]
        _, flow = self.start()
        waits = []
        S.device_run(flow, sleep=waits.append)
        self.assertEqual(waits, [5, 5, 10, 10])
        self.assertEqual(flow['state'], 'done')
        self.assertIsNone(flow['device_code'])
        acct = S.accounts()['people']['p@x']
        self.assertEqual((acct['login'], acct['kind'], acct['via']), ('hacalastudio', 'oauth', 'github'))
        st = S.device_status('p@x')
        self.assertTrue(st['status']['connected'])

    def test_expired_denied_and_refused(self):
        _, flow = self.start()
        self.assertIsNone(S.device_poll_once(flow, now=flow['expires_at'] + 1))
        self.assertEqual(flow['state'], 'expired')
        GH.token_answers[:] = [{'error': 'access_denied'}]
        _, flow = self.start()
        S.device_run(flow, sleep=lambda s: None)
        self.assertEqual(flow['state'], 'denied')
        GH.token_answers[:] = [{'error': 'expired_token'}]
        _, flow = self.start()
        S.device_run(flow, sleep=lambda s: None)
        self.assertEqual(flow['state'], 'expired')
        GH.token_answers[:] = [{'access_token': 'gho_agent_aaaaaaaaaaaaaaaaaaaaaaa'}]
        _, flow = self.start()
        S.device_run(flow, sleep=lambda s: None)
        self.assertEqual((flow['state'], flow['reason']), ('refused', 'agent'))
        self.assertNotIn('p@x', S.accounts()['people'])

    def test_cancel_and_no_client_id(self):
        _, flow = self.start()
        S.device_cancel('p@x')
        self.assertEqual(flow['state'], 'cancelled')
        self.assertIsNone(S.device_poll_once(flow))
        reset({})
        os.environ.pop('GITHUB_CLIENT_ID', None)
        with self.assertRaises(S.Problem) as e:
            S.device_start('p@x')
        self.assertEqual(e.exception.reason, 'no_client_id')
        os.environ['GITHUB_CLIENT_ID'] = 'Iv1.envclient123'
        self.assertEqual(S.client_id_info()['source'], 'env')
        os.environ.pop('GITHUB_CLIENT_ID')

    def test_set_client_id(self):
        out = S.set_client_id('p@x', {'client_id': 'Ov23liNEWCLIENT99'})
        self.assertEqual((out['client_id'], out['source']), ('Ov23liNEWCLIENT99', 'policy'))
        for bad in ('gho_xxxxxxxxxxxxxxxxxxxx', 'a' * 40 if False else '0123456789abcdef0123456789abcdef01234567', 'no spaces allowed'):
            with self.assertRaises(S.Problem):
                S.set_client_id('p@x', {'client_id': bad})
        self.assertEqual(S.set_client_id('p@x', {'client_id': ''})['set'], False)


if __name__ == '__main__':
    unittest.main()
