"""0.19.0 unit tests: bugs ship before review (Miguel, 10 Nov): Shipped flags on bug cards, Doesn't work during the AI
check or after the bug closed reopens it to Building; Queued reasons; agent-filed wording (wizardos-tracker#31); the
Goals count (goals of yours needing a status update); the minimal goal card; the version bar.
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import S, reset
from test_017 import people
from test_0182 import node

JS = (Path(__file__).resolve().parent.parent / 'web/app.js').read_text()


def fn(name):
    m = re.search(r'^function ' + name + r'\(.*?^}', JS, re.S | re.M)
    return m.group(0)


class FakeGH:
    """Replaces S.gh / S._current: one issue with state and labels; records writes."""
    def __init__(self, issue):
        self.issue, self.calls = issue, []

    def gh(self, token, method, path, body=None, **kw):
        self.calls.append((method, path, body))
        if method == 'PATCH':
            self.issue['state'] = body.get('state', self.issue['state'])
        elif method == 'POST' and path.endswith('/labels'):
            self.issue['labels'] |= set(body['labels'])
        elif method == 'DELETE' and '/labels/' in path:
            self.issue['labels'].discard(path.rsplit('/', 1)[1])
        return {}

    def current(self, acct, full, number):
        return {'state': self.issue['state'], 'state_reason': self.issue.get('reason'), 'user': {'login': self.issue['user']},
                'labels': [{'name': l} for l in sorted(self.issue['labels'])]}


class BugFlow(unittest.TestCase):
    def setUp(self):
        reset()
        people()
        self.saved = (S.gh, S._current)

    def tearDown(self):
        S.gh, S._current = self.saved

    def use(self, **issue):
        f = FakeGH({'state': 'open', 'user': 'mistermizel', **issue})
        S.gh, S._current = f.gh, f.current
        return f

    def test_doesnt_work_after_close_reopens(self):
        f = self.use(state='closed', labels={'bug', 'approved'})
        out = S.tested('m', {'repo': 'wizard-messenger', 'number': 7, 'note': 'Still broken'}, False)
        self.assertEqual(f.issue['state'], 'open')
        self.assertEqual(f.issue['labels'], {'bug', 'building'})
        self.assertTrue(out['reopened'])
        self.assertTrue(f.calls[0][2]['body'].startswith("Tested: doesn't work"))

    def test_doesnt_work_during_ai_check(self):
        f = self.use(labels={'bug', 'ai-review'})
        S.tested('m', {'repo': 'wizard-messenger', 'number': 8, 'note': 'Still broken'}, False)
        self.assertEqual(f.issue['labels'], {'bug', 'building'})
        self.assertEqual(f.issue['state'], 'open')

    def test_works_any_time_after_merge(self):   # 0.26: the check is optional and never waits for AI review
        f = self.use(labels={'bug', 'ai-review'})
        S.tested('m', {'repo': 'wizard-messenger', 'number': 9}, True)
        self.assertEqual(f.issue['labels'], {'bug', 'approved'})

    def test_features_unchanged(self):
        self.use(state='closed', labels={'feature', 'approved'})
        with self.assertRaises(S.Problem):
            S.tested('m', {'repo': 'wizard-messenger', 'number': 10, 'note': 'Still broken'}, False)

    def test_anyone_on_the_team(self):   # 0.26: not only the filer
        f = self.use(state='closed', labels={'bug', 'approved'}, user='JanMesaric')
        S.tested('m', {'repo': 'wizard-messenger', 'number': 11, 'note': 'Still broken'}, False)
        self.assertEqual(f.issue['state'], 'open')

    def test_not_planned_stays_closed(self):
        self.use(state='closed', reason='not_planned', labels={'bug'})
        with self.assertRaises(S.Problem):
            S.tested('m', {'repo': 'wizard-messenger', 'number': 12, 'note': 'Still broken'}, False)


class Board(unittest.TestCase):
    def setUp(self):
        reset()
        people()
        self.saved = (S._view_search, S.view_stats, S.org_repos)
        nodes = [node(1, ['bug', 'ai-review'], author='mistermizel', repo='humanitylabs-org/wizard-messenger'),
                 node(2, ['bug', 'ready-to-test'], author='defleur-agents', repo='humanitylabs-org/wizard-messenger'),
                 node(3, ['bug'], repo='humanitylabs-org/wizardos-tracker'),
                 node(4, ['bug'], repo='humanitylabs-org/wizard-messenger')]
        S._view_search = lambda token, view, q, **kw: (nodes, len(nodes))
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []

    def tearDown(self):
        S._view_search, S.view_stats, S.org_repos = self.saved

    def test_cards(self):
        d = S.board_split('m', {'view': 'bugs'})
        by = {i['number']: i for l in d['groups'].values() for i in l}
        self.assertTrue(by[1]['shipped'] and by[1]['can_fail'])          # Miguel filed it: may say Doesn't work in the AI check
        self.assertTrue(by[2]['shipped'] and by[2]['agent_filed'])
        self.assertTrue(by[2]['can_review'])   # 0.26: anyone on the team checks a bug
        self.assertEqual(by[3]['wait_reason'], 'Oscar builds this one')
        self.assertEqual(by[4]['wait_reason'], 'Next for the builder')
        self.assertIn('Bugs (Miguel, 10 Nov)', S.policy('m')['lines'][-1])
        self.assertEqual(S.policy('m')['builder_rules']['bug_flow']['auto_accept_seconds'], 7 * 86400)

    def test_version(self):
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 19, 0))
        self.assertIn(f"const PAGE_VERSION = '{S.VERSION}'", JS)


@unittest.skipUnless(shutil.which('node'), 'node missing')
class UI(unittest.TestCase):
    def run_js(self, src):
        return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)

    def test_bug_strip_and_wording(self):
        src = fn('binsOf') + '\n' + fn('sectionsOf') + '\n' + fn('shippedText') + '\n' + fn('bugLine') + '\n' + fn('whereLine') + """
const onboxOf = () => null, HUMAN_CHECK_TIP = '';
console.log(JSON.stringify([binsOf('bugs').map(b => b.word), binsOf('apps').map(b => b.word),
  whereLine({kind: 'bug', group: 'test', shipped: true, can_review: true})[0], whereLine({group: 'queued', wait_reason: 'Oscar builds this one'})[0],
  sectionsOf('apps').map(s => s[1]).includes('Filed')]));"""
        bins, apps, filer, queued, filed = self.run_js(src)
        self.assertEqual(bins, ['Queued', 'Building', 'Needs an answer', 'Merged', 'For testers', 'For everyone'])   # 0.26, 0.28
        self.assertEqual(apps, ['Queued', 'Building', 'Needs an answer', 'AI review', 'Human review', 'Shipping', 'Done'])
        self.assertEqual(filer, 'Merged · checking releases…')   # 0.25.1: 'Waiting on <who>' is the card's headline (waitHead)
        self.assertEqual(queued, 'Queued · Oscar builds this one')
        self.assertFalse(filed)
        self.assertNotIn("'Filed'", JS)
        self.assertNotIn("'Filed ·", JS)

    def test_goal_card_minimal(self):
        g = fn('goalCard')
        self.assertIn('Done list ${p.done}/${p.total}', g)
        self.assertNotIn('linkedLine', g)
        self.assertIn("getJSON('healthz')", JS)
        self.assertIn('120000', JS)


if __name__ == '__main__':
    unittest.main()
