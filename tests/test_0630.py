"""Tracker 0.63.0 (Miguel, 27 Nov 2026): the builder's pace counts working hours only, and the Claude allowance row
names every account in the builder's pool (two spent, one new: the builder is not on hold).
Run: python3 -m unittest discover -s tests"""
import json, os, pathlib, sys, tempfile, time, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = 1795726000   # 26 Nov 20:46 UTC


def fresh():
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    sys.path.insert(0, str(ROOT / 'app'))
    import importlib, server
    importlib.reload(server)
    return server


ACCTS = [{'label': 'b-max', 'used_pct': 5, 'resets_at': NOW + 3 * 3600, 'in_use': True},
         {'label': 'miguel-max', 'used_pct': 99, 'resets_at': NOW + 4 * 86400, 'in_use': False},
         {'label': 'oscar-max', 'used_pct': 91, 'resets_at': NOW + 2 * 86400, 'in_use': False}]


class Accounts(unittest.TestCase):
    def test_accounts_pass_the_clean_up(self):
        s = fresh()
        raw = {'verdict': 'upgrade', 'quota_used_pct': 5.0, 'pace_span_hours': 20.3,
               'quota_accounts': ACCTS + [{'label': 'x', 'used_pct': 'lots'}, 'junk', {'label': 'y' * 99, 'used_pct': 150, 'in_use': 1}]}
        out = s._res_clean(json.dumps(raw))
        self.assertEqual(out['pace_span_hours'], 20.3)
        self.assertEqual([a['label'] for a in out['quota_accounts']], ['b-max', 'miguel-max', 'oscar-max', 'y' * 40])
        self.assertEqual((out['quota_accounts'][3]['used_pct'], out['quota_accounts'][3]['in_use']), (100, False))
        self.assertNotIn('quota_accounts', s._res_clean(json.dumps({'verdict': 'fine', 'quota_accounts': 'no'})))

    def test_two_spent_and_one_new_is_not_a_hold(self):
        s = fresh()
        q = s._allowance({'quota_used_pct': 5.0, 'quota_resets_at': NOW + 3 * 3600, 'quota_accounts': ACCTS}, now=NOW)
        self.assertEqual(q['status'], 'fine')
        self.assertTrue(q['say'].startswith('5% used on the account with the most room'), q['say'])
        self.assertIn('3 accounts: b-max 5% (in use), oscar-max 91% (resets ', q['say'])
        self.assertIn('miguel-max 99% (resets ', q['say'])

    def test_every_account_full_is_the_limit(self):
        s = fresh()
        full = [{**a, 'used_pct': 99, 'in_use': a['label'] == 'oscar-max'} for a in ACCTS]
        q = s._allowance({'quota_used_pct': 99, 'quota_resets_at': NOW + 2 * 86400, 'quota_accounts': full}, now=NOW)
        self.assertEqual(q['status'], 'limit')
        self.assertIn('everything is on hold until the first account resets', q['say'])

    def test_one_account_reads_as_before(self):
        s = fresh()
        q = s._allowance({'quota_used_pct': 40, 'quota_resets_at': NOW + 86400}, now=NOW)
        self.assertEqual(q['say'][:9], '40% used;')


class Pace(unittest.TestCase):
    def test_the_estimate_carries_the_clock_hours(self):
        s = fresh()
        work = {'pool': 71, 'repos': 8, 'top_repo': 38, 'top_name': 'wizard-ux', 'repo_workers': 3}
        res = {'workers': 12, 'worker_min_per_item': 72.6, 'workers_fit': 6, 'test_boxes': 2, 'box_h_per_item': 0.18,
               'pace_items_per_h': 3.3, 'pace_worker_h_per_item': 1.39, 'pace_hours': 12.0, 'pace_span_hours': 20.3}
        est = s.builder_estimate(work, res)
        self.assertEqual((est['source'], est['pace_hours'], est['pace_span_hours']), ('pace', 12.0, 20.3))
        self.assertAlmostEqual(est['hours'], 21.5, delta=0.1)

    def test_the_page_says_working_hours(self):
        self.assertIn('working h)`, est.pace_per_h)', (ROOT / 'web/app.js').read_text())


if __name__ == '__main__':
    unittest.main()
