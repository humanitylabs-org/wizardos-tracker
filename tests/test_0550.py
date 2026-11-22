"""Tracker 0.55.0 (humanitylabs-org/wizardos-tracker#146, switch agent-watches): agents' filed items get a free watch
that wakes their thread only when the item moves, until the fix is installed on this Wizard.
Run: python3 -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-0550-'))
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402
import watches as W  # noqa: E402

JS = (ROOT / 'web' / 'app.js').read_text()
OWN = 'defleur-agents'


def snap(**kw):
    base = {'id': 'humanitylabs-org/wizard-ux#7', 'title': 'Messenger drops a photo', 'url': 'https://github.com/humanitylabs-org/wizard-ux/issues/7',
            'state': 'open', 'reason': None, 'labels': ['bug'], 'comments_total': 1,
            'comments': [{'id': 'c1', 'author': OWN}], 'prs': [], 'open_prs': 0, 'delivers': []}
    base.update(kw)
    return base


def pr(n=9, **kw):
    p = {'id': f'humanitylabs-org/wizard-ux#{n}', 'url': f'https://github.com/humanitylabs-org/wizard-ux/pull/{n}',
         'state': 'open', 'merged': False, 'head': 'a' * 40, 'mergeable': 'MERGEABLE', 'merge_state': 'BLOCKED'}
    p.update(kw)
    return p


def watch(**kw):
    w = {'id': 'humanitylabs-org/wizard-ux#7', 'repo': 'humanitylabs-org/wizard-ux', 'number': 7, 'thread': 't_1',
         'note': 'check the photo fix', 'by': OWN, 'since': 1000.0, 'fp': None, 'first_seen': None, 'last_wake': None,
         'pending': [], 'wakes': 0, 'held': [], 'ended': None}
    w.update(kw)
    return w


def baseline(s=None, now=1000.0):
    w, out = W.step(watch(), s or snap(), now, OWN)
    assert out is None
    return w


class Fingerprint(unittest.TestCase):
    def test_own_comment_never_counts(self):
        w = baseline()
        mine = snap(comments_total=2, comments=[{'id': 'c1', 'author': OWN}, {'id': 'c2', 'author': OWN}])
        w2, out = W.step(w, mine, 1100.0, OWN)
        self.assertIsNone(out)
        self.assertEqual(w2['pending'], [])
        self.assertEqual(W.fingerprint(mine, OWN), W.fingerprint(snap(), OWN))
        # the same comment by anyone else is movement
        theirs = snap(comments_total=2, comments=[{'id': 'c1', 'author': OWN}, {'id': 'c2', 'author': 'wizardos-builder[bot]'}])
        _, out = W.step(w, theirs, 1100.0, OWN)
        self.assertIn('new comment by wizardos-builder[bot]', out['text'])

    def test_own_login_case_insensitive(self):
        self.assertEqual(W.fingerprint(snap(comments=[{'id': 'x', 'author': 'Defleur-Agents'}]), OWN)['comments']['n'], 0)

    def test_labels_state_and_prs_move(self):
        w = baseline(snap(prs=[pr()], open_prs=1))
        cases = [(snap(labels=['bug', 'building'], prs=[pr()], open_prs=1), 'labels +building'),
                 (snap(state='closed', reason='completed', prs=[pr()], open_prs=1), 'closed as completed'),
                 (snap(prs=[pr(head='b' * 40)], open_prs=1), 'has new commits'),
                 (snap(prs=[pr(mergeable='CONFLICTING')], open_prs=1), 'is now conflicting'),
                 (snap(prs=[pr(merge_state='CLEAN')], open_prs=1), 'merge state clean'),
                 (snap(prs=[pr(state='merged', merged=True)], delivers=[{'repo': 'humanitylabs-org/wizard-ux', 'number': 9, 'sha': 'c' * 40}]), 'merged'),
                 (snap(prs=[pr(), pr(11)], open_prs=2), 'PR humanitylabs-org/wizard-ux#11 linked')]
        for s, words in cases:
            _, out = W.step(w, s, 2000.0, OWN)
            self.assertIsNotNone(out, words)
            self.assertIn(words, out['text'])
            self.assertIn('https://github.com/humanitylabs-org/wizard-ux/pull/9', out['text'])

    def test_unknown_mergeable_keeps_last_answer(self):
        w = baseline(snap(prs=[pr()], open_prs=1))
        _, out = W.step(w, snap(prs=[pr(mergeable='UNKNOWN', merge_state='UNKNOWN')], open_prs=1), 2000.0, OWN)
        self.assertIsNone(out)

    def test_long_threads_count_by_newest_other(self):
        many = [{'id': f'c{i}', 'author': 'miguel' if i % 2 else OWN} for i in range(100)]
        w = baseline(snap(comments_total=150, comments=many))
        shifted = many[1:] + [{'id': 'mine', 'author': OWN}]   # an own comment pushes an old one out of the read
        _, out = W.step(w, snap(comments_total=151, comments=shifted), 2000.0, OWN)
        self.assertIsNone(out)


class Debounce(unittest.TestCase):
    def test_one_wake_per_ten_minutes_and_nothing_lost(self):
        w = baseline()
        w, out = W.step(w, snap(labels=['bug', 'building']), 1100.0, OWN)
        self.assertIsNotNone(out)
        self.assertEqual(w['last_wake'], 1100.0)
        w, out = W.step(w, snap(labels=['bug', 'building', 'ai-review']), 1100.0 + 300, OWN)   # 5 minutes later
        self.assertIsNone(out)
        self.assertEqual(len(w['pending']), 1)
        w, out = W.step(w, snap(labels=['bug', 'building', 'ai-review']), 1100.0 + 599, OWN)
        self.assertIsNone(out)
        w, out = W.step(w, snap(labels=['bug', 'building', 'ai-review']), 1100.0 + 600, OWN)
        self.assertIsNotNone(out)
        self.assertIn('labels +ai-review', out['text'])
        self.assertEqual((w['wakes'], w['pending']), (2, []))

    def test_first_look_is_a_baseline(self):
        w, out = W.step(watch(), snap(labels=['bug', 'building']), 1000.0, OWN)
        self.assertIsNone(out)
        self.assertEqual(w['first_seen'], 1000.0)


class Heartbeat(unittest.TestCase):
    def test_daily_check_in_only(self):
        w = baseline()
        w, out = W.step(w, snap(), 1000.0 + W.HEARTBEAT - 1, OWN)
        self.assertIsNone(out)
        w, out = W.step(w, snap(), 1000.0 + W.HEARTBEAT, OWN)
        self.assertIn('daily check-in', out['text'])
        self.assertFalse(out['final'])
        w, out = W.step(w, snap(), 1000.0 + W.HEARTBEAT + 3600, OWN)
        self.assertIsNone(out)

    def test_twenty_quiet_items_wake_twenty_times_a_day(self):
        ws = [baseline() for _ in range(20)]
        wakes = 0
        for t in range(1000, 1000 + 86400 + 1, 300):
            for i, w in enumerate(ws):
                ws[i], out = W.step(w, snap(), float(t), OWN)
                wakes += bool(out)
        self.assertEqual(wakes, 20)


class Ends(unittest.TestCase):
    MERGED = dict(prs=[pr(state='merged', merged=True)], delivers=[{'repo': 'humanitylabs-org/wizard-ux', 'number': 9, 'sha': 'c' * 40}])

    def test_installed_one_final_wake_then_nothing(self):
        w = baseline(snap(**self.MERGED))
        w, out = W.step(w, snap(**self.MERGED), 2000.0, OWN, installed=True)
        self.assertTrue(out['final'])
        self.assertIn('is installed on this Wizard', out['text'])
        self.assertIn('Go check it', out['text'])
        self.assertEqual(w['ended']['why'], 'installed')
        for t in (3000.0, 2000.0 + W.HEARTBEAT * 3):
            w, out = W.step(w, snap(labels=['bug', 'x'], **self.MERGED), t, OWN, installed=True)
            self.assertIsNone(out)

    def test_not_installed_while_a_pr_is_open(self):
        self.assertIsNone(W.end_reason(snap(open_prs=1, **self.MERGED), True))

    def test_final_wake_waits_for_the_gap(self):
        w = baseline(snap(**self.MERGED))
        w, out = W.step(w, snap(labels=['bug', 'building'], **self.MERGED), 2000.0, OWN)
        self.assertIsNotNone(out)
        w, out = W.step(w, snap(labels=['bug', 'building'], **self.MERGED), 2100.0, OWN, installed=True)
        self.assertIsNone(out)
        self.assertIsNone(w['ended'])
        w, out = W.step(w, snap(labels=['bug', 'building'], **self.MERGED), 2600.0, OWN, installed=True)
        self.assertTrue(out['final'])

    def test_not_planned_dropped_wontfix(self):
        for s in (snap(state='closed', reason='not_planned'), snap(labels=['feature', 'dropped']),
                  snap(state='closed', reason='not_planned', labels=['bug', 'wontfix']), snap(state='closed', reason='duplicate')):
            w, out = W.step(baseline(), s, 2000.0, OWN)
            self.assertTrue(out['final'], s)
            self.assertIn('not planned', out['text'])
            self.assertEqual(w['ended']['why'], 'not_planned')
            self.assertIsNone(W.step(w, s, 9e9, OWN)[1])

    def test_moved_item_is_followed(self):
        w = baseline()
        w, out = W.step(w, {'moved_to': 'humanitylabs-org/wizard-messenger#40'}, 1500.0, OWN)
        self.assertIsNone(out)
        self.assertEqual((w['id'], w['number'], w['fp']), ('humanitylabs-org/wizard-messenger#40', 40, None))
        w, out = W.step(w, snap(id='humanitylabs-org/wizard-messenger#40'), 1800.0, OWN)
        self.assertIn('moved from humanitylabs-org/wizard-ux#7 to humanitylabs-org/wizard-messenger#40', out['text'])


class ToolArgs(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(W.watch_args({}), (None, None))
        self.assertEqual(W.watch_args({'watch_thread': ' 20261122_163000_ab12 ', 'watch_note': 'see\nphoto'}), ('20261122_163000_ab12', 'see photo'))
        for bad in ({'watch_thread': 'has space'}, {'watch_thread': 7}, {'watch_thread': 'x' * 161},
                    {'watch_note': 'no thread'}, {'watch_thread': 't', 'watch_note': 5}, {'watch_thread': 't', 'watch_note': 'x' * 601}):
            with self.assertRaises(W.WatchError, msg=bad):
                W.watch_args(bad)

    def test_bad_watch_refuses_before_filing(self):
        filed = []
        with self.assertRaises(S.Problem) as e:
            S._filed_with_watch(lambda a: filed.append(a) or {}, {'repo': 'wizard-ux', 'title': 'x', 'watch_thread': 'bad id'})
        self.assertEqual(e.exception.code, 400)
        self.assertEqual(filed, [])
        r = S.rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'board_report_bug', 'arguments': {'repo': 'wizard-ux', 'title': 'abc', 'watch_note': 'n'}}})
        self.assertTrue(r['result']['isError'])
        self.assertIn('watch_note needs watch_thread', r['result']['content'][0]['text'])

    def test_schemas(self):
        tools = {t['name']: t for t in S.TOOLS}
        for name in ('board_report_bug', 'board_report_feature', 'report_or_request'):
            props = tools[name]['inputSchema']['properties']
            self.assertIn('watch_thread', props)
            self.assertIn('watch_note', props)
            self.assertNotIn('watch_thread', tools[name]['inputSchema'].get('required', []))
        self.assertIn('watch_list', S.CALLS)
        self.assertIn('watch_stop', S.CALLS)
        self.assertEqual(set(tools), set(S.CALLS))


class Server(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='tracker-0550-s-')
        self._priv, self._sw = S.PRIVATE, os.environ.get('WIZARD_SWITCHES_DIR')
        S.PRIVATE = Path(self.dir) / 'private'
        os.environ['WIZARD_SWITCHES_DIR'] = self.dir
        self._acct, self._budget = S.account_for, S.budget_ok
        S.account_for = lambda person=None, agent=False: ('~agent', {'token': 't', 'login': OWN})
        S.budget_ok = lambda token, low=None, now=None: True

    def tearDown(self):
        S.PRIVATE = self._priv
        S.account_for, S.budget_ok = self._acct, self._budget
        if self._sw is None:
            os.environ.pop('WIZARD_SWITCHES_DIR', None)
        else:
            os.environ['WIZARD_SWITCHES_DIR'] = self._sw

    def on(self, value=True):
        S._sw_set(W.SWITCH, value)

    def file(self, thread='t_1'):
        item = {'id': 'humanitylabs-org/wizard-ux#7', 'repo': 'humanitylabs-org/wizard-ux', 'number': 7, 'title': 'Messenger drops a photo',
                'url': 'https://github.com/humanitylabs-org/wizard-ux/issues/7', 'author': OWN}
        return S._filed_with_watch(lambda a: dict(item), {'repo': 'wizard-ux', 'title': 'x', 'watch_thread': thread, 'watch_note': 'photo'})

    def test_switch_is_listed_off_by_default(self):
        sw = next(s for s in S.switches_doc()['switches'] if s['id'] == 'agent-watches')
        self.assertFalse(sw['on'])
        self.assertFalse(sw['default'])
        self.assertEqual(sw['issues'], ['humanitylabs-org/wizardos-tracker#146'])

    def test_switch_off_no_watch_no_polling_no_wake(self):
        out = self.file()
        self.assertEqual(out['watch']['saved'], False)
        self.assertEqual(S._watches(), {})
        self.on()
        self.file()
        self.on(False)
        looked, woke = [], []
        r = S.watch_round(now=5000.0, snapshot=lambda w: looked.append(w) or snap(), installed=lambda s: False,
                          wake=type('Wk', (), {'send': lambda *a: woke.append(a) or {'sent': True}})())
        self.assertEqual((r['ran'], looked, woke), (False, [], []))
        self.assertEqual(S.watches_view(None), {'on': False, 'watches': []})

    def test_round_wakes_once_then_stops_on_installed(self):
        self.on()
        out = self.file()
        self.assertTrue(out['watch']['saved'])
        self.assertEqual(out['watch']['wakes'], 'held')   # no app wake route on WizardOS yet
        sent = []

        class Fake:
            available = True

            def send(self, thread, name, text, key):
                sent.append((thread, name, text, key))
                return {'sent': True}
        state = {'s': snap(), 'installed': False}
        rnd = lambda t: S.watch_round(now=t, snapshot=lambda w: state['s'], installed=lambda s: state['installed'], wake=Fake())
        rnd(1000.0)
        self.assertEqual(sent, [])
        state['s'] = snap(comments_total=2, comments=[{'id': 'c1', 'author': OWN}, {'id': 'c2', 'author': 'wizardos-builder[bot]'}])
        rnd(1300.0)
        rnd(1600.0)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], 't_1')
        self.assertIn('Your note when you filed it: photo', sent[0][2])
        state['s'] = snap(comments_total=2, comments=state['s']['comments'], **Ends.MERGED)
        state['installed'] = True
        rnd(2000.0)
        self.assertEqual(len(sent), 2)
        self.assertIn('last wake', sent[1][1])
        rnd(9e6)
        self.assertEqual(len(sent), 2)
        self.assertEqual(S.watch_list()['watches'][0]['ended']['why'], 'installed')
        self.assertEqual(S.watches_view(None)['watches'], [])

    def test_held_wakes_are_kept_when_no_route(self):
        self.on()
        self.file()
        S.watch_round(now=1000.0, snapshot=lambda w: snap(), installed=lambda s: False)
        S.watch_round(now=2000.0, snapshot=lambda w: snap(labels=['bug', 'building']), installed=lambda s: False)
        listed = S.watch_list({'thread': 't_1'})
        self.assertEqual(listed['wake_route'], 'missing')
        self.assertEqual(len(listed['watches'][0]['held']), 1)
        self.assertIn('labels +building', listed['watches'][0]['held'][0]['text'])

    def test_rate_limit_stops_the_round(self):
        self.on()
        self.file('t_1')
        looked = []

        def limited(w):
            looked.append(w['id'])
            raise S.Problem(429, 'GitHub limit reached; back in 5 minutes.', 'rate_limited')
        S.watch_round(now=1000.0, snapshot=limited, installed=lambda s: False)
        self.assertEqual(len(looked), 1)
        self.assertIn('GitHub limit', S.watch_list()['watches'][0]['error'])
        S.budget_ok = lambda token, low=None, now=None: False
        looked.clear()
        S.watch_round(now=2000.0, snapshot=limited, installed=lambda s: False)
        self.assertEqual(looked, [])

    def test_watch_stop_and_list(self):
        self.on()
        self.file()
        self.assertEqual(S.watches_view(None)['watches'][0]['thread'], 't_1')
        r = S.rpc({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'watch_stop', 'arguments': {'issue': 'humanitylabs-org/wizard-ux#7'}}})
        self.assertTrue(r['result']['structuredContent']['stopped'])
        self.assertEqual(S.watch_list()['watches'][0]['ended']['why'], 'stopped')
        r = S.rpc({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'watch_stop', 'arguments': {'issue': 'humanitylabs-org/wizard-ux#7'}}})
        self.assertTrue(r['result']['isError'])
        with self.assertRaises(S.Problem):
            S.watch_list({'thread': 'bad id'})

    def test_box_facts_kept_for_installed(self):
        self.on()
        S._note_box(S._box_facts({'release': '0.3.200', 'channel': 'stable', 'apps': {'wizard-messenger': '0.2.1'}}))
        S._note_box(S._box_facts({'apps': {'notes': '1.0.0'}}))
        kept = S._read('box_facts.json', {})['box']
        self.assertEqual((kept['release'], kept['apps']), ('0.3.200', {'wizard-messenger': '0.2.1', 'notes': '1.0.0'}))
        self.assertFalse(S.watch_installed('t', snap(open_prs=1, **Ends.MERGED)))
        self.assertFalse(S.watch_installed('t', snap()))


class Docs(unittest.TestCase):
    def test_docs_and_page(self):
        skill = (ROOT / 'skill' / 'SKILL.md').read_text()
        for word in ('watch_thread', 'watch_list', 'watch_stop', 'Switch: wizardos-tracker:agent-watches'):
            self.assertIn(word, skill)
        self.assertIn('**0.55.0**', (ROOT / 'wizard.md').read_text())
        self.assertIn('/api/watches', json.loads((ROOT / 'openapi.json').read_text())['paths'])
        self.assertIn("'Watched by '", JS)
        self.assertIn("api('api/watches')", JS)
        self.assertIn('id="d-watch"', (ROOT / 'web' / 'index.html').read_text())

    def test_no_secret_or_host_route_in_app(self):
        for name in ('app/server.py', 'app/watches.py', 'web/app.js'):
            text = (ROOT / name).read_text()
            self.assertNotIn('WIZARD_HEAVY_TOKEN', text)
            self.assertNotIn('/wizard/internal/schedules/create', text.replace('/wizard/internal/schedules/create takes only', ''))


if __name__ == '__main__':
    unittest.main()
