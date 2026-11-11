"""0.19.1 unit tests: the Goals number is every open goal; Human review / Shipping / Done name the release that has
the change (wizardos-tracker#7); items of wizardos-builder never reach the board (0.30.1: wizardos-tracker items do).
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import S, reset
from test_0182 import node

JS = (Path(__file__).resolve().parent.parent / 'web/app.js').read_text()


def fn(name):
    return re.search(r'^function ' + name + r'\(.*?^}', JS, re.S | re.M).group(0)


class Hidden(unittest.TestCase):
    def test_query_excludes_hidden_repos(self):
        q = S.unhide_q('org:humanitylabs-org is:issue is:open label:bug')
        self.assertNotIn('wizardos-tracker', q)
        self.assertIn(' -repo:humanitylabs-org/wizardos-builder', q)
        self.assertEqual(S.unhide_q(q), q)
        self.assertEqual(S.unhide_q('repo:humanitylabs-org/wizard-ux is:issue'), 'repo:humanitylabs-org/wizard-ux is:issue')

    def test_view_nodes_drop_hidden(self):
        seen, saved = [], S.graphql
        nodes = [node(1, ['bug']), node(2, ['bug'], repo='humanitylabs-org/wizardos-tracker'),
                 node(3, ['bug'], repo='HumanityLabs-org/WizardOS-Builder'), node(4, ['bug'], repo='humanitylabs-org/wizard-messenger')]
        try:
            S.graphql = lambda tok, q, v, **k: (seen.append(v['q']), {'data': {'search': {'issueCount': 2, 'nodes': nodes, 'pageInfo': {}}}})[1]
            got, total = S._view_nodes('t', 'org:humanitylabs-org is:issue is:open')
        finally:
            S.graphql = saved
        self.assertEqual([n['number'] for n in got], [1, 2, 4])
        self.assertIn('-repo:humanitylabs-org/wizardos-builder', seen[0])

    def test_goal_links_drop_hidden(self):
        reset()
        def ref(n, repo):
            return {'source': {'__typename': 'Issue', 'number': n, 'title': 'x', 'url': f'https://g/{repo}/{n}', 'state': 'OPEN',
                               'repository': {'nameWithOwner': repo}, 'labels': {'nodes': [{'name': 'bug'}]}}}
        g = {'url': 'https://g/goal', 'timelineItems': {'nodes': [ref(1, 'humanitylabs-org/wizard-ux'), ref(2, 'humanitylabs-org/wizardos-tracker'),
                                                                   ref(3, 'humanitylabs-org/wizardos-builder')]}}
        self.assertEqual([i['number'] for i in S.linked_items(g)], [1, 2])

    def test_queue_reason_unchanged(self):
        self.assertEqual(S.queue_reason('humanitylabs-org/wizardos-builder'), 'Oscar builds this one')
        self.assertEqual(S.queue_reason('humanitylabs-org/wizardos-tracker'), 'Next for the builder')


class Release(unittest.TestCase):
    def test_release_of(self):
        saved = S.ship_one
        parts = {}
        try:
            S.ship_one = lambda t, d, base=None: parts[d['repo']]
            ux, msg, spec = {'repo': 'o/wizard-ux'}, {'repo': 'o/wizard-messenger'}, {'repo': 'o/wizard-os'}
            parts.update({'o/wizard-ux': ('testers', 'In For testers 0.3.140', '0.3.140'),
                          'o/wizard-messenger': ('done', 'Shipped in Messenger 0.2.0-unified.16.34', 'Messenger 0.2.0-unified.16.34'),
                          'o/wizard-os': ('done', 'Shipped on merge (no release needed)', None)})
            self.assertEqual(S.release_of('t', [msg])['text'], 'Shipped in Messenger 0.2.0-unified.16.34')
            self.assertEqual(S.release_of('t', [ux, msg])['text'], 'In For testers 0.3.140')
            self.assertEqual(S.release_of('t', [spec, msg])['text'], 'Shipped in Messenger 0.2.0-unified.16.34')
            self.assertIsNone(S.release_of('t', [spec]))
            self.assertIsNone(S.release_of('t', []))
            parts['o/wizard-ux'] = ('waiting', 'Waiting for release', None)
            self.assertIsNone(S.release_of('t', [ux, msg]))
            parts['o/wizard-ux'] = ('done', 'In For everyone 0.3.139', '0.3.139')
            self.assertEqual(S.release_of('t', [ux]), {'text': 'In For everyone 0.3.139', 'version': '0.3.139'})
        finally:
            S.ship_one = saved

    def test_kept_wording(self):
        self.assertEqual(S.kept_text({'text': 'Shipped in 0.3.134', 'version': '0.3.134'}), 'In For everyone 0.3.134')
        self.assertEqual(S.kept_text({'text': 'Shipped in Messenger 0.5.1', 'version': 'Messenger 0.5.1'}), 'Shipped in Messenger 0.5.1')
        self.assertEqual(S.kept_text({'text': 'Shipped in Mac app 1.2', 'version': 'mac 1.2'}), 'Shipped in Mac app 1.2')

    def test_onbox_carries_release(self):
        saved = (S.account_for, S.verdict, S.release_of)
        try:
            S.account_for = lambda p, *a: (p, {'token': 'tok_x_onbox', 'login': 'x'})
            S.verdict = lambda t, ds, n, box: {'state': 'yes', 'text': S.ON_TEXT, 'fix': None, 'parts': [], 'apps': []}
            S.release_of = lambda t, ds: {'text': 'In For testers 0.3.140', 'version': '0.3.140'}
            out = S.on_box('m', {'box': {'release': '0.3.140'}, 'items': [{'id': 'o/r#77', 'delivers': [{'repo': 'o/r', 'sha': 'a' * 40}]}]})
        finally:
            (S.account_for, S.verdict, S.release_of) = saved
        self.assertEqual(out['items']['o/r#77']['release']['text'], 'In For testers 0.3.140')

    def test_version(self):
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 19, 1))
        self.assertIn(f"const PAGE_VERSION = '{S.VERSION}'", JS)
        self.assertIn('id="d-release"', (Path(__file__).resolve().parent.parent / 'web/index.html').read_text())


@unittest.skipUnless(shutil.which('node'), 'node missing')
class UI(unittest.TestCase):
    def run_js(self, src):
        return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)

    def test_goals_count_is_all_open_goals(self):
        d = {'groups': {'goals': [{'turn': True}, {}, {'status': {'color': 'red'}}]}, 'total': 3}
        got = self.run_js(fn('goalsOpen') + f'\nconsole.log(JSON.stringify([goalsOpen({json.dumps(d)}), goalsOpen(null), goalsOpen({{groups: {{goals: [{{}}]}}, total: 70}})]));')
        self.assertEqual(got, [3, 0, 70])
        self.assertIn("const GOALS_TIP = 'Open goals';", JS)
        self.assertNotIn('goalsDue', JS)

    def test_release_lines(self):
        src = fn('releaseOf') + """
const onboxOf = i => i.ob || null;
console.log(JSON.stringify([
  releaseOf({group: 'test', ob: {state: 'yes', release: {text: 'In For testers 0.3.140'}}}),
  releaseOf({group: 'test', ob: {state: 'no', release: null}}),
  releaseOf({group: 'shipping', ship: {text: 'In For testers 0.3.140', version: '0.3.140'}}),
  releaseOf({group: 'shipping', ship: {text: 'Waiting for release', version: null}}),
  releaseOf({group: 'done', ship: {text: 'Shipped in Messenger 0.2.0-unified.16.34', version: 'Messenger 0.2.0-unified.16.34'}}),
  releaseOf({group: 'building'})]));"""
        self.assertEqual(self.run_js(src), ['In For testers 0.3.140', '', 'In For testers 0.3.140', '', 'Shipped in Messenger 0.2.0-unified.16.34', ''])


if __name__ == '__main__':
    unittest.main()
