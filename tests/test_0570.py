"""Tracker 0.57.0 (Miguel, 25 Nov 2026): the Builder lets a second worker into a repo once every other repo with work
has one (never a third), and it has no fixed worker count: its resource gate starts a job whenever the server has room,
up to 12 timers as a ceiling. The estimate and the bottleneck words follow: the busiest repo's floor is its items / 2,
'Workers (up to 12, resource-limited)' with the busy count, and the Server row says when the box is the limit.
Run: python3 -m unittest discover -s tests"""
import json, os, pathlib, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]

RES = {'at': 1, 'samples': 40, 'hours': 3.3, 'cpus': 4, 'mem_total_mb': 15992, 'workers': 12, 'test_boxes': 2,
       'load_per_cpu_p50': 0.4, 'load_per_cpu_p95': 0.9, 'cpu_saturated_pct': 0, 'cpu_busy_p50': 43.2, 'all_workers_busy_pct': 0,
       'held_pct': 0, 'busy_waits': 0, 'mem_free_p5_mb': 13000, 'disk_used_pct': 45, 'test_box_busy_pct': 33, 'tester_wait_pct': 0,
       'worker_min_per_item': 80, 'box_h_per_item': 0.18, 'box_h_source': 'guess',
       'workers_enabled': 12, 'workers_fit': 6, 'workers_busy_now': 5, 'doubled_pct': 10, 'workers_doubled_now': 2,
       'job_load': 0.6, 'job_mem_mb': 800,
       'verdict': 'fine', 'test_box_verdict': 'fine', 'reasons': [], 'got': 1, 'stale': False}
WORK = {'pool': 74, 'bugs': 20, 'features': 54, 'held': 0, 'passed24': 56, 'running': 5, 'repos': 11, 'top_repo': 32,
        'top_name': 'wizard-ux', 'at': 1, 'stale': False, 'repo_workers': 2}   # 0.58.0: this builder still says two


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server
    importlib.reload(server)
    return server


def bn(s, work=WORK, res=RES):
    est = s.builder_estimate(work, res)
    out = s.builder_bottlenecks(work, res, est)
    return est, out, {r['key']: r for r in out['rows']}


class Estimate(unittest.TestCase):
    def test_two_workers_per_repo_halve_the_busiest_repos_floor(self):
        s = fresh()
        e = s.builder_estimate(WORK, RES)
        # 6 fit on the box (not the 12 ceiling): 74 x 80 min / 6 = 16.4 h; wizard-ux's floor 32 x 80 / 2 = 21.3 h wins
        self.assertEqual((e['hours'], e['limit'], e['parallel'], e['workers'], e['workers_enabled'], e['repo_workers']),
                         (21.3, 'one_repo', 6, 6, 12, 2))
        e = s.builder_estimate({**WORK, 'top_repo': 10}, RES)
        self.assertEqual((e['hours'], e['limit']), (16.4, 'workers'))
        e = s.builder_estimate({**WORK, 'top_repo': 10, 'repos': 2}, RES)            # 2 repos x 2 workers = 4 wide
        self.assertEqual((e['parallel'], e['limit'], e['hours']), (4, 'repos', 24.7))

    def test_fit_is_used_when_reported_else_the_ceiling(self):
        s = fresh()
        self.assertEqual(s.builder_estimate(WORK, {**RES, 'workers_fit': None})['workers'], 12)
        self.assertEqual(s.builder_estimate(WORK, {k: v for k, v in RES.items() if k != 'workers_fit'})['workers'], 12)
        self.assertEqual(s.builder_estimate(WORK, {**RES, 'workers_fit': 0})['workers'], 12)   # nothing fits = unknown, not zero
        self.assertEqual(s.builder_estimate(WORK, {**RES, 'workers_fit': 40})['workers'], 12)  # never above the ceiling

    def test_new_server_numbers_pass_the_cleaner(self):
        s = fresh()
        s.builder_status(seen=True, work=json.dumps(WORK), res=json.dumps({k: v for k, v in RES.items() if k not in ('got', 'stale')}))
        sv = s.builder_status()['server']
        self.assertEqual((sv['workers_enabled'], sv['workers_fit'], sv['doubled_pct'], sv['job_load'], sv['job_mem_mb']), (12, 6, 10, 0.6, 800))


class Bottlenecks(unittest.TestCase):
    def test_one_repo_row_says_two_workers_can_be_in_it(self):
        s = fresh()
        est, out, by = bn(s)
        self.assertEqual(out['slowest'], 'Slowest part: wizard-ux. It has 32 of the items; it can get up to 2 workers whenever it holds a big share of the queue.')
        self.assertEqual((by['one_repo']['status'], by['one_repo']['say']),
                         ('limit', 'wizard-ux has 32 of the 74 items; it can get up to 2 workers whenever it holds a big share of the queue.'))
        self.assertEqual(by['workers']['name'], 'Workers (up to 12, resource-limited)')
        self.assertEqual((by['workers']['status'], by['workers']['say']),
                         ('fine', '5 running now of up to 12; about 6 fit on this server; more start whenever the server has room.'))
        self.assertEqual((by['server']['status'], by['server']['say']), ('fine', 'CPU busy 43% of the time; jobs were never held for resources.'))
        self.assertEqual(out['help'], 'Nothing right now; the queue is mostly one repo.')
        est, out, by = bn(s, {**WORK, 'repos': 1, 'top_repo': 10})
        self.assertEqual(by['one_repo']['say'], 'Only 1 repos have work, and a repo holds 2 workers at most.')

    def test_server_row_is_the_limit_when_jobs_are_held_for_resources(self):
        s = fresh()
        spread = {**WORK, 'top_repo': 8}
        est, out, by = bn(s, spread, {**RES, 'held_pct': 23, 'verdict': 'watch'})
        self.assertEqual((by['server']['status'], by['server']['say']), ('limit', 'Too small: jobs were held for resources 23% of the time; CPU busy 43% of the time.'))
        self.assertEqual(by['workers']['status'], 'tight')
        self.assertIn('the server row says why', by['workers']['say'])
        self.assertEqual((out['slowest'], out['help']), ('Slowest part: the server. Jobs are held for resources 23% of the time.', 'A bigger server (KVM 8).'))
        est, out, by = bn(s, spread, {**RES, 'held_pct': 8})
        self.assertEqual((by['server']['status'], by['server']['say']), ('fine', 'CPU busy 43% of the time; jobs were held for resources 8% of the time.'))
        self.assertEqual((by['workers']['status'], out['slowest']), ('fine', 'Nothing is holding the builder back.'))
        self.assertNotEqual(out['help'], 'More workers.')                           # never: the box, not a number, decides

    def test_older_builder_without_the_ceiling_keeps_the_old_rows(self):
        s = fresh()
        old = {k: v for k, v in RES.items() if k not in ('workers_enabled', 'workers_fit', 'doubled_pct', 'workers_doubled_now', 'job_load', 'job_mem_mb')}
        est, out, by = bn(s, {**WORK, 'top_repo': 8}, {**old, 'workers': 4, 'all_workers_busy_pct': 83})
        self.assertEqual(by['workers']['name'], 'Workers (4)')
        self.assertEqual((by['workers']['status'], out['help']), ('limit', 'More workers.'))
        self.assertEqual(by['server']['say'], 'CPU busy 43% of the time; jobs were never paused for it.')

    def test_measuring(self):
        s = fresh()
        est, out, by = bn(s, WORK, {**RES, 'verdict': 'measuring', 'test_box_verdict': 'measuring', 'hours': 0.5})
        self.assertEqual((by['workers']['status'], by['workers']['say']), ('measuring', '5 running now; the server decides how many fit (measuring).'))


class Words(unittest.TestCase):
    def test_version_and_tool(self):
        s = fresh()
        self.assertEqual(s.VERSION, '0.62.0')
        d = next(t for t in s.TOOLS if t['name'] == 'builder_status')['description']
        self.assertIn('whenever it holds a big share of the queue', d); self.assertIn('workers_enabled', d)
        self.assertIn('0.58.0', (ROOT / 'skill' / 'SKILL.md').read_text())


if __name__ == '__main__':
    unittest.main()
