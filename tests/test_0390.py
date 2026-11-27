"""0.39.0 (Miguel, 18 Nov): updates that run at the same time wait for each other instead of failing, one picture of
every app's update state, and Waiting on me (one place for everything that waits on you)."""
import unittest

from test_036 import JS, run, ok, app, UPD, JOB


class Concurrent(unittest.TestCase):
    def test_409_already_running_waits_then_posts_once_more(self):
        """Another update of the same app holds it (the automatic run, another device): wait, then update."""
        out = run([app()], {
            UPD: [{'http': 409, 'body': {'error': 'another release operation is already running for this app'}},
                  ok({'app': 'messenger', 'state': 'installing'})],
            JOB: [{'body': {'state': 'installed', 'status': 'running'}}],
        })
        self.assertEqual(out['state'], 'done', out)
        self.assertEqual(sum(c.startswith('POST') for c in out['calls']), 2, out['calls'])
        self.assertIn('Waiting', out['trail'])

    def test_box_already_updating_it_is_followed_not_posted_on_top(self):
        """The other update finishes the job: the app is current, so no second update is sent."""
        a = app(status='updating')
        out = run([a], {
            'GET /wizard-os-home/store-install/messenger': [ok({'state': 'installed'})],
        })
        # busy status at first, then the harness's catalog keeps 'updating'; the run must not POST an update on top
        self.assertFalse(any(c.startswith('POST /wizard-os-home/store-install/messenger') for c in out['calls']), out)


class Picture(unittest.TestCase):
    def test_every_app_has_one_state_in_named_groups(self):
        for g in ("['updating', 'Updating now']", "['queued', 'Queued']", "['failed', 'Didn’t update']",
                  "['ready', 'Update ready']", "['stopped', 'Stopped']", "['current', 'Up to date']"):
            self.assertIn(g, JS)
        self.assertIn("getJSON(STORE_INSTALL + '_app-updates')", JS, 'the App Manager’s own run is part of the picture')
        self.assertIn('Automatic updates (', JS)

    def test_a_tap_joins_the_one_queue(self):
        body = JS[JS.index('async function updateApp(id, btn, item)'):]
        self.assertIn('queueStart([{ key: id', body[:800])

    def test_a_late_queue_entry_is_picked_up(self):
        self.assertIn('draining.then(() => (queueOpen() ? drainQueue() : null))', JS)


class WaitingOnMe(unittest.TestCase):
    def test_button_and_view(self):
        from test_036 import ROOT
        html = (ROOT / 'web/index.html').read_text()
        # 0.50.0 (Miguel, 21 Nov): no separate screen; an orange count on the tab and the stage instead
        self.assertNotIn('me-btn', html + JS)
        for k in ('loadMe', 'renderMe', 'Questions for you', 'To approve'):
            self.assertNotIn(k, JS)
        for v in ('core', 'apps', 'bugs', 'goals'):
            self.assertIn(f'<b class="bd-wait-n" data-wait="{v}" hidden></b>', html)
        for k in ("['test', 'To try']", "'Feedback to approve '", "'Updates on this Wizard '"):   # 0.45.0: one place, one count
            self.assertNotIn(k, JS)

    def test_default_view_is_core(self):
        self.assertIn("return TABS.includes(v) ? v : 'core'; } catch (_) { return 'core'; }", JS)


if __name__ == '__main__':
    unittest.main()
