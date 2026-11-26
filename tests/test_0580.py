"""Tracker 0.58.0 (Miguel, 25 Nov 2026): the Builder lets up to three workers into a repo once every other repo with work
has one (never a fourth) and says so in its workload report (repo_workers). The estimate and the bottleneck words
follow: the busiest repo's floor is its items / repo_workers, the work runs min(fit, repo_workers x repos) wide, the One
repo row reads 'it can get up to 3 workers whenever it holds a big share of the queue', and 'A bigger server (KVM 8)' is the help as soon
as the Server row is tight or the limit while one repo is not what binds.
Run: python3 -m unittest discover -s tests"""
import json, os, pathlib, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_0570 import RES, WORK, fresh, bn   # noqa: E402

WORK3 = {**WORK, 'repo_workers': 3}
WORK0 = {k: v for k, v in WORK.items() if k != 'repo_workers'}   # a builder that sends no repo_workers


class Estimate(unittest.TestCase):
    def test_three_workers_per_repo_from_the_builders_report(self):
        s = fresh()
        e = s.builder_estimate(WORK3, RES)
        # 6 fit on the box: 74 x 80 min / 6 = 16.4 h; wizard-ux's floor 32 x 80 / 3 = 14.2 h no longer wins
        self.assertEqual((e['hours'], e['limit'], e['parallel'], e['workers'], e['repo_workers']), (16.4, 'workers', 6, 6, 3))
        e = s.builder_estimate({**WORK3, 'top_repo': 50}, RES)                        # 50 x 80 / 3 = 22.2 h beats 16.4
        self.assertEqual((e['hours'], e['limit']), (22.2, 'one_repo'))
        e = s.builder_estimate({**WORK3, 'top_repo': 10, 'repos': 1}, RES)            # 1 repo x 3 workers = 3 wide
        self.assertEqual((e['parallel'], e['limit'], e['hours']), (3, 'repos', 32.9))
        e = s.builder_estimate({**WORK3, 'top_repo': 10, 'repos': 2}, RES)            # 2 x 3 = 6 = fit: workers bind
        self.assertEqual((e['parallel'], e['limit']), (6, 'workers'))

    def test_an_older_builder_without_repo_workers_gets_the_default_three(self):
        s = fresh()
        e = s.builder_estimate(WORK0, RES)                                             # no repo_workers in the report
        self.assertEqual((e['repo_workers'], e['hours'], e['limit']), (3, 16.4, 'workers'))
        e = s.builder_estimate({**WORK, 'repo_workers': 2}, RES)                       # a builder still on two
        self.assertEqual((e['repo_workers'], e['hours'], e['limit']), (2, 21.3, 'one_repo'))
        e = s.builder_estimate({**WORK, 'repo_workers': 0}, RES)                       # 0 = not sent
        self.assertEqual(e['repo_workers'], 3)

    def test_repo_workers_rides_the_workload_report(self):
        s = fresh()
        s.builder_status(seen=True, work=json.dumps({k: v for k, v in WORK3.items() if k not in ('at', 'stale')}),
                         res=json.dumps({k: v for k, v in RES.items() if k not in ('got', 'stale')}))
        b = s.builder_status()
        self.assertEqual((b['work']['repo_workers'], b['estimate']['repo_workers']), (3, 3))
        s.builder_status(seen=True, work=json.dumps({k: v for k, v in WORK0.items() if k not in ('at', 'stale')}))
        self.assertEqual(s.builder_status()['work']['repo_workers'], 3)                # missing = default


class Bottlenecks(unittest.TestCase):
    def test_one_repo_row_says_up_to_three(self):
        s = fresh()
        est, out, by = bn(s, {**WORK3, 'top_repo': 50})
        self.assertEqual(out['slowest'], 'Slowest part: wizard-ux. It has 50 of the items; it can get up to 3 workers whenever it holds a big share of the queue.')
        self.assertEqual((by['one_repo']['status'], by['one_repo']['say']),
                         ('limit', 'wizard-ux has 50 of the 74 items; it can get up to 3 workers whenever it holds a big share of the queue.'))
        self.assertEqual(out['help'], 'Nothing right now; the queue is mostly one repo.')
        est, out, by = bn(s, WORK3)                                                    # 32 of 74: tight, not the limit
        self.assertEqual((by['one_repo']['status'], by['one_repo']['say']),
                         ('tight', 'wizard-ux has 32 of the 74 items; it can get up to 3 workers whenever it holds a big share of the queue.'))
        est, out, by = bn(s, {**WORK3, 'repos': 1, 'top_repo': 10})
        self.assertEqual(by['one_repo']['say'], 'Only 1 repos have work, and a repo holds 3 workers at most.')
        self.assertEqual(out['slowest'], 'Slowest part: only 1 repos have work, and a repo holds 3 workers at most.')
        est, out, by = bn(s, {**WORK, 'repo_workers': 2, 'top_repo': 50})            # a builder still on two says two
        self.assertIn('it can get up to 2 workers', by['one_repo']['say'])

    def test_a_bigger_server_is_the_help_when_the_server_is_tight_and_one_repo_does_not_bind(self):
        s = fresh()
        tight = {**RES, 'verdict': 'watch'}
        est, out, by = bn(s, WORK3, tight)                                             # limit = workers, server tight
        self.assertEqual((est['limit'], by['server']['status'], out['help']), ('workers', 'tight', 'A bigger server (KVM 8).'))
        est, out, by = bn(s, WORK3, {**RES, 'mem_free_p5_mb': 1500})                   # tight for memory: same
        self.assertEqual((by['server']['status'], out['help']), ('tight', 'A bigger server (KVM 8).'))
        est, out, by = bn(s, {**WORK3, 'top_repo': 50}, tight)                         # one repo binds: not the server
        self.assertEqual((est['limit'], by['server']['status'], out['help']), ('one_repo', 'tight', 'Nothing right now; the queue is mostly one repo.'))
        est, out, by = bn(s, {**WORK3, 'repos': 1, 'top_repo': 10}, tight)             # too few repos bind: not the server
        self.assertEqual((est['limit'], out['help']), ('repos', 'Nothing right now; only 1 repos have work.'))
        est, out, by = bn(s, WORK3, RES)                                               # server fine: nothing
        self.assertEqual((by['server']['status'], out['help']), ('fine', 'Nothing right now.'))
        est, out, by = bn(s, WORK3, {**RES, 'held_pct': 23})                           # the limit: as before
        self.assertEqual((by['server']['status'], out['help']), ('limit', 'A bigger server (KVM 8).'))


class Words(unittest.TestCase):
    def test_version_and_tool(self):
        s = fresh()
        self.assertEqual(s.VERSION, '0.63.0')
        d = next(t for t in s.TOOLS if t['name'] == 'builder_status')['description']
        self.assertIn('up to three workers', d); self.assertIn('repo_workers', d)
        self.assertIn('0.58.0', (ROOT / 'skill' / 'SKILL.md').read_text())
        self.assertIn('0.58.0', (ROOT / 'wizard.md').read_text())
        self.assertIn("'repo_workers'", (ROOT / 'app' / 'server.py').read_text().split('WORK_KEYS = ')[1].split('\n')[0])


if __name__ == '__main__':
    unittest.main()
