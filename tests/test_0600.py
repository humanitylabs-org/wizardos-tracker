"""Tracker 0.60.0 (Miguel, 25 Nov 2026): the Builder pop-up said 'Nothing is holding the builder back.' right above its
own rows 'Test boxes: The limit' and 'Waiting longest: The limit'. The one sentence now names every row at the limit,
the most binding first, and 'What would help' matches it. A test box that was stuck (its tester had left without
letting it go) reads as that, not as a reason for another test box.
Run: python3 -m unittest discover -s tests"""
import itertools, os, pathlib, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]

RES = {'at': 1, 'samples': 82, 'hours': 6.8, 'cpus': 4, 'mem_total_mb': 15992, 'workers': 12, 'test_boxes': 2,
       'load_per_cpu_p50': 0.68, 'load_per_cpu_p95': 1.41, 'cpu_saturated_pct': 5, 'cpu_busy_p50': 43.1, 'all_workers_busy_pct': 43,
       'held_pct': 0, 'busy_waits': 0, 'mem_free_p5_mb': 11469, 'disk_used_pct': 61.6, 'test_box_busy_pct': 33, 'tester_wait_pct': 0,
       'worker_min_per_item': 75.6, 'box_h_per_item': 0.18, 'box_h_source': 'guess',
       'workers_enabled': 12, 'workers_fit': 6, 'workers_busy_now': 4, 'doubled_pct': 0, 'workers_doubled_now': 0,
       'job_load': 0.59, 'job_mem_mb': 535,
       'verdict': 'fine', 'test_box_verdict': 'fine', 'reasons': [], 'got': 1, 'stale': False}
WORK = {'pool': 152, 'bugs': 40, 'features': 112, 'held': 0, 'passed24': 114, 'running': 4, 'repos': 15, 'top_repo': 30,
        'top_name': 'wizard-ux', 'at': 1, 'stale': False, 'repo_workers': 3}
LATE = {'waiting': 78, 'oldest_h': 192, 'over_day': 47}          # Waiting longest: the limit
BOXES = {'test_box_verdict': 'add', 'test_box_busy_pct': 57, 'tester_wait_pct': 24}   # Test boxes: the limit
SERVER = {'verdict': 'upgrade', 'held_pct': 21}                  # Server: the limit
NOTHING = 'Nothing is holding the builder back.'


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server
    importlib.reload(server)
    return server


def rows(s, work=WORK, res=RES):
    est = s.builder_estimate(work, res)
    out = s.builder_bottlenecks(work, res, est)
    return out, {r['key']: r for r in out['rows']}


class OneSentence(unittest.TestCase):
    def test_the_pop_up_that_contradicted_itself(self):
        s = fresh()
        out, by = rows(s, work={**WORK, **LATE}, res={**RES, **BOXES})
        self.assertEqual((by['test_boxes']['status'], by['waiting']['status'], by['server']['status']), ('limit', 'limit', 'fine'))
        self.assertEqual(out['slowest'], 'Slowest part: the 2 test boxes. Testers waited for one 24% of the time. '
                                         '47 of 78 items have waited more than a day.')
        self.assertEqual(out['help'], 'Another test box.')

    def test_several_at_the_limit_most_binding_first(self):
        s = fresh()
        out, by = rows(s, work={**WORK, **LATE}, res={**RES, **BOXES, **SERVER})
        self.assertEqual(out['slowest'], 'Slowest part: the server. Jobs are held for resources 21% of the time. '
                                         'Also at the limit: the 2 test boxes. 47 of 78 items have waited more than a day.')
        self.assertEqual(out['help'], 'A bigger server (KVM 8). Another test box.')
        far = __import__('time').time() + 5 * 86400
        out, by = rows(s, work={**WORK, **LATE, 'held': 200},
                       res={**RES, **BOXES, **SERVER, 'quota_used_pct': 88, 'quota_pct_per_hour': 3, 'quota_hours_left': 4, 'quota_resets_at': far})
        self.assertTrue(out['slowest'].startswith('Slowest part: the Claude allowance. New features are on hold until it resets'), out['slowest'])
        self.assertTrue(out['slowest'].endswith('Also at the limit: the server, the 2 test boxes and a yes or no from a person. '
                                                '47 of 78 items have waited more than a day.'), out['slowest'])
        self.assertEqual(out['help'], 'Another Claude subscription for the builder, or a slower pace. A bigger server (KVM 8). '
                                      'Another test box. A yes or no on the 200 items waiting.')

    def test_what_bounds_the_estimate_comes_before_the_server(self):
        s = fresh()
        out, by = rows(s, work={**WORK, 'top_repo': 140}, res={**RES, **SERVER})
        self.assertEqual(by['one_repo']['status'], 'limit')
        self.assertEqual(out['slowest'], 'Slowest part: wizard-ux. It has 140 of the items; it can get up to 3 workers whenever it holds '
                                         'a big share of the queue. Also at the limit: the server.')
        self.assertEqual(out['help'], 'A bigger server (KVM 8).')

    def test_only_the_wait_is_at_the_limit(self):
        s = fresh()
        out, by = rows(s, work={**WORK, **LATE})
        self.assertEqual([k for k, r in by.items() if r['status'] == 'limit'], ['waiting'])
        self.assertEqual(out['slowest'], 'Items wait too long: 47 of 78 have waited more than a day. No single part is at its limit.')
        self.assertEqual(out['help'], 'Nothing to add right now: no single part is at its limit.')
        out, by = rows(s, work={**WORK, **LATE}, res={**RES, 'verdict': 'watch', 'test_box_verdict': 'watch'})
        self.assertEqual(out['slowest'], 'Items wait too long: 47 of 78 have waited more than a day. No single part is at its '
                                         'limit; the closest: the server, the 2 test boxes and the workers.')
        self.assertEqual(out['help'], 'A bigger server (KVM 8).')
        out, by = rows(s, work={**WORK, **LATE, 'top_repo': 65})     # one repo holds 43% of the queue: tight, named by its name
        self.assertEqual(by['one_repo']['status'], 'tight')
        self.assertTrue(out['slowest'].endswith('No single part is at its limit; the closest: wizard-ux.'), out['slowest'])

    def test_people_at_the_limit_are_named(self):
        s = fresh()
        out, by = rows(s, work={**WORK, 'held': 160})
        self.assertEqual(by['people']['status'], 'limit')
        self.assertEqual(out['slowest'], 'Slowest part: a yes or no from a person. 160 finished items wait for one.')
        self.assertEqual(out['help'], 'A yes or no on the 160 items waiting.')
        out, by = rows(s, work={**WORK, 'pool': 0, 'top_repo': 0, 'held': 3})
        self.assertEqual(out['slowest'], 'Nothing to build right now. 3 finished items wait for a yes or no.')

    def test_nothing_at_the_limit_still_reads_as_before(self):
        s = fresh()
        out, by = rows(s)
        self.assertFalse([r for r in out['rows'] if r['status'] == 'limit'])
        self.assertEqual((out['slowest'], out['help']), (NOTHING, 'Nothing right now.'))
        out, _ = rows(s, work={**WORK, 'waiting': 30, 'oldest_h': 20, 'over_day': 0})
        self.assertEqual(out['slowest'], NOTHING)

    def test_never_nothing_while_a_row_is_at_the_limit(self):
        s = fresh()
        names = {'server': 'the server', 'test_boxes': 'test boxes', 'waiting': 'waited more than a day', 'people': 'yes or no',
                 'one_repo': 'wizard-ux', 'allowance': 'Claude allowance', 'workers': 'workers'}
        far = __import__('time').time() + 5 * 86400
        parts = [({}, SERVER, {'verdict': 'watch'}), ({}, BOXES, {'test_box_verdict': 'watch'}),
                 ({}, {'quota_used_pct': 90, 'quota_pct_per_hour': 3, 'quota_hours_left': 3, 'quota_resets_at': far})]
        works = [({}, LATE), ({}, {'held': 200}, {'held': 6}), ({}, {'top_repo': 140})]
        seen = 0
        for res_bits in itertools.product(*parts):
            for work_bits in itertools.product(*works):
                res, work = dict(RES), dict(WORK)
                for b in res_bits:
                    res.update(b)
                for b in work_bits:
                    work.update(b)
                out, by = rows(s, work=work, res=res)
                at = [k for k, r in by.items() if r['status'] == 'limit']
                if at:
                    seen += 1
                    self.assertNotIn('Nothing is holding', out['slowest'], (at, out['slowest']))
                    for k in at:
                        self.assertIn(names[k], out['slowest'], (k, out['slowest']))
                else:
                    self.assertEqual(out['slowest'], NOTHING)
                if by['test_boxes']['status'] == 'limit':
                    self.assertIn('Another test box.', out['help'])
                if by['server']['status'] == 'limit':
                    self.assertIn('A bigger server (KVM 8).', out['help'])
        self.assertGreater(seen, 100)


class StuckTestBox(unittest.TestCase):
    def test_a_box_that_was_stuck_is_not_a_reason_for_another_box(self):
        s = fresh()
        # the builder took the stuck time out of tester_wait_pct, so its verdict is fine again; the row says what happened
        out, by = rows(s, res={**RES, 'tester_wait_pct': 2, 'tester_wait_any_pct': 24, 'test_box_leaks': 1, 'test_box_leak_min': 139,
                               'test_box_leak_pct': 28, 'test_box_leak_last': 1795617900, 'test_boxes_leaked_now': 0})
        self.assertEqual(by['test_boxes']['status'], 'fine')
        self.assertEqual(by['test_boxes']['say'], 'In use 33% of the time; testers waited for one 2% of the time. '
                                                  'A test box was stuck once this week (2 h 19 min in all); that time is not counted here.')
        self.assertNotIn('Another test box', out['help'])
        self.assertEqual(out['slowest'], NOTHING)
        _, by = rows(s, res={**RES, 'test_box_leaks': 3, 'test_box_leak_min': 45})
        self.assertIn('A test box was stuck 3 times this week (45 min in all)', by['test_boxes']['say'])

    def test_a_box_stuck_right_now(self):
        s = fresh()
        out, by = rows(s, res={**RES, 'test_boxes_leaked_now': 1, 'test_box_leaks': 2, 'test_box_leak_min': 30})
        self.assertEqual(by['test_boxes']['status'], 'tight')
        self.assertEqual(by['test_boxes']['say'], 'One is stuck right now: a tester left without letting it go, and the builder '
                                                  'frees it within minutes. In use 33% of the time; testers never waited for one.')
        self.assertNotIn('Another test box', out['help'])

    def test_real_waiting_still_asks_for_a_box(self):
        s = fresh()
        out, by = rows(s, res={**RES, **BOXES, 'test_box_leaks': 1, 'test_box_leak_min': 139})
        self.assertEqual(by['test_boxes']['status'], 'limit')
        self.assertIn('Another test box.', out['help'])

    def test_an_older_builder_reads_as_before(self):
        s = fresh()
        _, by = rows(s)
        self.assertEqual(by['test_boxes']['say'], 'In use 33% of the time; testers never waited for one.')

    def test_the_fields_pass_the_cleaner(self):
        s = fresh()
        import json
        got = s._res_clean(json.dumps({**RES, 'tester_wait_any_pct': 24, 'test_box_leak_pct': 28, 'test_box_leaks': 1,
                                       'test_box_leak_min': 139, 'test_box_leak_last': 1795617900, 'test_boxes_leaked_now': 0,
                                       'test_box_leak_note': '<b>no</b>'}))
        self.assertEqual([got[k] for k in ('tester_wait_any_pct', 'test_box_leak_pct', 'test_box_leaks', 'test_box_leak_min',
                                           'test_box_leak_last', 'test_boxes_leaked_now')], [24, 28, 1, 139, 1795617900, 0])
        self.assertNotIn('test_box_leak_note', got)


class Versions(unittest.TestCase):
    def test_version(self):
        self.assertIn("VERSION = '0.61.0'", (ROOT / 'app/server.py').read_text())
        self.assertIn('**0.60.0**', (ROOT / 'wizard.md').read_text())


if __name__ == '__main__':
    unittest.main()
