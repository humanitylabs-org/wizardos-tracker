"""Tracker 0.55.1 (Miguel, 25 Nov 2026): 'WizardOS update failed' on every tap of Try again, for two days, while no
install had started. The box answers a tap made while Wizard is working (a chat reply, a helper agent, a scheduled job)
with started:false + waiting + waiting_for and starts nothing; the Tracker ignored that, then read the box's LAST
failure (it stays until a new install runs) as this tap's result. Now the tap asks: Update when it finishes / Update
anyway; an update that waits says so on the pill (with Cancel); and a run never reports a failure that was already
there before the tap.
Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)
OLD = 'wizard-agent-service: update to release source failed'
QUIET = 'WizardOS updates when Wizard is quiet'
LATER = {'text': 'WizardOS updates later', 'btn': 'Cancel', 'bad': False}   # the pill's short form
FAILED_PILL = {'text': 'WizardOS update failed', 'btn': 'Try again', 'bad': True}


class Source(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in S.VERSION.split('.')), (0, 55, 1))
        self.assertIn('**0.55.1**', (ROOT / 'wizard.md').read_text())

    def test_what_is_sent_is_what_the_app_manager_takes(self):
        # wam/cli.py: {"action": "apply"[, "anyway": true | "when_idle": true]} or {"action": "when_idle_cancel"}
        self.assertIn("STORE_POST({ action: 'apply', ...how })", JS)
        self.assertIn("updateWizardOS(null, item, { anyway: true })", JS)
        self.assertIn("updateWizardOS(null, item, { when_idle: true })", JS)
        self.assertIn("STORE_POST({ action: 'when_idle_cancel' })", JS)

    def test_the_rest_of_the_update_is_as_it_was(self):
        body = JS[JS.index('async function updateWizardOS_'):JS.index('// A WizardOS update restarts Wizard')]
        self.assertIn("Wizard restarts for a moment.`, 'Update', () => {", body)                 # the confirm step
        self.assertIn("store.set('board.osrun', { to: target, from: u.installed, at: r.at, item: item ? item.id : null, old });", body)
        self.assertIn('for (const end = r.at + 25 * 60000; Date.now() < end; await sleep(3000))', body)
        self.assertIn("throw new Error('Still not done after 25 minutes. Check Settings › Updates.');", body)
        self.assertEqual(body.count("e.status === 404 ? 'Update in Settings › Updates.' : e.message"), 2)
        self.assertIn('followOS(r, o.from, o.old)', JS)   # a reload inside the first 90 seconds remembers the old failure too
        self.assertIn('const OS_GRACE_MS = 90000;', JS)

    def test_settings_says_it_waits(self):
        p = JS[JS.index('function paintWizards'):JS.index('// While anything updates, the picture refreshes')]
        self.assertIn("osWaits() ? '· updates when Wizard is quiet ' : ''", p)
        self.assertIn("osWaits() ? smallBtn('Cancel', b => osIdleCancel(b))", p)

    def test_the_pill_stays_one_line_on_a_phone(self):
        # measured at 360px: 'WizardOS update failed' + Try again ends at 348px; the idle pill with Cancel must not be wider
        self.assertIn("const OS_IDLE_PILL = 'WizardOS updates later';", JS)
        self.assertLessEqual(len('WizardOS updates later') + len('Cancel'), len('WizardOS update failed') + len('Try again'))

    def test_no_new_look(self):
        diff_free = (ROOT / 'web' / 'styles.css').read_text()
        self.assertNotIn('0.55.1', diff_free)             # existing popover, buttons, pill and lines only
        ask = JS[JS.index('function osBusyAsk'):JS.index('async function osIdleCancel')]
        for x in ("make('div', 'bd-askrow')", "'bd-mini'", "'bd-mini bd-mini-go'", 'pop(osAnchor(btn)'):
            self.assertIn(x, ask)


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'fixture_0551.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_a_tap_while_wizard_is_busy_asks_and_never_says_failed(self):
        o = self.out
        self.assertEqual(o['before'], FAILED_PILL)                                   # the failure from two days ago
        self.assertEqual(o['confirm'], {'text': 'Update WizardOS 0.3.350 \u2192 0.3.362? Wizard restarts for a moment.', 'btns': ['Cancel', 'Update']})
        b = o['busy']
        self.assertEqual(b['posts'], [{'action': 'apply'}])
        self.assertEqual(b['started'], 0)
        self.assertEqual(b['ask'], {'text': 'Wizard is busy right now: A chat reply, Replying in \u201cMac app trial\u201d, A helper agent and 1 more. '
                                            'Updating WizardOS now would stop that.', 'btns': ['Update anyway', 'Update when it finishes']})
        self.assertIsNone(b['run'])                                                  # no run, so no 'WizardOS didn't update' panel
        self.assertEqual(b['panels'], [])
        self.assertIsNone(b['osrun'])
        self.assertTrue(o['inView'])

    def test_the_question_names_what_it_knows(self):
        self.assertEqual(self.out['askOne'], 'Wizard is busy right now: A chat reply. Updating WizardOS now would stop that.')
        self.assertEqual(self.out['askNone'], 'Wizard is busy right now. Updating WizardOS now would stop that.')

    def test_update_when_it_finishes_queues_it_and_the_pill_says_so(self):
        l = self.out['later']
        self.assertEqual(l['posts'], [{'action': 'apply'}, {'action': 'apply', 'when_idle': True}])
        self.assertEqual(l['started'], 0)
        self.assertEqual(l['pill'], LATER)
        self.assertIsNone(l['run'])
        self.assertEqual(l['panels'], [])
        self.assertEqual(self.out['laterOpen'], {'rows': [['os', 'Cancel']], 'why': QUIET + '.', 'all': None})

    def test_cancel_takes_it_off_the_box(self):
        c = self.out['cancelled']
        self.assertEqual(c['post'], {'action': 'when_idle_cancel'})
        self.assertIsNone(c['waits'])
        self.assertEqual(c['pill'], FAILED_PILL)

    def test_a_page_that_loads_while_it_waits_says_so(self):
        self.assertEqual(self.out['loaded'], LATER)   # never 'update failed · Try again'
        self.assertEqual(self.out['loadedInstalling'], {'waits': False, 'pill': None})

    def test_update_all_leaves_the_waiting_update_alone(self):
        self.assertEqual(self.out['withApp'], {'text': '2 updates ready', 'btn': 'Update', 'bad': False})
        self.assertEqual(self.out['withAppDone'], {'calls': ['a1'], 'posts': []})

    def test_update_all_asks_too_and_does_not_count_wizardos_as_updated(self):
        a = self.out['all']
        self.assertEqual(self.out['allPill'], {'text': '2 updates ready', 'btn': 'Update all', 'bad': False})
        self.assertEqual(a['calls'], ['a1'])
        self.assertEqual(a['posts'], [{'action': 'apply'}])
        self.assertEqual(a['ask'], 'Wizard is busy right now: A chat reply, Replying in \u201cMac app trial\u201d, A helper agent and 1 more. '
                                   'Updating WizardOS now would stop that.')
        self.assertIsNone(a['run'])
        self.assertEqual(a['counted'], ['a1'])                                       # the app, not WizardOS
        self.assertIsNone(a['left'])
        self.assertIsNone(a['failed'])                                               # and nothing 'didn't update'
        self.assertEqual(a['pill'], {'text': 'WizardOS update ready', 'btn': 'Update', 'bad': False})

    def test_update_anyway_starts_it_and_the_old_failure_is_not_this_run(self):
        s, i, d = self.out['anywayStale'], self.out['anywayInstalling'], self.out['anywayDone']
        self.assertEqual(s['posts'], [{'action': 'apply'}, {'action': 'apply', 'anyway': True}])
        self.assertEqual(s['started'], 1)
        self.assertEqual(s['run'], ['running', 'Installing', ''])                    # three answers still carried the old failure
        self.assertEqual(s['panels'], [['os', 'running', None]])
        self.assertIsNone(s['pill'])                                                 # no 'update failed · Try again' beside a running update
        self.assertEqual(s['osrun']['old'], json.dumps([OLD, '0.3.362'], separators=(',', ':')))
        self.assertEqual({k: s['osrun'][k] for k in ('to', 'from', 'item')}, {'to': '0.3.362', 'from': '0.3.350', 'item': None})
        self.assertEqual(i['run'], ['running', 'Installing', ''])                    # an install that runs has not failed
        self.assertEqual(d['run'], ['done', 'Done', ''])
        self.assertIsNone(d['osrun'])

    def test_a_failure_from_before_the_tap_counts_again_after_90_seconds(self):
        self.assertEqual(self.out['graceOver'], [OLD, 1])

    def test_a_run_with_nothing_remembered_fails_as_before(self):
        self.assertEqual(self.out['noMemory'], [OLD, 1])

    def test_a_new_failure_is_reported_at_once(self):
        self.assertEqual(self.out['newReason'], ['Not enough disk space', 1])
        self.assertEqual(self.out['interrupted'], ['The WizardOS update stopped.', 1])
        self.assertEqual(self.out['failedAfterInstalling'], ['running', OLD, True])


if __name__ == '__main__':
    unittest.main()
