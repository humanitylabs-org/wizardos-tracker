"""0.20 unit tests: the 'Report or request' form (app/report.py, /api/report, MCP report_or_request), plain
'<Name> checks this one (he filed it)' / 'Your turn: check it' wording, and one 'Your turn first' sort on every tab.
Run: python3 -m unittest discover -s tests"""
import json
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
ORG = 'humanitylabs-org'
APPS = [{'id': 'messenger', 'name': 'Messenger', 'repo': 'humanitylabs-org/wizard-messenger'},
        {'id': 'calendar', 'name': 'Calendar', 'repo': 'wizard-calendar'}]
CORE = ('wizard-os', 'wizard-ux', 'wizard-app-manager', 'wizard-agent-service', 'try-wizard')


def fn(name, src=JS):
    return re.search(r'^function ' + name + r'\(.*?^}', src, re.S | re.M).group(0)


class Resolve(unittest.TestCase):
    def test_core_topics(self):
        got = {k: R.resolve(k, ORG, core_repos=CORE) for k in ('home', 'mac', 'updates', 'agent')}
        self.assertEqual({k: v['repo'] for k, v in got.items()},
                         {'home': f'{ORG}/wizard-ux', 'mac': f'{ORG}/try-wizard', 'updates': f'{ORG}/wizard-app-manager',
                          'agent': f'{ORG}/wizard-agent-service'})
        self.assertTrue(all(v['area'] == 'core' and not v['picked'] for v in got.values()))
        self.assertEqual([t['name'] for t in R.options()['core']], ['Home, Chats & Settings', 'Mac app', 'Updates & installing', 'Agent'])

    def test_installed_app(self):
        w = R.resolve('app:messenger', ORG, 'humanitylabs-org/wizard-messenger', 'Messenger', core_repos=CORE)
        self.assertEqual((w['repo'], w['name'], w['area']), (f'{ORG}/wizard-messenger', 'Messenger', 'app'))
        w = R.resolve('app:calendar', ORG, 'wizard-calendar', 'Calendar', core_repos=CORE)
        self.assertEqual(w['repo'], f'{ORG}/wizard-calendar')
        # no repo hint: the app id inside the org
        self.assertEqual(R.resolve('app:notes', ORG, None, 'Notes', core_repos=CORE)['repo'], f'{ORG}/notes')
        # an app whose repo is core counts as core
        self.assertEqual(R.resolve('app:x', ORG, 'wizard-os', 'X', core_repos=CORE)['area'], 'core')
        with self.assertRaises(R.ReportError):
            R.resolve('app:../etc', ORG, core_repos=CORE)
        with self.assertRaises(R.ReportError):
            R.resolve('a b c', ORG, core_repos=CORE)

    def test_not_sure_picks(self):
        w = R.resolve('unsure', ORG, text='Messenger shows the wrong chat after I react', apps=APPS, core_repos=CORE)
        self.assertEqual((w['repo'], w['name'], w['area'], w['picked']), (f'{ORG}/wizard-messenger', 'Messenger', 'app', True))
        w = R.resolve('unsure', ORG, text='The update failed to install overnight', apps=APPS, core_repos=CORE)
        self.assertEqual((w['repo'], w['area']), (f'{ORG}/wizard-app-manager', 'core'))
        w = R.resolve('unsure', ORG, text='My agent forgets what I said', apps=APPS, core_repos=CORE)
        self.assertEqual(w['repo'], f'{ORG}/wizard-agent-service')
        w = R.resolve('unsure', ORG, text='Something odd happened somewhere', apps=APPS, core_repos=CORE)
        self.assertEqual(w['repo'], f'{ORG}/wizard-ux')

    def test_text_title_footer(self):
        with self.assertRaises(R.ReportError):
            R.compose({'kind': 'other', 'text': 'long enough text'})
        with self.assertRaises(R.ReportError):
            R.compose({'kind': 'bug', 'text': 'short'})
        self.assertEqual(R.title_of('Reacting jumps the chat to the top. It should stay put.'), 'Reacting jumps the chat to the top')
        long = 'word ' * 40
        self.assertTrue(len(R.title_of(long)) <= 91 and R.title_of(long).endswith('…'))
        w = R.resolve('app:messenger', ORG, 'wizard-messenger', 'Messenger', core_repos=CORE)
        body = R.body_of('bug', 'It broke.', {'wizard_version': '0.3.149 (For testers)', 'app_version': '0.2.1', 'device': 'Mac · Chrome'}, w)
        self.assertTrue(body.startswith('It broke.\n\n---\nFiled with Report or request'))
        self.assertIn('WizardOS 0.3.149 (For testers) · Messenger 0.2.1 · Mac · Chrome', body)

    def test_landed(self):
        app = {'repo': 'o/wizard-messenger', 'name': 'Messenger', 'area': 'app', 'picked': False}
        core = {'repo': 'o/wizard-ux', 'name': 'Home, Chats & Settings', 'area': 'core', 'picked': False}
        self.assertEqual(R.landed('bug', app, 'the builder starts soon'), 'Filed as a bug in Messenger · the builder starts soon')
        self.assertEqual(R.landed('feature', core, 'waits for James or Miguel to approve'), 'Filed as a core feature · waits for James or Miguel to approve')
        self.assertEqual(R.landed('feature', app, 'the builder starts soon'), 'Filed as a feature for Messenger · the builder starts soon')


class Server(unittest.TestCase):
    def setUp(self):
        reset()
        self.saved = S._create
        self.calls = []
        S._create = lambda acct, full, title, body, label: (self.calls.append((full, title, body, label)) or
                                                            {'id': 'I1', 'number': 9, 'title': title, 'url': f'https://g/{full}/9', 'labels': [label], 'labelled': False})

    def tearDown(self):
        S._create = self.saved

    # 0.21: report_file files in wizard-os with label triage (tests/test_021.py); the 0.20 per-repo filing is gone.

    def test_options_and_mcp(self):
        o = S.report_options('owner')
        self.assertEqual([k['key'] for k in o['kinds']], ['bug', 'feature'])
        self.assertIn('wizard-ux', o['core_repos'])
        self.assertIn('report_or_request', [t['name'] for t in S.TOOLS])
        self.assertIn('report_or_request', S.CALLS)
        api = json.loads((ROOT / 'openapi.json').read_text())
        self.assertIn('/api/report', api['paths'])


class Wording(unittest.TestCase):
    def test_checks_this_one(self):
        reset()
        self.assertEqual(S.human_rule('bug', 'jdefleur', [], 'mistermizel'), (False, 'James checks this one (he filed it)'))
        self.assertEqual(S.human_rule('bug', 'defleur-agents', [], 'mistermizel'), (False, 'James checks this one (his agent filed it)'))
        reset({'team': [{'name': 'Ana', 'logins': ['ana'], 'pronoun': 'she', 'agents': []}, {'name': 'Miguel', 'logins': ['mistermizel'], 'agents': []}]})
        self.assertEqual(S.human_rule('bug', 'ana', [], 'mistermizel')[1], 'Ana checks this one (she filed it)')
        reset()
        self.assertNotIn('tests this:', (ROOT / 'app/server.py').read_text())

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_card_lines(self):
        src = fn('shippedText') + '\n' + fn('bugLine') + '\n' + fn('whereLine') + """
const ob = { 'o/r#1': { release: { text: 'In For testers 0.3.150' } } };
const onboxOf = i => ob[i.id] || null;
console.log(JSON.stringify([
  whereLine({id: 'o/r#1', kind: 'bug', group: 'test', shipped: true, can_review: true})[0],
  whereLine({id: 'o/r#1', kind: 'bug', group: 'test', shipped: true, can_review: false, review_rule: 'James checks this one (he filed it)'})[0],
  whereLine({id: 'o/r#1', kind: 'bug', group: 'airev', shipped: true})[0],
  whereLine({kind: 'bug', group: 'done', state_reason: 'completed', ship: {text: 'In For everyone 0.3.152'}, checked: {text: 'Checked by Miguel'}})[0],
  whereLine({kind: 'bug', group: 'shipping', state_reason: 'completed', ship: {text: 'In For testers 0.3.150'}, checked: {text: 'Checked (no problems in 7 days)'}})[0],
  whereLine({kind: 'bug', group: 'done', state_reason: 'completed', ship: {text: 'Shipped in Messenger 0.2.1'}, checked: {text: 'Checked by Jan'}})[0],
  whereLine({group: 'test', can_review: false, review_rule: 'Jan checks this one (he filed it)'})[0],
  whereLine({group: 'test', can_review: true})[0]]));"""
        got = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(got, ['Shipped in For testers 0.3.150 · Your turn: check it', 'Shipped in For testers 0.3.150 · Human check pending',
                               'Shipped in For testers 0.3.150 · Human check pending', 'Shipped in For everyone 0.3.152 · Checked by Miguel',
                               'Shipped in For testers 0.3.150 · Checked (no problems in 7 days)', 'Shipped in Messenger 0.2.1 · Checked by Jan',
                               'Jan checks this one (he filed it)', 'Your turn: check it'])

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_bug_strip(self):
        src = 'const HUMAN_CHECK_TIP = "x";\n' + fn('binsOf') + '\nconsole.log(JSON.stringify(binsOf("bugs")));'
        bins = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual([b['word'] for b in bins], ['Queued', 'Building', 'Shipped', 'Human check', 'Checked'])
        self.assertEqual(bins[2]['groups'], ['airev'])
        self.assertEqual(bins[4]['groups'], ['shipping', 'done'])
        self.assertIn("const HUMAN_CHECK_TIP = 'A quick sanity check by whoever filed it. It never holds up shipping.';", JS)

    def test_checked_of(self):
        reset()
        c = lambda *b: {'nodes': [{'body': x} for x in b]}
        self.assertEqual(S.checked_of({'comments': c('hi', 'Tested: works \u2014 @oscarhenrycollins')})['text'], 'Checked by Miguel')
        self.assertEqual(S.checked_of({'comments': c('Tested: works \u2014 @jdefleur'), 'closedAt': 'x', 'stateReason': 'COMPLETED'})['text'], 'Checked by James')
        closer = lambda who: {'nodes': [{'actor': {'login': who}}]}
        swept = {'nodes': [{'author': {'login': S.BUILDER}, 'body': 'No Doesn\u2019t work in 7 days: closing as fixed.'}]}
        self.assertEqual(S.checked_of({'comments': swept, 'closedAt': 'x', 'stateReason': 'COMPLETED', 'closer': closer(S.BUILDER)})['text'], 'Checked (no problems in 7 days)')
        self.assertEqual(S.checked_of({'comments': c('Merged.'), 'closedAt': 'x', 'stateReason': 'COMPLETED', 'closer': closer(S.BUILDER)})['text'], 'Closed on merge (no human check)')
        self.assertEqual(S.checked_of({'comments': c('Fixed.'), 'closedAt': 'x', 'stateReason': 'COMPLETED', 'closer': closer('defleur-agents')})['text'], 'Checked by James')
        self.assertIsNone(S.checked_of({'comments': c('Fixed.')}))
        self.assertIsNone(S.checked_of({'comments': c(), 'closedAt': 'x', 'stateReason': 'NOT_PLANNED'}))


class OneSort(unittest.TestCase):
    def test_one_sort_for_every_tab(self):
        self.assertIn("store.get('board.sort3')", JS)
        self.assertNotIn("'board.sort2.' + view", JS)
        self.assertIn(": 'turn'; };", JS)

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_miguels_items_lead_bugs_and_app_features(self):
        """The same lift render() does: every section of the tab (Bugs' Shipped stage too), items whose turn it is first."""
        src = fn('myTurn') + '\n' + fn('sectionsOf') + """
const it = (n, group, can_review) => ({ id: n, number: n, group, can_review });
const bugs = { test: [it(1, 'test', false), it(2, 'test', true), it(3, 'test', true)], airev: [it(4, 'airev')], building: [it(5, 'building')], queued: [], shipping: [] };
const apps = { test: [it(6, 'test', true)], queued: [it(7, 'queued')], building: [], airev: [], shipping: [] };
const lift = (v, g) => sectionsOf(v).filter(([k]) => k !== 'done' && g[k]).flatMap(([k]) => g[k].filter(myTurn)).map(i => i.number);
console.log(JSON.stringify([lift('bugs', bugs), lift('apps', apps)]));"""
        got = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(got, [[2, 3], [6]])


class Form(unittest.TestCase):
    def test_one_button_on_top(self):
        self.assertIn('id="report-open"', HTML)
        # 0.22: the round primary '+' in the one header row (floating on phones); test_022 checks the rest
        bar = HTML[HTML.index('id="bar"'):HTML.index('</header>')]
        self.assertIn('id="report-open"', bar)
        self.assertIn('class="bd-rr"', HTML)
        self.assertNotIn('report-btn', HTML + JS)
        self.assertNotIn('Report a bug', HTML)
        self.assertNotIn("api('api/bugs'", JS)

    def test_three_steps(self):   # 0.21: two steps (test_021); the prompts stay
        for word in ('Something’s broken', 'I’d like something new', 'api/report', 'Update first'):
            self.assertIn(word, RJS)
        self.assertIn('src="report.js"', HTML)
        self.assertEqual(R.PROMPTS['bug']['label'], 'What happened, and what should happen?')
        self.assertEqual(R.PROMPTS['feature']['label'], 'What would you like, and why?')

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_js_parses(self):
        subprocess.run(['node', '--check', str(ROOT / 'web/report.js')], check=True)

    def test_version(self):
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 20, 0))


if __name__ == '__main__':
    unittest.main()
