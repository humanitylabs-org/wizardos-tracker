"""Tracker 0.64.0 (Miguel and Jan, 27 Nov 2026): All tab (#70), Created by me (#69), the item sheet's refresh (#68),
Tried by N · 👍 N · 👎 N (#86), a stale Update offer (#74), and one Needs you notification when the count rises (#87).
Run: python3 -m unittest discover -s tests"""
import json, os, pathlib, subprocess, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / 'web/app.js').read_text()
HTML = (ROOT / 'web/index.html').read_text()


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server, feedback_inbox
    importlib.reload(feedback_inbox)
    importlib.reload(server)
    return server


class Version(unittest.TestCase):
    def test_everywhere(self):
        s = fresh()
        self.assertEqual(s.VERSION, '0.64.0')
        self.assertIn("const PAGE_VERSION = '0.64.0';", JS)
        self.assertIn("version: '0.64.0' });", JS)
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], '0.64.0')
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], '0.64.0')
        self.assertIn('/api/switch-counts', json.loads((ROOT / 'openapi.json').read_text())['paths'])


class AllTab(unittest.TestCase):
    def test_all_is_left_of_core_and_keeps_the_other_tabs(self):
        tabs = [x for x in HTML.split('data-view="')[1:]]
        order = [t.split('"')[0] for t in tabs]
        self.assertEqual(order[:5], ['goals', 'all', 'core', 'apps', 'bugs'])
        self.assertIn("const VIEWS = ['goals', 'core', 'apps', 'bugs'];", JS)   # the server's views are unchanged
        self.assertIn("if (which === 'all') return Promise.all(ALL_OF.map(v => load(v, refresh)));", JS)
        self.assertIn("Object.defineProperty(cache, 'all', { get: allData, enumerable: false });", JS)

    def test_all_merges_once_each(self):
        start, end = JS.index('let allMemo = null;'), JS.index("Object.defineProperty(cache, 'all'")
        prog = ("const ALL_OF = ['core', 'apps', 'bugs']; const cache = {};" + JS[start:end] +
                "cache.core = {names: {a: 'A'}, repos: ['r/x'], groups: {queued: [{id: 'r/x#1'}], test: [{id: 'r/x#2'}]}};"
                "cache.apps = {names: {b: 'B'}, repos: ['r/y'], groups: {queued: [{id: 'r/y#3'}]}};"
                "cache.bugs = {names: {}, repos: ['r/y'], groups: {queued: [{id: 'r/y#3'}], relwait: [{id: 'r/y#4'}]}};"
                "const d = allData(); console.log(JSON.stringify({q: d.groups.queued.map(i => i.id), t: d.groups.test.length,"
                " r: d.groups.relwait.length, repos: d.repos, total: d.total, same: allData() === d, view: d.view}));")
        out = json.loads(subprocess.run(['node', '-e', prog], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out['q'], ['r/x#1', 'r/y#3'])
        self.assertEqual((out['t'], out['r'], out['total'], out['same'], out['view']), (1, 1, 4, True, 'all'))
        self.assertEqual(sorted(out['repos']), ['r/x', 'r/y'])

    def test_no_stats_on_all(self):
        self.assertIn("const statsOff = d.view === 'all';", JS)


class CreatedByMe(unittest.TestCase):
    def test_pill_and_filter(self):
        self.assertIn('id="mine-btn" aria-pressed="false"', HTML)
        self.assertIn("const keep = i => byWho(i) && byRepo(i) && (d.view === 'goals' || byMine(i));", JS)
        self.assertIn("store.get('board.mine') === true", JS)

    def test_split_names_the_persons_agents(self):
        s = fresh()
        base = s.policy_base()
        agents = {t['name']: [a['login'].lower() for a in t['agents']] for t in base['team']}
        self.assertIn('oscarhenrycollins', agents['Miguel'])
        self.assertIn("'agents_of': {t['name']: [a['login'].lower() for a in t['agents']] for t in base['team']}", (ROOT / 'app/server.py').read_text())


class DetailRefresh(unittest.TestCase):
    def test_button_and_timer(self):
        self.assertIn('id="d-reload" aria-label="Refresh this item"', HTML)
        self.assertIn("el('d-reload').onclick = () => refreshDetail(true);", JS)
        self.assertIn("Date.now() - detailAt >= 30000) refreshDetail(false); }, 5000);", JS)
        self.assertIn("api('api/detail?' + q)", JS)


class Tried(unittest.TestCase):
    def test_counts_by_issue(self):
        s = fresh()
        import feedback_inbox as fi
        body = {'contract': 'wizard.switch-counts/1', 'boxes': 3, 'counts': {
            'messenger:send-go': {'tried': 2, 'up': 1, 'down': 1, 'issues': ['humanitylabs-org/Messenger#12', 'bad issue']},
            'notes:x': {'tried': 0, 'up': 0, 'down': 0, 'issues': ['a/b#1']},
            'notes:y': {'tried': 1, 'up': 1, 'down': 0, 'issues': ['humanitylabs-org/messenger#12']}}}

        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(body).encode()
        fi._counts.clear()
        out = fi.switch_counts({'token': 't', 'login': 'm'}, opener=lambda req, timeout: R())
        self.assertEqual(out['boxes'], 3)
        self.assertEqual(out['counts']['humanitylabs-org/messenger#12'], {'tried': 3, 'up': 2, 'down': 1, 'switch': 'messenger:send-go'})
        self.assertNotIn('notes:x', out['switches'])
        self.assertEqual(out['switches']['messenger:send-go']['issues'], ['humanitylabs-org/Messenger#12'])

    def test_page_line(self):
        self.assertIn('Tried by ${c.tried} · 👍 ${c.up} · 👎 ${c.down}', JS)
        self.assertIn('id="d-tried"', HTML)


class StaleOffer(unittest.TestCase):
    def test_update_decides_on_fresh_facts(self):
        self.assertIn("if (catalogAge() > 15000) { catalog = null; await Promise.all([loadCatalog(true)", JS)
        self.assertIn("if (!a.update && !stopped) { staleOffer(id); }", JS)


class NeedsYouNotify(unittest.TestCase):
    def setUp(self):
        self.s = fresh()
        self.s._sw_set('needs-you-badge', True)
        self.s._box_person = lambda: 'm'
        self.sent = []
        self.count = [2]
        self.s.needs_you = lambda key, args=None: {'count': self.count[0], 'login': 'mistermizel',
                                                  'items': [{'id': f'r#{n}', 'why': 'To approve', 'title': f'T{n}'} for n in range(self.count[0])]}

    def post(self, title, msg):
        self.sent.append(title)
        return True

    def test_first_round_only_sets_the_mark_then_one_alert_per_rise(self):
        s = self.s
        self.assertFalse(s.needs_you_tick(post=self.post)['sent'])          # first: mark 2, quiet
        self.assertFalse(s.needs_you_tick(post=self.post)['sent'])          # same: quiet
        self.count[0] = 3
        self.assertTrue(s.needs_you_tick(post=self.post)['sent'])           # rose: one alert
        self.assertEqual(self.sent, ['3 things wait for you in the Tracker'])
        self.assertFalse(s.needs_you_tick(post=self.post)['sent'])          # never repeated
        self.count[0] = 1
        s.needs_you_tick(post=self.post)                                    # fell: mark 1, quiet
        self.count[0] = 2
        s.needs_you_tick(post=self.post)
        self.assertEqual(len(self.sent), 2)

    def test_off_sends_nothing(self):
        self.s._sw_set('needs-you-badge', False)
        self.assertEqual(self.s.needs_you_tick(post=self.post), {'skipped': 'off'})

    def test_unreachable_notifications_tries_once_more(self):
        s = self.s
        s.needs_you_tick(post=self.post)
        self.count[0] = 4
        self.assertFalse(s.needs_you_tick(post=lambda t, m: False)['sent'])
        self.assertTrue(s.needs_you_tick(post=self.post)['sent'])


if __name__ == '__main__':
    unittest.main()
