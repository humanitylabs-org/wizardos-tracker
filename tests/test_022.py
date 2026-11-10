"""0.22 unit tests: mobile first. One header row (Report or request is the round primary '+', never a tab), the stage
strip on one line, 44px targets and full-height bottom sheets on phones, Update progress in place, the app sheet full
screen with Close first, and Try it as the first control beside Open <app>.
Run: python3 -m unittest discover -s tests"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import S

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
HTML = (ROOT / 'web/index.html').read_text()
CSS = (ROOT / 'web/styles.css').read_text()
PHONE = CSS[CSS.index('0.22 mobile first'):]


def phone_rules():
    m = re.search(r'@media \(max-width: 599px\) \{(.*)\n\}\n@media \(max-width: 360px\)', PHONE, re.S)
    return m.group(1)


class Header(unittest.TestCase):
    def test_one_row(self):
        bar = HTML[HTML.index('<header class="bd-hbar" id="bar">'):HTML.index('</header>')]
        order = [bar.index(x) for x in ('id="goals-btn"', 'role="tablist"', 'id="builder"', 'id="report-open"', 'id="settings-btn"')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('id="acct"', bar, 'the account line lives in Settings')
        self.assertIn('id="acct"', HTML[HTML.index('id="settings"'):])
        self.assertNotIn('bd-head', HTML)
        for short in ('Core', 'Apps', 'Bugs'):
            self.assertIn(f'<span class="bd-tab-s" aria-hidden="true">{short}</span>', bar)

    def test_report_is_a_round_primary_plus(self):
        b = HTML[HTML.index('id="report-open"') - 40:HTML.index('</button>', HTML.index('id="report-open"'))]
        self.assertNotIn('role="tab"', b)
        self.assertIn('aria-label="Report or request"', b)
        self.assertIn('M12 5v14M5 12h14', b)                      # the '+'
        self.assertIn('<span class="bd-rr-t">Report</span>', b)   # '+ Report' on wide screens
        ph = phone_rules()
        rr = re.search(r'\.bd-rr \{([^}]*)\}', ph).group(1)
        for want in ('position: fixed', 'border-radius: 50%', 'width: 56px', 'height: 56px', 'safe-area-inset-bottom', 'right:'):
            self.assertIn(want, rr)

    def test_tools_one_row(self):
        tools = HTML[HTML.index('<div class="bd-tools">'):HTML.index('</div>', HTML.index('<div class="bd-tools">'))]
        for x in ('filter-btn', 'sort-btn', 'stats-btn', 'id="fresh"', 'id="reload"'):
            self.assertIn(x, tools)
        self.assertIn('.bd-tools { flex-wrap: nowrap;', PHONE)


class Phone(unittest.TestCase):
    def test_strip_never_wraps(self):
        ph = phone_rules()
        self.assertRegex(ph, r'\.bd-strip \{[^}]*overflow-x: auto')
        self.assertRegex(ph, r'\.bd-strip \.bd-stepli \{ flex: none;')
        self.assertIn('white-space: nowrap', re.search(r'\.bd-strip \.bd-bin-w \{([^}]*)\}', ph).group(1))
        self.assertIn('sc.scrollLeft', JS, 'the chosen stage scrolls into view')

    def test_targets_44(self):
        ph = phone_rules()
        self.assertRegex(ph, r'\.bd-mini, \.bd-chip, \.bd-tool, \.bd-menu-i, \.bd-acct-act \{ min-height: 44px; \}')
        self.assertRegex(ph, r'\.wz-sheet-x \{ width: 44px; height: 44px;')
        self.assertIn('min-height: 44px', re.search(r'\.bd-try\.bd-try-pill \{([^}]*)\}', PHONE).group(1))

    def test_full_height_bottom_sheets(self):
        ph = phone_rules()
        self.assertRegex(ph, r'\.wz-sheet, \.wz-sheet\.bd-report \{ width: 100%; max-width: 100%; margin: auto 0 0; max-height: calc\(100dvh')
        self.assertIn('env(safe-area-inset-bottom', ph[ph.index('.wz-sheet, .wz-sheet.bd-report'):])
        self.assertRegex(ph, r'#report\.wz-sheet, #detail\.wz-sheet \{ height: calc\(100dvh')

    def test_no_sideways_scroll(self):
        self.assertIn('html, body { overflow-x: hidden; }', PHONE)


class Update(unittest.TestCase):
    def test_steps_elapsed_hint(self):
        self.assertIn("const UPD_STEPS = ['Starting', 'Installing', 'Restarting', 'Done'];", JS)
        for x in ('usually about', 'took ', 'clock(sec)', 'Try again', 'bd-upd-why', 'ONBOX_TEXT.yes'):
            self.assertIn(x, JS)
        self.assertIn("'aria-live', 'polite'", JS[JS.index('function updPanel'):])

    def test_polls_job_then_health(self):
        body = JS[JS.index('async function updateApp'):JS.index('async function updateAll')]
        self.assertLess(body.index("runStep(r, 'Installing'"), body.index("runStep(r, 'Restarting'"))
        self.assertIn("'/healthz'", body)
        self.assertIn('jobDetail(j)', body, 'a step the App Manager does name is shown')
        os_ = JS[JS.index('async function followOS'):]
        self.assertIn('u.failure_reason', os_)
        self.assertIn("store.get('board.osrun')", JS, 'a WizardOS update resumes its progress after Wizard reloads the page')

    def test_card_shows_progress_in_place(self):
        self.assertIn('row.append(updPanel(run, i))', JS)
        self.assertIn("ONBOX_TEXT = { yes: 'On your Wizard ✓'", JS)


class Modal(unittest.TestCase):
    def test_close_first_full_screen(self):
        # 0.23.1: the bar reads title · Try it · Works / Doesn't work · Close (Close at the end, always on row one)
        bar = HTML[HTML.index('<div class="bd-appmodal-bar"'):]
        self.assertLess(bar.index('id="appmodal-h"'), bar.index('id="appmodal-x"'))
        ph = phone_rules()
        self.assertRegex(ph, r'#appmodal\.bd-appmodal \{ width: 100%; max-width: 100%; height: 100dvh;')

    def test_keeps_place_and_works_without_showmodal(self):
        self.assertIn("el('scroll').scrollTop", JS)
        self.assertIn("typeof d.showModal === 'function'", JS)
        self.assertIn('WizardApp.back', JS)
        self.assertIn("document.documentElement.classList.remove('bd-modal-on')", JS)


class TryFirst(unittest.TestCase):
    def test_try_then_open_then_verdict(self):
        body = JS[JS.index("// 0.22: the try flow, in order"):JS.index("if (wait && inDetail) row.append")]
        self.assertLess(body.index('trySwitch(i)'), body.index('Open ${app.name}'))
        self.assertLess(body.index('appToggle(i, swApp, hit)'), body.index('Open ${app.name}'))
        self.assertLess(body.index('Open ${app.name}'), body.index('verdictBtns(i, row, wait)'))
        self.assertIn("make('div', 'bd-trygrp')", body)

    def test_labelled_with_state(self):
        f = JS[JS.index('function tryFace'):JS.index('function trySwitch')]
        self.assertIn("'Try it'", f)
        self.assertIn("on ? 'On' : 'Off'", f)
        self.assertIn("'aria-checked'", f)
        self.assertGreaterEqual(JS.count('tryFace(b, '), 6)
        self.assertNotIn("b.setAttribute('aria-checked', String(", JS.replace(f, ''), 'every toggle goes through tryFace')


class Version(unittest.TestCase):
    def test_version(self):
        self.assertTrue(S.VERSION >= '0.22.0')
        self.assertIn("const PAGE_VERSION = '" + S.VERSION + "'", JS)

    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_js_parses(self):
        subprocess.run(['node', '--check', str(ROOT / 'web/app.js')], check=True)


if __name__ == '__main__':
    unittest.main()
