"""Tracker 0.34.0 (Miguel, 15 Nov, humanitylabs-org/wizardos-tracker#87): Needs you badge. GET /api/needs-you counts
only what actually waits on the viewer, behind the app switch needs-you-badge; the server alerts new items once.
Run: python3 -m unittest discover -s tests"""
import json
import os
import unittest
from pathlib import Path

from test_013 import S, reset, DATA
from test_017 import people
from test_0182 import node

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
B = 'wizardosbuilder'
ASK_MIGUEL = {'totalCount': 1, 'nodes': [{'author': {'login': B}, 'createdAt': '2026-11-10T01:00:00Z',
                                         'body': '@mistermizel should the restore test keep the old copy?'}]}
ASK_JAN = {'totalCount': 1, 'nodes': [{'author': {'login': B}, 'createdAt': '2026-11-10T01:00:00Z',
                                      'body': '@JanMesaric which name should the switch get?'}]}

CORE = [
    node(1, ['feature'], author='mistermizel', title='Miguel idea'),                     # waits for approval, Miguel filed
    node(2, ['feature'], author='oscarhenrycollins', title='Oscar idea'),                # filed by Miguel's agent
    node(3, ['feature'], author='jdefleur', title='James idea'),                         # James filed: not Miguel's badge
    node(4, ['feature', 'james-approved', 'ready-to-test'], author='mistermizel', title='Miguel to try'),
    node(5, ['feature', 'james-approved', 'ready-to-test'], author='JanMesaric', title='Jan to try'),
    node(6, ['feature', 'james-approved', 'show-and-tell'], author='mistermizel', title='Show James'),
    node(7, ['feature', 'james-approved', 'builder:blocked'], author='JanMesaric', comments=ASK_MIGUEL, title='Q for Miguel'),
    node(8, ['feature', 'james-approved', 'builder:blocked'], author='mistermizel', comments=ASK_JAN, title='Q for Jan'),
    node(9, ['feature', 'james-approved', 'building'], author='mistermizel', title='Just building'),
]
BUGS = [
    node(20, ['bug', 'ready-to-test'], author='mistermizel', repo='humanitylabs-org/wizard-notes', title='Shipped bug'),
    node(21, ['bug', 'ai-review'], author='mistermizel', repo='humanitylabs-org/wizard-notes', title='Shipped bug 2'),
    node(22, ['bug', 'builder:blocked'], author='JanMesaric', repo='humanitylabs-org/wizard-notes', comments=ASK_MIGUEL,
         title='Bug question'),
]
APPS = [node(30, ['feature', 'ready-to-test'], author='oscarhenrycollins', repo='humanitylabs-org/wizard-notes', title='App to try')]
GOALS = [
    node(40, ['goal'], author='jdefleur', title='Miguel goal', assignees={'nodes': [{'login': 'mistermizel'}]}),
    node(41, ['goal'], author='jdefleur', title='Jan goal', assignees={'nodes': [{'login': 'JanMesaric'}]}),
]


class Fixture(unittest.TestCase):
    def setUp(self):
        reset()
        people()
        S._needs.clear()
        self.saved = (S._view_search, S._view_nodes, S.view_stats, S.org_repos, S.view_repos)
        by_view = {'core': CORE, 'apps': APPS, 'bugs': BUGS}

        def search(token, view, q, **kw):
            if view in ('core', 'apps'):
                both = CORE + APPS
                return both, len(both)
            return by_view[view], len(by_view[view])
        S._view_search = search
        S._view_nodes = lambda token, q, **kw: (GOALS, len(GOALS))
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []
        S.view_repos = lambda *a, **k: []
        self.sw = Path(DATA) / 'switches.json'
        os.environ['WIZARD_SWITCHES_DIR'] = DATA
        if self.sw.exists():
            self.sw.unlink()
        f = Path(DATA) / 'private' / S.NEEDS_FILE
        if f.exists():
            f.unlink()

    def tearDown(self):
        S._view_search, S._view_nodes, S.view_stats, S.org_repos, S.view_repos = self.saved
        os.environ.pop('WIZARD_SWITCHES_DIR', None)

    def ids(self, person):
        return {i['id']: i['why'] for i in S.needs_you(person)['items']}


class CountingRule(Fixture):
    def test_miguel(self):
        got = self.ids('m')
        u = 'humanitylabs-org/wizard-ux#'
        self.assertEqual(got, {
            u + '1': 'Approve your idea', u + '2': 'Approve your idea',      # his and his agent's ideas
            u + '4': 'Your feature to try',
            'humanitylabs-org/wizard-notes#30': 'Your feature to try',       # filed by Oscar = Miguel
            u + '7': 'Builder asked you a question',
            'humanitylabs-org/wizard-notes#22': 'Builder asked you a question',
            'humanitylabs-org/wizard-ux#40': 'Your goal needs a status',
        })
        for left_out in ('3', '5', '6', '8', '9'):   # James's approval, Jan's review, James's show, Jan's question, building
            self.assertNotIn(u + left_out, got)
        for shipped in ('20', '21'):                 # shipped bugs wait on nobody
            self.assertNotIn('humanitylabs-org/wizard-notes#' + shipped, got)

    def test_james_gets_approvals_and_show(self):
        got = self.ids('j')
        u = 'humanitylabs-org/wizard-ux#'
        self.assertEqual(got.get(u + '3'), 'Approve your idea')
        self.assertEqual(got.get(u + '1'), 'Approve this core feature')
        self.assertEqual(got.get(u + '6'), 'Show-and-tell for you')
        self.assertNotIn(u + '4', got)
        self.assertNotIn(u + '7', got)

    def test_jan_never_gets_approvals_he_cannot_give(self):
        got = self.ids('n')
        u = 'humanitylabs-org/wizard-ux#'
        self.assertEqual(set(got), {u + '5', u + '8', 'humanitylabs-org/wizard-ux#41'})

    def test_shape_and_links(self):
        d = S.needs_you('m')
        self.assertEqual(d['count'], len(d['items']))
        self.assertFalse(d['on'])
        it = next(i for i in d['items'] if i['id'] == 'humanitylabs-org/wizard-ux#7')
        self.assertEqual(it, {'id': 'humanitylabs-org/wizard-ux#7', 'title': 'Q for Miguel', 'why': 'Builder asked you a question',
                              'link': '/wizardos-tracker/#item/humanitylabs-org/wizard-ux/7'})

    def test_pure_rule(self):
        cards = {'james': [{'id': 'a#1', 'turn': True, 'mine': False}, {'id': 'a#2', 'turn': True, 'mine': True}],
                 'test': [{'id': 'a#3', 'turn': True, 'shipped': True}, {'id': 'a#4', 'turn': True}],
                 'show': [{'id': 'a#5', 'turn': True}], 'answer': [{'id': 'a#6', 'turn': False}]}
        self.assertEqual([i['id'] for i in S.needs_you_items([{'james': False, 'groups': cards}])], ['a#2', 'a#4'])
        self.assertEqual([i['id'] for i in S.needs_you_items([{'james': True, 'groups': cards}])], ['a#1', 'a#2', 'a#4', 'a#5'])


class Switch(Fixture):
    def test_declared_off_with_issue(self):
        doc = S.switches_doc()
        sw = next(s for s in doc['switches'] if s['id'] == 'needs-you-badge')
        self.assertFalse(sw['on'])
        self.assertFalse(sw['default'])
        self.assertEqual(sw['issues'], ['humanitylabs-org/wizardos-tracker#87'])
        self.assertIn('switches:\n  contract: wizard.app-switches/1', (ROOT / 'wizard.md').read_text())
        self.assertIn('uses: [notifications]', (ROOT / 'wizard.md').read_text())

    def test_on_shows_in_answer(self):
        S._sw_set('needs-you-badge', True)
        self.assertTrue(S.needs_you('m')['on'])

    def test_page_sets_badge_from_api(self):
        self.assertIn("api('api/needs-you')", JS)
        self.assertIn('d && d.on ? Math.max(0, d.count | 0) : 0', JS)
        self.assertIn('b.set(n)', JS)
        self.assertIn('setInterval(needsBadge, 5 * 60000)', JS)


class Notify(Fixture):
    def post(self, title, message):
        self.sent.append((title, message))
        return True

    def test_off_sends_nothing(self):
        self.sent = []
        self.assertEqual(S.needs_you_tick(post=self.post), {'skipped': 'off'})
        self.assertEqual(self.sent, [])

    def test_first_summary_then_only_new(self):
        S._sw_set('needs-you-badge', True)
        self.sent = []
        out = S.needs_you_tick(post=self.post)
        self.assertTrue(out['first'])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], '7 things wait for you in the Tracker')
        self.assertIn('Builder asked you a question: Q for Miguel', self.sent[0][1])
        S._needs.clear()
        self.sent = []
        out = S.needs_you_tick(post=self.post)
        self.assertEqual((out['first'], out['new'], self.sent), (False, [], []))   # nothing repeats
        # a new question for Miguel -> exactly one alert for it
        CORE.append(node(10, ['feature', 'james-approved', 'builder:blocked'], author='JanMesaric', comments=ASK_MIGUEL,
                         title='New Q'))
        try:
            S._needs.clear()
            out = S.needs_you_tick(post=self.post)
        finally:
            CORE.pop()
        self.assertEqual(self.sent, [('Builder asked you a question', 'New Q (humanitylabs-org/wizard-ux#10)')])
        saved = json.loads((Path(DATA) / 'private' / S.NEEDS_FILE).read_text())
        self.assertIn('humanitylabs-org/wizard-ux#10', saved['ids'])
        self.assertEqual(oct((Path(DATA) / 'private' / S.NEEDS_FILE).stat().st_mode & 0o777), '0o600')

    def test_failed_post_is_retried(self):
        S._sw_set('needs-you-badge', True)
        S.needs_you_tick(post=lambda t, m: True)
        CORE.append(node(11, ['feature', 'james-approved', 'builder:blocked'], author='JanMesaric', comments=ASK_MIGUEL, title='R'))
        try:
            S._needs.clear()
            self.assertEqual(S.needs_you_tick(post=lambda t, m: False)['sent'], [])
            S._needs.clear()
            self.sent = []
            S.needs_you_tick(post=self.post)
        finally:
            CORE.pop()
        self.assertEqual(len(self.sent), 1)

    def test_notify_owner_speaks_mcp(self):
        import http.server
        import threading
        got = {}

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                got['body'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                b = b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"content":[],"isError":false}}\n\n'
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = S.NOTIFY_URL
        S.NOTIFY_URL = f'http://127.0.0.1:{srv.server_address[1]}/mcp'
        os.environ['WIZARD_TRUSTED_ORIGINS'] = 'https://box.ts.net,https://box.ts.net:8444'
        try:
            self.assertTrue(S.notify_owner('Hi', 'There'))
        finally:
            S.NOTIFY_URL = old
            os.environ.pop('WIZARD_TRUSTED_ORIGINS', None)
            srv.shutdown()
            srv.server_close()
        p = got['body']['params']
        self.assertEqual(p['name'], 'notify')
        self.assertEqual(p['arguments']['app'], 'wizardos-tracker')
        self.assertEqual(p['arguments']['link'], 'https://box.ts.net:8444/wizard-os-home/?open=wizardos-tracker')


if __name__ == '__main__':
    unittest.main()
