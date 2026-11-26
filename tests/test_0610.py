"""Tracker 0.61.0 (Miguel, 25 Nov 2026 evening): the builder now gives a repo that holds a big share of the queue (at
least a quarter) a second and third worker whenever it is a whole worker under its fair share, even while other repos
have work. The One repo row said 'up to 3 workers can be in it once other repos run dry', which never happened; it now
says 'it can get up to 3 workers whenever it holds a big share of the queue'. The serial floor stays top_repo / 3.
Run: python3 -m unittest discover -s tests"""
import os, pathlib, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]

# the live numbers of 25 Nov 16:00 UTC (work.json and resources.json on the builder host)
WORK = {'pool': 150, 'bugs': 16, 'features': 134, 'held': 0, 'passed24': 102, 'running': 7, 'repos': 15, 'top_repo': 64,
        'top_name': 'wizard-ux', 'repo_workers': 3, 'waiting': 77, 'oldest_h': 190, 'over_day': 46, 'at': 1, 'stale': False}
RES = {'at': 1, 'samples': 82, 'hours': 6.8, 'cpus': 4, 'workers': 12, 'test_boxes': 2, 'worker_min_per_item': 75.6,
       'box_h_per_item': 0.18, 'workers_enabled': 12, 'workers_fit': 6, 'workers_busy_now': 7, 'held_pct': 0,
       'verdict': 'fine', 'test_box_verdict': 'fine', 'reasons': [], 'got': 1, 'stale': False}
SAY = 'wizard-ux has 64 of the 150 items; it can get up to 3 workers whenever it holds a big share of the queue.'


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server
    importlib.reload(server)
    return server


class FairShareWording(unittest.TestCase):
    def test_one_repo_row_and_sentence(self):
        s = fresh()
        est = s.builder_estimate(WORK, RES)                                   # 6 fit: the workers bind
        by = {r['key']: r for r in s.builder_bottlenecks(WORK, RES, est)['rows']}
        self.assertEqual((est['limit'], by['one_repo']['status'], by['one_repo']['say']), ('workers', 'tight', SAY))
        res = {**RES, 'workers_fit': 12}                                      # 12 fit: wizard-ux binds
        est = s.builder_estimate(WORK, res)
        self.assertEqual(est['limit'], 'one_repo')
        self.assertAlmostEqual(est['hours'], round(64 * 75.6 / 60 / 3, 1))     # floor stays top_repo / 3
        out = s.builder_bottlenecks(WORK, res, est)
        by = {r['key']: r for r in out['rows']}
        self.assertEqual((by['one_repo']['status'], by['one_repo']['say']), ('limit', SAY))
        self.assertTrue(out['slowest'].startswith('Slowest part: wizard-ux. It has 64 of the items; it can get up to 3 '
                                                  'workers whenever it holds a big share of the queue.'), out['slowest'])

    def test_no_old_wording_left(self):
        for f in ('app/server.py', 'web/app.js', 'skill/SKILL.md'):
            self.assertNotIn('once other repos run dry', (ROOT / f).read_text(), f)

    def test_version(self):
        s = fresh()
        self.assertEqual(s.VERSION, '0.63.0')
        self.assertIn("const PAGE_VERSION = '0.63.0';", (ROOT / 'web/app.js').read_text())


if __name__ == '__main__':
    unittest.main()
