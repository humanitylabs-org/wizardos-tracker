"""Tracker 0.30.0 (Robert's call, 11 Nov): Needs changes (features) / Still broken (bugs) instead of Doesn't work;
Pending approval always shown. Run: python3 -m unittest discover -s tests"""
import json
import unittest
from pathlib import Path

from test_013 import S

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
FS = (ROOT / 'web/feedback-stage.js').read_text()


class Words(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 30, 0))
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], S.VERSION)

    def test_buttons(self):
        self.assertIn("? 'Still broken' : 'Needs changes'", JS)
        self.assertNotIn("'Doesn’t work'", JS)

    def test_reset_reads_old_and_new(self):
        for t in ("Tested: doesn't work — @x", 'Tested: needs changes — @x', 'Tested: still broken — @x'):
            self.assertTrue(S.RESET.match(t), t)

    def test_pending_always_shown(self):
        self.assertNotIn('if (!forView(v).length) return list;', FS)


if __name__ == '__main__':
    unittest.main()
