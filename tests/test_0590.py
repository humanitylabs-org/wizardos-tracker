"""Tracker 0.59.0 (Miguel, 25 Nov 2026): the Builder folds related queued asks of one repo into one item before it
builds. A folded item ('Folded into #N', label folded, closed as not planned) is not done, not shipped and not declined;
the item it was folded into lists its asks. The Builder pop-up gets two rows: Waiting longest and Claude allowance.
Run: python3 -m unittest discover -s tests"""
import calendar, json, os, pathlib, sys, tempfile, time, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
APPJS = (ROOT / 'web/app.js').read_text()
SRC = (ROOT / 'app/server.py').read_text()

RES = {'at': 1, 'samples': 40, 'hours': 3.3, 'cpus': 4, 'mem_total_mb': 15992, 'workers': 12, 'test_boxes': 2,
       'load_per_cpu_p50': 0.4, 'load_per_cpu_p95': 0.9, 'cpu_saturated_pct': 0, 'cpu_busy_p50': 43.2, 'all_workers_busy_pct': 0,
       'held_pct': 0, 'busy_waits': 0, 'mem_free_p5_mb': 13000, 'disk_used_pct': 45, 'test_box_busy_pct': 33, 'tester_wait_pct': 0,
       'worker_min_per_item': 80, 'box_h_per_item': 0.18, 'box_h_source': 'guess',
       'workers_enabled': 12, 'workers_fit': 6, 'workers_busy_now': 5, 'doubled_pct': 10, 'workers_doubled_now': 2,
       'job_load': 0.6, 'job_mem_mb': 800,
       'verdict': 'fine', 'test_box_verdict': 'fine', 'reasons': [], 'got': 1, 'stale': False}
WORK = {'pool': 74, 'bugs': 20, 'features': 54, 'held': 0, 'passed24': 56, 'running': 5, 'repos': 11, 'top_repo': 12,
        'top_name': 'wizard-ux', 'at': 1, 'stale': False, 'repo_workers': 3}
NOW = calendar.timegm((2026, 11, 25, 5, 0, 0))
RESET = calendar.timegm((2026, 11, 30, 5, 0, 0))   # a Monday

# exactly what the builder writes (wizardos-builder bin/builder-groom, fold_text)
HOME_BODY = """## What to build
The agent inbox shows what needs the owner, per agent.

## Asks
- [x] 1. Agent inbox: unread count per agent (this item, filed by Miguel) <!-- groom:ask 40 -->
- [ ] 2. Agent inbox: mark all read (#44, filed by Miguel) <!-- groom:ask 44 -->
- [ ] 3. Agent inbox: sort by newest (#51, filed by Miguel) <!-- groom:ask 51 -->

_3 related asks, built and decided together as one item. Nothing was dropped: each ask's own words are below. To take one out again, reopen its item._

<!-- groom:home v1 -->

## Each ask in its own words

<!-- groom:text 40 -->
<details><summary>1. Agent inbox: unread count per agent</summary>

Show the count.
- [ ] a tick box inside an ask's own words is not an ask

</details>
<!-- groom:end 40 -->
"""


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


class Folded(unittest.TestCase):
    def test_a_home_item_lists_its_asks(self):
        s = fresh()
        asks = s.asks_of(HOME_BODY)
        self.assertEqual([(a['number'], a['done']) for a in asks], [(40, True), (44, False), (51, False)])
        self.assertEqual(asks[0]['text'], 'Agent inbox: unread count per agent (this item, filed by Miguel)')
        tasks = s.tasks_of(HOME_BODY)   # its Done-list is the asks, not the tick boxes inside an ask's own words
        self.assertEqual((len(tasks), sum(t['done'] for t in tasks)), (3, 1))

    def test_any_other_item_is_untouched(self):
        s = fresh()
        body = '- [x] one\n- [ ] two <!-- groom:ask 9 -->'
        self.assertEqual(s.asks_of(body), [])
        self.assertEqual(len(s.tasks_of(body)), 2)

    def test_folded_into_reads_the_builders_comment(self):
        s = fresh()
        bot = {'author': {'login': 'wizardos-builder[bot]'}}
        text = 'so it is built together with related asks. Nothing was dropped. Reopen this item to split it back out.'
        cs = [{**bot, 'body': f'Folded into #40 {text}'}, {'author': {'login': 'mistermizel'}, 'body': 'Folded into #99'}]
        self.assertEqual(s.folded_into(['feature', 'folded'], cs), 40)       # only the builder's word counts
        self.assertEqual(s.folded_into(['feature', 'Folded'], cs + [{**bot, 'body': f'Folded into #41 {text}'}]), 41)   # the newest
        self.assertEqual(s.folded_into(['feature', 'folded'], []), 0)
        self.assertIsNone(s.folded_into(['feature'], cs))                    # not folded: the comment alone says nothing
        self.assertEqual((s.folded_text(40), s.folded_text(0)), ('Folded into #40', 'Folded into another item'))

    def test_a_folded_item_is_not_shipped_and_not_declined(self):
        s = fresh()
        sh = s.ship_status('t', 'o/r#44', [], [], 'closed', 'not_planned', ['feature', 'folded'])
        self.assertEqual((sh['text'], sh.get('folded'), sh['version']), ('Folded into another item', True, None))
        self.assertEqual(s.ship_status('t', 'o/r#45', [], [], 'closed', 'not_planned', ['feature'])['text'], 'Closed: not planned')

    def test_the_done_list_and_the_stats_leave_folded_items_out(self):
        self.assertIn("is:issue is:closed {VIEW_Q[view]} -label:{FOLDED_LABEL} sort:updated-desc", SRC)
        self.assertIn("is:issue {kind} -label:{FOLDED_LABEL} sort:created-desc", SRC)
        self.assertIn("'count': sum(1 for i in items if not i.get('folded'))", SRC)
        self.assertIn("if view != 'goals':", SRC[SRC.index('-label:{FOLDED_LABEL} sort:updated-desc'):][:400])   # the Goals board is not part of it

    def test_the_page_shows_folded_into_and_does_not_count_it(self):
        self.assertIn("const notFolded = l => l.filter(i => !i.folded).length;", APPJS)
        self.assertEqual(APPJS.count('notFolded(l), 0)'), 2)                     # both stage strips
        self.assertIn("String(notFolded(list))", APPJS)                          # the section's number
        self.assertIn("if (g === 'done' && i.folded) return [i.ship.text, ''];", APPJS)
        self.assertIn("if (i.asks > 1) c.append(make('p', 'bd-hint', `${i.asks} asks, built together`));", APPJS)

    def test_no_goal_wording_for_folding(self):
        for line in SRC.splitlines():
            if 'fold' in line.lower() and 'goal' in line.lower():
                self.assertTrue("view != 'goals'" in line or 'Goals board' in line or "view == 'goals'" in line, line)


class WaitingLongest(unittest.TestCase):
    def test_hidden_until_the_builder_reports_it(self):
        s = fresh()
        self.assertNotIn('waiting', rows(s)[1])
        self.assertNotIn('allowance', rows(s)[1])

    def test_fine_tight_and_the_limit(self):
        s = fresh()
        r = rows(s, {**WORK, 'waiting': 40, 'oldest_h': 9, 'over_day': 0})[1]['waiting']
        self.assertEqual((r['name'], r['status'], r['say']), ('Waiting longest', 'fine', 'The oldest item waiting to be built has waited 9 h; nothing has waited more than a day.'))
        r = rows(s, {**WORK, 'waiting': 40, 'oldest_h': 31, 'over_day': 2})[1]['waiting']
        self.assertEqual((r['status'], r['say']), ('tight', 'The oldest item waiting to be built has waited 31 h; 2 of 40 have waited more than a day.'))
        r = rows(s, {**WORK, 'waiting': 73, 'oldest_h': 187, 'over_day': 48})[1]['waiting']
        self.assertEqual((r['status'], r['say']), ('limit', 'The oldest item waiting to be built has waited 8 days; 48 of 73 have waited more than a day.'))
        self.assertEqual(rows(s, {**WORK, 'waiting': 4, 'oldest_h': 30, 'over_day': 1})[1]['waiting']['say'],
                         'The oldest item waiting to be built has waited 30 h; 1 of 4 has waited more than a day.')
        self.assertEqual(rows(s, {**WORK, 'waiting': 4, 'oldest_h': 60, 'over_day': 3})[1]['waiting']['status'], 'limit')   # most of a small queue
        self.assertEqual(rows(s, {**WORK, 'waiting': 0, 'oldest_h': 0, 'over_day': 0})[1]['waiting']['say'], 'Nothing is waiting to be built.')

    def test_the_numbers_pass_the_cleaner(self):
        s = fresh()
        s.builder_status(seen=True, work=json.dumps({**WORK, 'waiting': 73, 'oldest_h': 187, 'over_day': 48}))
        w = s.builder_status()['work']
        self.assertEqual((w['waiting'], w['oldest_h'], w['over_day']), (73, 187, 48))
        s.builder_status(seen=True, work=json.dumps(WORK))            # an older builder: no row, no zeros made up
        self.assertNotIn('oldest_h', s.builder_status()['work'])


class Allowance(unittest.TestCase):
    def q(self, s, used, left=None, resets=RESET, per=3.2):
        return s._allowance({'quota_used_pct': used, 'quota_pct_per_hour': per, 'quota_hours_left': left, 'quota_resets_at': resets}, now=NOW)

    def test_hidden_without_the_fields(self):
        s = fresh()
        self.assertIsNone(s._allowance(RES, now=NOW))
        self.assertIsNone(s._allowance(None))

    def test_tight_when_it_runs_out_before_it_resets(self):
        s = fresh()
        q = self.q(s, 45, 14)
        self.assertEqual((q['status'], q['say']), ('tight', '45% used, at this pace it runs out in about 14 h; resets Mon 30 Nov.'))

    def test_fine_when_it_lasts(self):
        s = fresh()
        q = self.q(s, 20, 400)
        self.assertEqual((q['status'], q['say']), ('fine', '20% used; at this pace it lasts until it resets Mon 30 Nov.'))
        self.assertEqual(self.q(s, 20, None)['say'], '20% used; resets Mon 30 Nov.')
        self.assertEqual(self.q(s, 20, None, resets=None)['say'], '20% used.')

    def test_the_limit_when_work_is_on_hold(self):
        s = fresh()
        q = self.q(s, 86, 3)
        self.assertEqual((q['status'], q['say']), ('limit', '86% used: new features are on hold until it resets Mon 30 Nov.'))
        q = self.q(s, 96, 1)
        self.assertEqual((q['status'], q['say']), ('limit', '96% used: everything is on hold until it resets Mon 30 Nov.'))

    def test_the_row_the_slowest_part_and_what_would_help(self):
        s = fresh()
        far = time.time() + 5 * 86400
        out, by = rows(s, res={**RES, 'quota_used_pct': 45, 'quota_pct_per_hour': 3.2, 'quota_hours_left': 14, 'quota_resets_at': far})
        self.assertEqual((by['allowance']['name'], by['allowance']['status']), ('Claude allowance', 'tight'))
        self.assertNotIn('Claude subscription', out['help'])
        out, by = rows(s, res={**RES, 'quota_used_pct': 88, 'quota_pct_per_hour': 3.2, 'quota_hours_left': 4, 'quota_resets_at': far})
        self.assertEqual(by['allowance']['status'], 'limit')
        self.assertTrue(out['slowest'].startswith('Slowest part: the Claude allowance. New features are on hold until it resets'), out['slowest'])
        self.assertTrue(out['help'].startswith('Another Claude subscription for the builder, or a slower pace.'), out['help'])
        self.assertEqual([r['key'] for r in out['rows']][-1], 'allowance')

    def test_the_fields_pass_the_cleaner(self):
        s = fresh()
        res = {k: v for k, v in RES.items() if k not in ('got', 'stale')}
        s.builder_status(seen=True, work=json.dumps(WORK), res=json.dumps({**res, 'quota_used_pct': 45, 'quota_pct_per_hour': 3.2, 'quota_hours_left': 14, 'quota_resets_at': RESET}))
        sv = s.builder_status()['server']
        self.assertEqual((sv['quota_used_pct'], sv['quota_pct_per_hour'], sv['quota_hours_left'], sv['quota_resets_at']), (45, 3.2, 14, RESET))


class Versions(unittest.TestCase):
    def test_version(self):
        s = fresh()
        self.assertEqual(s.VERSION, '0.64.0')
        self.assertIn("const PAGE_VERSION = '0.64.0';", APPJS)


if __name__ == '__main__':
    unittest.main()
