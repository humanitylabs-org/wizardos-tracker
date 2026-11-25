"""Tracker 0.55.0 (Miguel, 25 Nov 2026): how long the queue takes at the builder's real workers and test boxes, and
whether the builder server is big enough (its own 5-minute samples)."""
import json, os, pathlib, subprocess, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / 'web' / 'app.js').read_text()

RES = {'at': 1, 'samples': 40, 'hours': 3.3, 'cpus': 4, 'mem_total_mb': 15992, 'workers': 4, 'test_boxes': 2,
       'load_per_cpu_p50': 0.4, 'load_per_cpu_p95': 0.9, 'cpu_saturated_pct': 0, 'all_workers_busy_pct': 60,
       'held_pct': 0, 'mem_free_p5_mb': 13000, 'disk_used_pct': 45, 'test_box_busy_pct': 20, 'tester_wait_pct': 0,
       'worker_min_per_item': 80, 'box_h_per_item': 0.18, 'box_h_source': 'guess',
       'verdict': 'fine', 'test_box_verdict': 'fine', 'reasons': ['ok'], 'evil': '<script>'}


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server
    importlib.reload(server)
    return server


class Estimate(unittest.TestCase):
    def test_reported_cleaned_and_estimated(self):
        s = fresh()
        b = s.builder_status()
        self.assertIsNone(b['server']); self.assertIsNone(b['estimate'])
        s.builder_status(seen=True, work=json.dumps({'pool': 72, 'bugs': 40, 'features': 32, 'held': 0, 'passed24': 30,
                                                     'running': 4, 'repos': 12, 'top_repo': 10, 'top_name': 'wizard-ux'}))
        s.builder_status(seen=True, res=json.dumps(RES))
        b = s.builder_status()
        self.assertNotIn('evil', b['server'])
        self.assertEqual((b['server']['verdict'], b['server']['workers'], b['server']['stale']), ('fine', 4, False))
        e = b['estimate']
        # 72 items x 80 min / 4 at once = 24 h; boxes allow 2 / 0.18 = 11 an hour; wizard-ux's 10 one by one = 13.3 h
        self.assertEqual((e['hours'], e['limit'], e['parallel'], e['workers'], e['test_boxes']), (24.0, 'workers', 4, 4, 2))
        self.assertEqual(e['top_name'], 'wizard-ux')
        s.builder_status(seen=True, work=json.dumps({'pool': 1, 'top_name': '<b>x</b>'}))
        self.assertEqual(s.builder_status()['work']['top_name'], '')

    def test_limits(self):
        s = fresh()
        w = {'pool': 30, 'repos': 2, 'top_repo': 5}
        self.assertEqual(s.builder_estimate(w, RES)['limit'], 'repos')                     # 2 at once: 20 h
        self.assertEqual(s.builder_estimate({'pool': 30, 'repos': 6, 'top_repo': 25}, RES)['limit'], 'one_repo')
        e = s.builder_estimate({'pool': 30, 'repos': 6, 'top_repo': 2}, {**RES, 'box_h_per_item': 1.0})
        self.assertEqual((e['limit'], e['hours']), ('test_boxes', 15.0))                   # 2 boxes, 1 h per item
        self.assertIsNone(s.builder_estimate({'pool': 3}, {**RES, 'worker_min_per_item': None}))

    def test_bad_reports_never_break_the_switch(self):
        s = fresh()
        for bad in ('not json', '[]', json.dumps({'verdict': 'explode'})):
            s.builder_status(seen=True, res=bad)
        self.assertIsNone(s.builder_status()['server'])
        s.builder_status(seen=False, res=json.dumps(RES))      # only the builder may report
        self.assertIsNone(s.builder_status()['server'])

    def test_tool_says_it_is_real(self):
        s = fresh()
        d = next(t for t in s.TOOLS if t['name'] == 'builder_status')['description'] if hasattr(s, 'TOOLS') else \
            (ROOT / 'app' / 'server.py').read_text()
        self.assertNotIn('Mock-up: not wired', (ROOT / 'app' / 'server.py').read_text())
        self.assertIn('estimate', d)


class Page(unittest.TestCase):
    def run_js(self, b):
        start, end = JS.index("const SERVER_WORD"), JS.index('function showBuilder(b) {')   # 0.56.0: same block, see test_0560
        code = """
const out = []; let popped = null;
const make = (t, c, x) => ({ tag: t, cls: c, text: x || '', kids: [], append(...k) { this.kids.push(...k); }, set onclick(f) { this.click = f; } });
const box = { hidden: true, replaceChildren(c) { this.chip = c; } };
const el = () => box; const me = { connected: true }; const when = () => 'earlier';
const pop = (a, t, items) => { popped = items.filter(Boolean); };
""" + JS[start:end] + """
workLine(%s);
const txt = n => n.text + n.kids.map(txt).join(' ');
console.log(JSON.stringify({ chip: txt(box.chip), hidden: box.hidden }));
box.chip.click(); console.log(JSON.stringify(popped.map(txt)));
""" % json.dumps(b)
        out = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        a, p = out.stdout.strip().split('\n')
        return json.loads(a), json.loads(p)

    def test_chip_and_popup(self):
        work = {'pool': 72, 'bugs': 40, 'features': 32, 'held': 0, 'passed24': 30, 'hours': 57.6, 'stale': False}
        est = {'hours': 24.0, 'workers': 4, 'test_boxes': 2, 'parallel': 4, 'limit': 'workers', 'item_hours': 1.33, 'repos': 12, 'top_repo': 10}
        chip, popup = self.run_js({'running': True, 'work': work, 'estimate': est, 'server': {**RES, 'stale': False, 'got': 1}})
        self.assertIn('~24 h of work · server OK', chip['chip'])
        self.assertIn('72 items · about 24 h', popup[0])          # 0.56.0: the pop-up is the bottleneck checklist (test_0560)
        chip, popup = self.run_js({'running': True, 'work': work, 'estimate': {**est, 'limit': 'one_repo', 'hours': 30, 'top_name': 'wizard-os'},
                                   'server': {**RES, 'verdict': 'upgrade', 'reasons': ['every CPU was busy'], 'stale': False, 'got': 1}})
        self.assertIn('server too small', chip['chip'])
        chip, _ = self.run_js({'running': True, 'work': work, 'estimate': None, 'server': None})   # older builder: as before
        self.assertIn('~2.5 days of work', chip['chip']); self.assertNotIn('server', chip['chip'])


if __name__ == '__main__':
    unittest.main()
