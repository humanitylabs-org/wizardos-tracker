"""Tracker 0.56.0 (Miguel, 25 Nov 2026: 'the stats are too confusing... make it clear what the bottlenecks can be'):
the Builder pop-up names the slowest part, lists what can slow the builder down with a status word and one reason
each, and says what would help. The server works it out (builder_bottlenecks) so the tool and the page agree."""
import json, os, pathlib, subprocess, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / 'web' / 'app.js').read_text()

RES = {'at': 1, 'samples': 40, 'hours': 3.3, 'cpus': 4, 'mem_total_mb': 15992, 'workers': 4, 'test_boxes': 2,
       'load_per_cpu_p50': 0.4, 'load_per_cpu_p95': 0.9, 'cpu_saturated_pct': 0, 'cpu_busy_p50': 43.2, 'all_workers_busy_pct': 83,
       'held_pct': 0, 'busy_waits': 0, 'mem_free_p5_mb': 13000, 'disk_used_pct': 45, 'test_box_busy_pct': 33, 'tester_wait_pct': 0,
       'worker_min_per_item': 80, 'box_h_per_item': 0.18, 'box_h_source': 'guess',
       'verdict': 'fine', 'test_box_verdict': 'fine', 'reasons': [], 'got': 1, 'stale': False}
# 0.57.0: a repo holds two workers once the others run dry, so a repo's floor is its items x 80 min / 2: wizard-ux with
# 32 of 74 (21.3 h) no longer beats the 4 workers (24.7 h); with 50 of 74 (33.3 h) it still does, so this queue has 50.
WORK = {'pool': 74, 'bugs': 20, 'features': 54, 'held': 0, 'passed24': 56, 'running': 4, 'repos': 11, 'top_repo': 50,
        'top_name': 'wizard-ux', 'at': 1, 'stale': False}


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server
    importlib.reload(server)
    return server


def bn(s, work=WORK, res=RES):
    est = s.builder_estimate(work, res)
    out = s.builder_bottlenecks(work, res, est)
    return out, {r['key']: r for r in out['rows']}


class Bottlenecks(unittest.TestCase):
    def test_one_repo_is_the_limit_on_miguels_queue(self):
        s = fresh()
        out, by = bn(s)
        self.assertEqual(out['slowest'], 'Slowest part: wizard-ux. It has 50 of the items; two workers can be in it once other repos run dry.')
        self.assertEqual([r['key'] for r in out['rows']], ['one_repo', 'workers', 'server', 'test_boxes', 'people'])
        self.assertEqual((by['one_repo']['status'], by['one_repo']['say']), ('limit', 'wizard-ux has 50 of the 74 items; two workers can be in it once other repos run dry.'))
        # all workers busy 83% but more would not help: the repo holds the queue
        self.assertEqual(by['workers']['status'], 'tight'); self.assertIn('more would not help while one repo holds the queue', by['workers']['say'])
        self.assertEqual((by['server']['name'], by['server']['status']), ('Server (4 CPU, 16 GB)', 'fine'))
        self.assertEqual(by['server']['say'], 'CPU busy 43% of the time; jobs were never paused for it.')
        self.assertEqual((by['test_boxes']['name'], by['test_boxes']['say']), ('Test boxes (2)', 'In use 33% of the time; testers never waited for one.'))
        self.assertEqual(by['people']['say'], 'Nothing waits for a person.')
        self.assertEqual(out['help'], 'Nothing right now; the queue is mostly one repo.')
        self.assertEqual((out['items'], out['hours']), (74, 33.3))   # 0.57.0: 50 x 80 min / 2 workers

    def test_workers_are_the_limit_only_when_nothing_else_is(self):
        s = fresh()
        spread = {**WORK, 'top_repo': 8}
        out, by = bn(s, spread)
        self.assertEqual(by['workers']['status'], 'limit'); self.assertIn('Slowest part: the 4 workers', out['slowest'])
        self.assertEqual(out['help'], 'More workers.')
        out, by = bn(s, spread, {**RES, 'verdict': 'upgrade', 'busy_waits': 3})
        self.assertEqual((by['workers']['status'], by['server']['status']), ('tight', 'limit'))
        self.assertEqual(by['server']['say'], 'Too small for 4 workers: CPU busy 43% of the time; jobs were paused 3 times for it.')
        self.assertEqual((out['slowest'], out['help']), ('Slowest part: the server. It is too small for 4 workers.', 'A bigger server (KVM 8).'))
        out, by = bn(s, spread, {**RES, 'all_workers_busy_pct': 30})
        self.assertEqual((by['workers']['status'], out['slowest']), ('fine', 'Nothing is holding the builder back.'))
        self.assertEqual(by['workers']['say'], 'All 4 were busy only 30% of the time.')

    def test_test_boxes_memory_disk_and_people(self):
        s = fresh()
        out, by = bn(s, {**WORK, 'top_repo': 8}, {**RES, 'test_box_verdict': 'add', 'tester_wait_pct': 22, 'test_box_busy_pct': 90})
        self.assertEqual((by['test_boxes']['status'], by['test_boxes']['say']), ('limit', 'In use 90% of the time; testers waited for one 22% of the time.'))
        self.assertEqual(out['help'], 'Another test box.')
        out, by = bn(s, WORK, {**RES, 'mem_free_p5_mb': 1500, 'disk_used_pct': 91})
        self.assertEqual(by['server']['status'], 'tight')
        self.assertIn('only 1.5 GB of memory free at the lowest; disk 91% full', by['server']['say'])
        out, by = bn(s, {**WORK, 'held': 20})
        self.assertEqual((by['people']['status'], by['people']['say']), ('tight', '20 finished items wait for someone to say yes or no; not counted in the time above.'))
        self.assertEqual(out['help'], 'A yes or no on the 20 items waiting.')
        out, by = bn(s, {**WORK, 'pool': 3, 'top_repo': 1, 'held': 9})
        self.assertEqual(by['people']['status'], 'limit')

    def test_measuring_and_missing_server(self):
        s = fresh()
        out, by = bn(s, WORK, {**RES, 'verdict': 'measuring', 'test_box_verdict': 'measuring', 'hours': 0.5})
        self.assertEqual(by['server']['say'], 'Measuring, first answer in about 30 min.')
        self.assertEqual(by['test_boxes']['status'], 'measuring')
        self.assertEqual(out['slowest'], 'Slowest part: wizard-ux. It has 50 of the items; two workers can be in it once other repos run dry.')
        out, by = bn(s, {**WORK, 'top_repo': 8}, {**RES, 'verdict': 'measuring', 'test_box_verdict': 'measuring', 'hours': 0.5})
        self.assertEqual((by['workers']['status'], out['help']), ('tight', 'Wait for the server numbers (about 30 min).'))
        self.assertIn('still measuring', out['slowest'])
        out = s.builder_bottlenecks({**WORK, 'pool': 0}, None, None)
        self.assertEqual((out['slowest'], out['help']), ('Nothing to build right now.', 'Nothing; the builder is out of work.'))
        self.assertIsNone(s.builder_bottlenecks(None, None, None))

    def test_status_carries_it_and_the_tool_says_so(self):
        s = fresh()
        s.builder_status(seen=True, work=json.dumps(WORK), res=json.dumps({k: v for k, v in RES.items() if k not in ('got', 'stale')}))
        b = s.builder_status()
        self.assertEqual(b['bottlenecks']['slowest'], 'Slowest part: wizard-ux. It has 50 of the items; two workers can be in it once other repos run dry.')
        d = next(t for t in s.TOOLS if t['name'] == 'builder_status')['description']
        self.assertIn('bottlenecks', d); self.assertIn('fine|tight|limit|measuring', d)


class Page(unittest.TestCase):
    def run_js(self, b):
        start, end = JS.index("const SERVER_WORD"), JS.index('function showBuilder(b) {')
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
box.chip.click(); console.log(JSON.stringify(popped.map(n => ({ cls: n.cls, text: txt(n), kids: n.kids.map(k => k.cls) }))));
""" % json.dumps(b)
        out = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        a, p = out.stdout.strip().split('\n')
        return json.loads(a), json.loads(p)

    def test_popup_shows_the_checklist_not_raw_rows(self):
        s = fresh()
        est = s.builder_estimate(WORK, RES)
        b = {'running': True, 'work': WORK, 'estimate': est, 'server': RES, 'bottlenecks': s.builder_bottlenecks(WORK, RES, est)}
        chip, popup = self.run_js(b)
        self.assertIn('~33 h of work · server OK', chip['chip'])
        texts = [p['text'] for p in popup]
        self.assertEqual(texts[0], '74 items · about 33 h')
        self.assertEqual(texts[1], 'Slowest part: wizard-ux. It has 50 of the items; two workers can be in it once other repos run dry.')
        self.assertEqual(popup[1]['cls'], 'bd-work-s bd-bn-slow')
        self.assertEqual(texts[2], 'What can slow it down')
        self.assertEqual(texts[3].strip(), 'One repo at a time The limit'); self.assertEqual(popup[3]['kids'], ['', 'bd-bn-s limit'])
        self.assertEqual(texts[4], 'wizard-ux has 50 of the 74 items; two workers can be in it once other repos run dry.')
        self.assertIn('Workers (4) tight'.replace('tight', 'Tight'), [t.strip() for t in texts])
        self.assertIn('Waiting for a yes or no Fine', [t.strip() for t in texts])
        self.assertTrue(any(t.startswith('What would help:') and 'mostly one repo' in t for t in texts))
        self.assertIn('Done in the last day 56', [t.strip() for t in texts])
        self.assertTrue(any('Measured every 5 minutes over the last 3 h' in t for t in texts))
        joined = ' '.join(texts)
        for gone in ('Load per CPU', 'Held back', 'Memory free', 'Disk used', 'Queue clears', 'Can build now'):
            self.assertNotIn(gone, joined)

    def test_older_builder_without_bottlenecks(self):
        chip, popup = self.run_js({'running': True, 'work': {**WORK, 'hours': 31.7}, 'estimate': None, 'server': None, 'bottlenecks': None})
        self.assertIn('~32 h of work', chip['chip'])
        self.assertEqual(popup[0]['text'], '74 items · about 32 h')
        self.assertNotIn('What can slow it down', ' '.join(p['text'] for p in popup))


if __name__ == '__main__':
    unittest.main()
