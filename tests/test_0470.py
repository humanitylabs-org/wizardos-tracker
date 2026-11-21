"""0.47.0 (James, 21 Nov 2026; wizardos-tracker#117): a bug labelled owner-correction fixes one of James's own
corrections. It never closes on 7 quiet days or the builder tester's pass: an open one waits on James ('Waiting on
James: Works, or a check on his box' with the tip), and one the builder closed on a real-box check reads 'Checked on
James's box'. Plain bugs are unchanged. /api/policy builder_rules.bug_flow.owner_correction describes the rule.
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import GH, S, reset
from test_017 import people
from test_0182 import node

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
BOT = 'wizardos-builder[bot]'
TIP = "One of James's own corrections: it closes only when James says Works or a check on his box is posted."
BOX = ('<!-- real-box-check -->\nAI check on James\'s own Wizard.\nBox: telos (James)\nVersion served: wizard-ux 0.3.160\n'
       'Seen: Back from a nested view stays in the app.')


def fn(name):
    m = re.search(r'\n(?:async )?function ' + name + r'\(', JS)
    i, depth = JS.index('{', m.start()), 0
    for j in range(i, len(JS)):
        depth += {'{': 1, '}': -1}.get(JS[j], 0)
        if depth == 0:
            return JS[m.start():j + 1]


def comments(*rows):
    return {'nodes': [{'author': {'login': who}, 'body': body, 'createdAt': at} for who, body, at in rows]}


class Policy(unittest.TestCase):
    def setUp(self):
        reset()
        self.p = S.policy()

    def test_bug_flow_owner_correction(self):
        oc = self.p['builder_rules']['bug_flow']['owner_correction']
        self.assertEqual(oc['label'], 'owner-correction')
        self.assertEqual(oc['tip'], TIP)
        self.assertEqual(oc['waits_on'], ['James'])
        self.assertEqual(oc['closed_text'], "Checked on James's box")
        self.assertEqual(oc['real_box_check']['marker'], '<!-- real-box-check -->')
        self.assertEqual(oc['real_box_check']['lines'], ['Box:', 'Version served:', 'Seen:'])
        self.assertIn(BOT, oc['real_box_check']['not_from'])
        self.assertIn('wizardosbuilder', oc['real_box_check']['not_from'])
        self.assertEqual(len(oc['never_closes_on']), 2)
        # the plain bug rule is unchanged
        bf = self.p['builder_rules']['bug_flow']
        self.assertEqual((bf['closed_by'], bf['auto_accept_seconds'], bf['tested_by']), ('builder', None, 'builder tester (before merge)'))

    def test_lines_say_it(self):
        text = '\n'.join(self.p['lines'])
        self.assertIn('Owner corrections (label owner-correction', text)
        self.assertIn("Checked on James's box", text)
        self.assertIn('Exactly two human steps: Pending approval', text)   # 0.46.0 unchanged
        self.assertEqual(self.p['human_steps'], ['feedback', 'show'])


class Rules(unittest.TestCase):
    def setUp(self):
        reset()
        people()
        self.base = S.policy_base()

    def test_real_box_check(self):
        self.assertTrue(S.real_box_check(BOX))
        self.assertTrue(S.real_box_check('<!-- real-box-check -->\n- **Box:** telos\n- **Version served:** 0.3.160\n- **Seen:** it opens'))
        for bad in (BOX.replace('<!-- real-box-check -->\n', ''), BOX.replace('Seen:', 'Notes:'),
                    BOX.replace('Version served: wizard-ux 0.3.160', 'Version served:'), BOX + '\nBut it still does not work.', '', None):
            self.assertFalse(S.real_box_check(bad), bad)

    def test_open_owner_correction_waits_on_james(self):
        for g in ('test', 'airev', 'shipping'):
            w = S.waiting_on({'group': g, 'category': 'bug', 'opener': 'Jan', 'labels': ['bug', 'ready-to-test', 'owner-correction']}, self.base)
            self.assertEqual(w['who'], ['James'], g)
            self.assertEqual((w['kind'], w['owner_correction'], w['why'], w['stuck']), ('person', True, TIP, False))
            self.assertEqual(w['what'], 'Works, or a check on his box')
        # the card flag alone counts too (labels may be any case on GitHub; _card lower-cases them)
        self.assertTrue(S.waiting_on({'group': 'test', 'category': 'bug', 'owner_correction': True}, self.base)['owner_correction'])

    def test_plain_bug_waits_on_nobody(self):
        w = S.waiting_on({'group': 'test', 'category': 'bug', 'opener': 'James', 'labels': ['bug', 'ready-to-test']}, self.base)
        self.assertEqual(w, {'who': [], 'kind': 'release', 'stuck': False})
        # a closed owner correction (Shipping) waits on nobody either
        w = S.waiting_on({'group': 'shipping', 'category': 'bug', 'state': 'closed', 'labels': ['owner-correction']}, self.base)
        self.assertEqual(w['who'], [])

    def test_card_flag(self):
        c = S._card(node(1, ['bug', 'Owner-Correction']), 'test')
        self.assertTrue(c['owner_correction'])
        self.assertFalse(S._card(node(2, ['bug']), 'test')['owner_correction'])

    def test_checked_on_james_box(self):
        closer = {'nodes': [{'actor': {'login': BOT}}]}
        done = {'closedAt': '2026-11-21T00:00:00Z', 'stateReason': 'COMPLETED', 'closer': closer}
        c = S.checked_of({**done, 'comments': comments(('defleur-agents', BOX, '2026-11-20T10:00:00Z'),
                                                       (BOT, "Checked on the owner's box: an AI check ...", '2026-11-20T10:30:00Z'))}, self.base)
        self.assertEqual(c['text'], "Checked on James's box")
        self.assertTrue(c['box'])
        self.assertIsNone(c['by'])
        self.assertEqual(c['at'], '2026-11-20T10:00:00Z')
        # the builder's own note alone (the check comment scrolled out of the last comments) still reads the same
        c = S.checked_of({**done, 'comments': comments((BOT, "Checked on the owner's box: ...", '2026-11-20T10:30:00Z'))}, self.base)
        self.assertEqual(c['text'], "Checked on James's box")
        # a check posted by the builder is no check; a broken-looking one is no check
        for who, body in ((BOT, BOX), ('defleur-agents', BOX.replace('Seen:', 'Notes:'))):
            c = S.checked_of({**done, 'comments': comments((who, body, '2026-11-20T10:00:00Z'),
                                                           (BOT, 'Checked (no problems in 7 days): ...', '2026-11-21T00:00:00Z'))}, self.base)
            self.assertEqual(c['text'], 'Checked (no problems in 7 days)', who)
        # James's own Works wins
        c = S.checked_of({**done, 'comments': comments(('defleur-agents', BOX, '2026-11-20T10:00:00Z'),
                                                       ('oscarhenrycollins', 'Tested: works \u2014 @jdefleur', '2026-11-20T11:00:00Z'))}, self.base)
        self.assertEqual(c['text'], 'Checked by James')
        # still open: pending, even with a check posted (the builder's sweep closes it)
        self.assertIsNone(S.checked_of({'comments': comments(('defleur-agents', BOX, '2026-11-20T10:00:00Z'))}, self.base))


class Board(unittest.TestCase):
    """board_split over a stubbed GitHub search: Bugs with one owner correction and one plain bug, both shipped."""
    def setUp(self):
        GH.issues.clear()
        reset()
        people()
        S._decided.clear()
        S._boards.clear()
        self.saved = (S._view_search, S._view_nodes, S.view_stats, S.org_repos)
        nodes = [node(1, ['bug', 'ready-to-test', 'owner-correction']), node(2, ['bug', 'ready-to-test'])]
        S._view_search = lambda token, view, q, **kw: (list(nodes) if view == 'bugs' else [], len(nodes) if view == 'bugs' else 0)
        S._view_nodes = lambda token, q, **kw: ([], 0)
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []

    def tearDown(self):
        S._view_search, S._view_nodes, S.view_stats, S.org_repos = self.saved
        S._boards.clear()
        reset()

    def test_cards(self):
        cards = {i['number']: i for l in S.board_split('m', {'view': 'bugs'})['groups'].values() for i in l}
        oc, plain = cards[1], cards[2]
        self.assertEqual(oc['group'], 'test')
        self.assertTrue(oc['owner_correction'])
        self.assertEqual(oc['waiting_on']['who'], ['James'])
        self.assertEqual(oc['waiting_on']['why'], TIP)
        self.assertFalse(oc['turn'])                     # Waiting on me is unchanged (0.45.0)
        self.assertFalse(plain['owner_correction'])
        self.assertEqual(plain['waiting_on']['who'], [])


class Source(unittest.TestCase):
    def test_tips(self):
        self.assertIn("const OWNER_CHECK_TIP = 'One of James’s own corrections: it closes only when James says Works or a check on his box is posted.';", JS)
        self.assertIn('const HUMAN_CHECK_TIP = ', JS)   # plain bugs keep theirs
        self.assertIn("' + OWNER_NOTE,", JS)

    def test_style_rules(self):
        new = JS[JS.index('// 0.47.0: the plain-words reason'):JS.index('// 0.26: \'Checked by Miguel')]
        self.assertNotRegex(new, r'#[0-9a-fA-F]{3,8}\b')
        self.assertNotIn('rgba(', new)


@unittest.skipUnless(shutil.which('node'), 'node missing')
class Card(unittest.TestCase):
    """The real waitHead / ocHint / checkTag on a fake DOM."""
    def run_js(self, tail):
        src = ("const make = (t, c, x) => ({ t, c, x, kids: [], append(...k) { this.kids.push(...k); } });\n"
               "const document = { createTextNode: x => ({ x }) }; const cache = { bugs: { me_person: 'James' } }; const view = 'bugs';\n"
               "const OWNER_CHECK_TIP = " + JS.split('const OWNER_CHECK_TIP = ')[1].split(';\n')[0] + ';\n'
               "const WAIT_WHAT = " + JS.split('const WAIT_WHAT = ')[1].split(';')[0] + ';\n'
               + fn('waitHead') + '\n' + fn('ocHint') + '\n' + fn('checkTag') + '\n'
               + "const txt = n => n == null ? null : n.kids && n.kids.length ? n.kids.map(txt).join('') : (n.x || '');\n" + tail)
        return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)

    def test_open_owner_correction(self):
        head, cls, title, hint, plain, plainhint = self.run_js("""
const wo = { who: ['James'], kind: 'person', owner_correction: true, what: 'Works, or a check on his box', why: "One of James's own corrections: it closes only when James says Works or a check on his box is posted." };
const i = { group: 'test', kind: 'bug', waiting_on: wo };
const p = waitHead(i), h = ocHint(i), q = { group: 'test', kind: 'bug', waiting_on: { who: [], kind: 'release' } };
console.log(JSON.stringify([txt(p), p.c, p.title, txt(h), waitHead(q), ocHint(q)]));""")
        self.assertEqual(head, 'Waiting on James: Works, or a check on his box')
        self.assertIn('me', cls.split())                 # James sees it is his
        self.assertEqual(title, TIP)
        self.assertEqual(hint, TIP)
        self.assertIsNone(plain)                         # plain bugs: no headline, as before
        self.assertIsNone(plainhint)

    def test_checked_on_box_tag(self):
        box, person, swept = self.run_js("""
console.log(JSON.stringify([txt(checkTag({ kind: 'bug', checked: { by: null, box: true, text: "Checked on James's box", at: '2026-11-20T10:00:00Z' } })),
  txt(checkTag({ kind: 'bug', checked: { by: 'Miguel', text: 'Checked by Miguel' } })),
  checkTag({ kind: 'bug', checked: { by: null, text: 'Checked (no problems in 7 days)' } })]));""")
        self.assertTrue(box.startswith("✓ Checked on James's box · "), box)
        self.assertEqual(person, '✓ Checked by Miguel')
        self.assertIsNone(swept)


if __name__ == '__main__':
    unittest.main()
