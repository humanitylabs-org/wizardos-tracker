"""Tracker 0.28.0 (Miguel, 11 Nov): Needs an answer. Open builder:blocked items get their own stage ('answer'), with
the builder's question in plain words and 'Waiting on <whom it @-mentioned>'.
Run: python3 -m unittest discover -s tests"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import S, reset
from test_017 import people
from test_0182 import node

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
B = 'wizardosbuilder'


def fn(name):
    start = JS.index('function ' + name + '(')
    depth, i = 0, JS.index('{', start)
    while True:
        depth += {'{': 1, '}': -1}.get(JS[i], 0)
        i += 1
        if depth == 0:
            return JS[start:i]


class Version(unittest.TestCase):
    def test_version(self):
        self.assertEqual(S.VERSION, '0.28.0')
        self.assertIn('version: 0.28.0', (ROOT / 'wizard.md').read_text())
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], '0.28.0')
        self.assertIn("PAGE_VERSION = '0.28.0'", JS)
        self.assertIn("version: '0.28.0' })", JS)


class Question(unittest.TestCase):
    def setUp(self):
        reset()
        people()

    def q(self, *rows):
        return S.builder_question(list(rows))

    def test_sentence_with_question_mark(self):
        body = ('Builder question (blocked, PR #21 left open):\n\nPR #21 has the whole of #17 behind a switch. The `reuse` '
                'check is red on [the bundle](https://x/y).\n\n@jdefleur (or Robert): which do you want?\n'
                '(a) a SHA256-locked exception at sha256 `b4992515d30c4305b0ed34c8daaba42642ca439e72e6ed19f47abd1732a10da5`; or\n'
                '(b) a ratchet rule that skips vendor bundles?\n')
        r = self.q((B, 'Builder started.'), (B, body), ('oscarhenrycollins', 'Answer (Miguel): (b). Is that ok?'))
        self.assertEqual(r['question'], 'James (or Robert): which do you want?')
        self.assertEqual(r['asked'], ['James'])
        self.assertEqual(r['at'], 1)

    def test_no_markdown_links_or_commit_ids(self):
        r = self.q((B, 'Question: can someone push `2529be0` to **GitHub** (see [the guide](https://x/g)) so I can read it?'))
        q = r['question']
        self.assertEqual(q, 'Can someone push to GitHub (see the guide) so I can read it?')
        for bad in ('2529be0', '`', '*', 'http', '['):
            self.assertNotIn(bad, q)

    def test_short_question_gets_its_context(self):
        r = self.q((B, 'So the two rules pull against each other. Which way should I go?\nA) Restyle.\nB) Keep it.'))
        self.assertEqual(r['question'], 'So the two rules pull against each other. Which way should I go?')

    def test_mention_run_reads_as_names(self):
        r = self.q((B, 'Calendar is read-only.\n\n@mistermizel @oscarhenrycollins which should I do?\n\n(a) Land #13 (keep both?)'))
        self.assertEqual(r['question'], 'Miguel or Oscar: which should I do?')
        self.assertEqual(r['asked'], ['Miguel', 'Oscar'])

    def test_paragraph_after_question(self):
        r = self.q((B, 'Builder blocked.\n\n**Question**\n\nPick a name for the new switch, then I go on.\n\nThanks.'))
        self.assertEqual(r['question'], 'Pick a name for the new switch, then I go on.')

    def test_no_builder_comment(self):
        self.assertEqual(self.q(('mistermizel', 'Any news?')), {'question': '', 'asked': [], 'at': None})


class Mentions(unittest.TestCase):
    def setUp(self):
        reset()
        people()

    def test_logins_to_team_names(self):
        names = S.mention_names('@jdefleur @defleur-agents @mistermizel @oscarhenrycollins @JanMesaric @hacalastudio')
        self.assertEqual(names, ['James', 'Miguel', 'Oscar', 'Jan', 'Robert'])

    def test_agents_are_their_people_and_strangers_dropped(self):
        self.assertEqual(S.mention_names('Question for @defleur-agents / @wizardosbuilder / @someone-else: ok?'), ['James'])
        self.assertEqual(S.mention_names('mail me at a@jdefleur.com, or see `@mistermizel` in ```\n@JanMesaric\n```'), ['Miguel'])

    def test_waiting_on_joins_with_or(self):
        w = S.waiting_on({'group': 'answer', 'opener': 'Jan', 'asked': ['Miguel', 'James']})
        self.assertEqual((w['who'], w['kind'], w['stuck']), (['Miguel', 'James'], 'person', False))
        self.assertEqual(S.waiting_on({'group': 'answer', 'opener': 'Jan', 'asked': []})['who'], ['Jan'])   # the filer
        self.assertEqual(' or '.join(w['who']), 'Miguel or James')


class Stage(unittest.TestCase):
    """A builder:blocked item lands in Needs an answer, wherever it was (queued, building, sorting)."""
    def setUp(self):
        reset()
        people()
        self.saved = (S._view_search, S.view_stats, S.org_repos)
        ask = {'totalCount': 2, 'nodes': [{'author': {'login': B}, 'body': 'Builder started.', 'createdAt': '2026-11-10T00:00:00Z'},
                                          {'author': {'login': B}, 'createdAt': '2026-11-10T01:00:00Z',
                                           'body': '@mistermizel @jdefleur: should this stay off by default?'}]}
        node_ = lambda *a, **k: node(*a, repo='humanitylabs-org/wizard-notes', **k)   # an app repo
        light = [node_(1, ['feature', 'builder:blocked']), node_(2, ['feature', 'building', 'builder:blocked'], author='mistermizel'),
                 node_(3, ['feature', 'triage', 'builder:blocked']), node_(4, ['feature']), node_(5, ['feature', 'building'])]
        heavy = [dict(n, comments=ask) for n in light if n['number'] == 1]
        self.queries = []

        def search(token, view, q, **kw):
            self.queries.append(q)
            return (heavy, 1) if 'builder:blocked' in q else (light, len(light)) if not kw.get('heavy') else ([], 0)
        S._view_search = search
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []

    def tearDown(self):
        S._view_search, S.view_stats, S.org_repos = self.saved

    def test_item_group(self):
        self.assertEqual(S.item_group('humanitylabs-org/wizard-notes', ['feature', 'builder:blocked']), 'answer')
        self.assertEqual(S.item_group('humanitylabs-org/wizard-notes', ['feature', 'building', 'builder:blocked']), 'answer')
        self.assertEqual(S.item_group('humanitylabs-org/wizard-notes', ['triage', 'builder:blocked']), 'answer')
        # past the builder, a stale label never hides an item from its own stage
        self.assertEqual(S.item_group('humanitylabs-org/wizard-notes', ['ready-to-test', 'builder:blocked']), 'test')
        self.assertEqual(S.item_group('humanitylabs-org/wizard-notes', ['approved', 'builder:blocked']), 'shipping')
        self.assertIn('answer', S.OPEN_GROUPS)
        self.assertEqual(S.OPEN_GROUPS.index('answer'), S.OPEN_GROUPS.index('test') + 1)

    def test_blocked_items_land_in_answer(self):
        d = S.board_split('m', {'view': 'apps'})
        g = d['groups']
        self.assertEqual(sorted(i['number'] for i in g['answer']), [1, 2, 3])
        self.assertEqual([i['number'] for i in g['queued']], [4])
        self.assertEqual([i['number'] for i in g['building']], [5])
        one = next(i for i in g['answer'] if i['number'] == 1)
        self.assertEqual(one['question'], 'Miguel or James: should this stay off by default?')
        self.assertEqual(one['waiting_on']['who'], ['Miguel', 'James'])
        self.assertTrue(one['turn'])                                   # Miguel is asked: Waiting on me first
        two = next(i for i in g['answer'] if i['number'] == 2)
        self.assertEqual(two['waiting_on']['who'], ['Miguel'])        # no comments known: the filer
        self.assertEqual(d['counts']['answer'], 3)
        self.assertTrue(any('label:"builder:blocked"' in q for q in self.queries))
        self.assertTrue(all(i['number'] != 1 for i in d['doing'] if i['group'] != 'answer'))


@unittest.skipUnless(shutil.which('node'), 'node missing')
class UI(unittest.TestCase):
    def run_js(self, src):
        return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)

    def test_strip_and_sections(self):
        src = fn('binsOf') + '\n' + fn('sectionsOf') + """
const w = v => binsOf(v).map(b => b.word);
console.log(JSON.stringify([w('core'), w('apps'), w('bugs'), sectionsOf('apps').map(s => s[0]), sectionsOf('bugs').map(s => s[0])]));"""
        core, apps, bugs, sec, bsec = self.run_js(src)
        self.assertEqual(core[:3], ['Waiting for approval', 'Build queue', 'Needs an answer'])
        self.assertEqual(apps[:4], ['Queued', 'Building', 'Needs an answer', 'AI review'])
        self.assertEqual(bugs[:3], ['Queued', 'Building', 'Needs an answer'])
        self.assertEqual(sec[:2], ['test', 'answer'])                 # a person's turn, next to Human review
        self.assertEqual(bsec[0], 'answer')

    def test_card_headline_and_question(self):
        src = ("const make = (t, c, x) => ({ c, x, kids: [], append(...k) { this.kids.push(...k); } });\n"
               "const document = { createTextNode: x => ({ x }) }; const cache = {}; const view = 'apps';\n"
               "const WAIT_WHAT = " + JS.split('const WAIT_WHAT = ')[1].split(';')[0] + ';\n' + fn('waitHead') + '\n'
               + fn('whereLine') + """
const i = { group: 'answer', question: 'Should it stay off?', waiting_on: { who: ['Miguel', 'James'], kind: 'person' } };
const p = waitHead(i), txt = n => n.kids && n.kids.length ? n.kids.map(txt).join('') : (n.x || '');
console.log(JSON.stringify([p.c, txt(p), whereLine(i), waitHead({ group: 'queued', blocked: true, waiting_on: { who: ['Jan'] } })]));""")
        cls, head, where, old = self.run_js(src)
        self.assertEqual(cls, 'bd-waiton')
        self.assertEqual(head, 'Waiting on Miguel or James to answer the builder')
        self.assertEqual(where, ['Should it stay off?', 'ask'])
        self.assertIsNone(old)                                         # 0.25.1's blocked-in-Queued headline is gone

    def test_answer_button(self):
        self.assertIn("smallBtn('Answer', () => openDetail(i, true))", JS)
        self.assertIn("'Open on GitHub ↗'", JS)


if __name__ == '__main__':
    unittest.main()
