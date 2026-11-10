"""Tracker 0.23.1: the whole human check inside the app pop-up; Doesn't work always asks what's wrong."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
HTML = (ROOT / 'web' / 'index.html').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402


def fn(name):
    a = JS.index('function ' + name + '(')
    b = JS.index('\nfunction ', a + 10)
    return JS[a:b]


class Version(unittest.TestCase):
    def test_version(self):
        self.assertTrue(S.VERSION >= '0.23.1')
        self.assertIn("PAGE_VERSION = '" + S.VERSION + "'", JS)
        self.assertIn("version: '" + S.VERSION + "'", JS)
        self.assertIn('version: ' + S.VERSION, (ROOT / 'wizard.md').read_text())
        self.assertIn('"version": "' + S.VERSION + '"', (ROOT / 'runtipi' / 'config.json').read_text())


class PopupBar(unittest.TestCase):
    def test_bar_has_title_toggle_verdict_and_close(self):
        bar = HTML[HTML.index('<div class="bd-appmodal-bar" id="appmodal-bar">'):HTML.index('<iframe id="appmodal-f"')]
        order = [bar.index(x) for x in ('id="appmodal-h"', 'id="appmodal-try"', 'id="appmodal-acts"', 'id="appmodal-x"')]
        self.assertEqual(order, sorted(order))

    def test_open_carries_the_item(self):
        self.assertIn('async function openApp(id, name, btn, item)', JS)
        self.assertIn('openApp(app.id, app.name, b, i)', JS)
        self.assertNotRegex(JS, r'openApp\(app\.id, app\.name, b\)')

    def test_bar_uses_the_cards_toggle_and_buttons(self):
        mb = fn('modalBar')
        self.assertIn('it.title', mb)
        self.assertIn('tryToggle(it)', mb)
        self.assertIn("verdictBtns(it, el('appmodal-bar'), tryState(it).wait)", mb)
        # the card uses the very same pieces
        aa = fn('actionArea')
        self.assertIn('tryState(i)', aa)
        self.assertIn('verdictBtns(i, row, wait)', aa)

    def test_flip_rebuilds_bar_and_reloads_frame(self):
        self.assertEqual(JS.count('flipped();'), 2)   # core catalog switch and app switch
        fl = fn('flipped')
        self.assertIn('modalBar()', fl)
        self.assertIn('reloadFrame()', fl)
        self.assertIn('contentWindow.location.reload()', fn('reloadFrame'))

    def test_verdict_from_popup_closes_it(self):
        self.assertIn("if (el('appmodal').open) closeApp();", fn('afterAct'))

    def test_phone_two_rows_toggle_and_close_on_row_one(self):
        self.assertIn('grid-template-areas: "h try x" "acts acts tab"', CSS)
        self.assertIn('grid-template-columns: minmax(0, 1fr) auto auto', CSS)
        self.assertRegex(CSS, r'\.bd-appmodal-h \{[^}]*text-overflow: ellipsis')


class NoteRequired(unittest.TestCase):
    def test_every_doesnt_work_uses_the_required_note(self):
        self.assertNotIn("What went wrong? (optional)", JS)
        self.assertEqual(len(re.findall(r"smallBtn\('Doesn’t work', b => doesntWork\(", JS)), 2)
        self.assertIn('required: true', fn('doesntWork'))
        self.assertIn("label: 'What’s wrong?'", JS)
        self.assertIn('Swiping feels choppy, it should glide one day at a time', JS)

    def test_send_disabled_until_text(self):
        na = fn('noteAsk')
        self.assertIn('go.disabled = !ta.value.trim()', na)
        self.assertIn('if (opt.required && !note)', na)

    def test_server_refuses_empty_note(self):
        with self.assertRaises(S.Problem) as e:
            orig = S.account_for
            S.account_for = lambda p: (p, {'token': 't', 'login': 'x'})
            try:
                S.tested('x', {'repo': 'humanitylabs-org/wizard-calendar', 'number': 20, 'note': '   '}, False)
            finally:
                S.account_for = orig
        self.assertEqual((e.exception.code, e.exception.reason), (400, 'note_required'))


if __name__ == '__main__':
    unittest.main()
