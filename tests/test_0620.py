"""Tracker 0.62.0 (Miguel, 26 Nov 2026): the queue estimate uses the builder's measured pace (items its tester passed
per hour over the last 12 h), never less than the busiest repo's items in series at the measured worker time per item.
The 7-day model said about 4 items an hour (23 h for 93 items) while the builder did 7-8.
Run: python3 -m unittest discover -s tests"""
import os, pathlib, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]

# the live numbers of 26 Nov 01:20 UTC (work.json and resources.json on the builder host)
WORK = {'pool': 93, 'bugs': 4, 'features': 89, 'held': 0, 'passed24': 142, 'running': 4, 'repos': 7, 'top_repo': 56,
        'top_name': 'wizard-ux', 'repo_workers': 3, 'at': 1, 'stale': False}
RES = {'at': 1, 'samples': 201, 'hours': 16.8, 'cpus': 4, 'workers': 12, 'test_boxes': 2, 'worker_min_per_item': 74.7,
       'box_h_per_item': 0.18, 'workers_enabled': 12, 'workers_fit': 5, 'workers_busy_now': 5, 'held_pct': 28,
       'verdict': 'upgrade', 'test_box_verdict': 'fine', 'reasons': [], 'got': 1, 'stale': False}


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server
    importlib.reload(server)
    return server


class Pace(unittest.TestCase):
    def test_without_a_pace_the_old_model_stays(self):
        s = fresh()
        est = s.builder_estimate(WORK, RES)
        self.assertEqual((est['source'], est['pace_per_h'], est['limit']), ('model', None, 'one_repo'))
        self.assertAlmostEqual(est['hours'], round(56 * 74.7 / 60 / 3, 1))               # 23.2 h

    def test_the_measured_pace_sets_the_hours(self):
        s = fresh()
        res = {**RES, 'pace_items_per_h': 7.5, 'pace_jobs': 5.0, 'pace_worker_h_per_item': 0.67, 'pace_hours': 12}
        est = s.builder_estimate({**WORK, 'top_repo': 20}, res)
        self.assertEqual((est['source'], est['pace_per_h'], est['pace_hours'], est['hours']), ('pace', 7.5, 12, 12.4))
        self.assertEqual(est['per_day'], 180.0)
        self.assertNotEqual(est['limit'], 'one_repo')

    def test_the_one_repo_floor_is_still_a_lower_bound(self):
        s = fresh()
        res = {**RES, 'pace_items_per_h': 7.5, 'pace_worker_h_per_item': 0.93, 'pace_hours': 12}
        est = s.builder_estimate(WORK, res)                                            # 56 x 0.93 / 3 = 17.4 h > 93 / 7.5
        self.assertEqual((est['source'], est['limit'], est['hours']), ('pace', 'one_repo', 17.4))

    def test_a_pace_of_nothing_falls_back(self):
        s = fresh()
        for bad in ({'pace_items_per_h': 0, 'pace_worker_h_per_item': 0.5}, {'pace_items_per_h': None},
                    {'pace_items_per_h': 5.0}):
            self.assertEqual(s.builder_estimate(WORK, {**RES, **bad})['source'], 'model', bad)

    def test_the_pace_fields_come_through_from_the_builder(self):
        s = fresh()
        import json
        out = s._res_clean(json.dumps({**RES, 'pace_items_per_h': 5.7, 'pace_jobs': 5.3, 'pace_worker_h_per_item': 0.93,
                                       'pace_hours': 12}))
        self.assertEqual((out['pace_items_per_h'], out['pace_jobs'], out['pace_worker_h_per_item'], out['pace_hours']),
                         (5.7, 5.3, 0.93, 12))

    def test_popup_row_and_version(self):
        s = fresh()
        js = (ROOT / 'web/app.js').read_text()
        self.assertIn("est && est.source === 'pace' && row(`Done per hour (last ${Math.round(est.pace_hours || 12)} h)`, est.pace_per_h)", js)
        self.assertEqual(s.VERSION, '0.62.0')
        self.assertIn("const PAGE_VERSION = '0.62.0';", js)


if __name__ == '__main__':
    unittest.main()
