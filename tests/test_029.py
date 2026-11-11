"""Tracker 0.29.0 (Miguel, 11 Nov): the stats follow the current stages on every tab and on each item.
Run: python3 -m unittest discover -s tests"""
import json
import unittest
from pathlib import Path

from test_013 import S, reset

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
L, U, C = 'LabeledEvent', 'UnlabeledEvent', 'ClosedEvent'


class Version(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 29, 0))
        self.assertIn('version: ' + S.VERSION, (ROOT / 'wizard.md').read_text())
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], S.VERSION)
        self.assertIn(f"PAGE_VERSION = '{S.VERSION}'", JS)


class StageTimes(unittest.TestCase):
    def test_approval_answer_and_show(self):
        ev = [(100, L, 'james-approved'), (200, L, 'building'), (300, L, 'builder:blocked'), (400, U, 'builder:blocked'),
              (500, L, 'ai-review'), (600, L, 'ready-to-test'), (650, U, 'ai-review'), (700, L, 'show-and-tell'),
              (900, U, 'show-and-tell'), (950, C, '')]
        h = S.history_of(ev, 0, '1970-01-01T00:15:50Z', 'CLOSED', now=1000)
        self.assertEqual(h['approval'], 100)
        self.assertEqual(h['answer_rounds'], [100])
        self.assertEqual(h['show_rounds'], [200])
        self.assertEqual(h['handoff_at'], 500)
        self.assertEqual(h['spent2']['answer'], 100)

    def test_open_question_counts_until_now(self):
        h = S.history_of([(50, L, 'building'), (100, L, 'builder:blocked')], 0, None, 'OPEN', now=400)
        self.assertEqual(h['answer_rounds'], [])
        self.assertEqual(h['spent2']['answer'], 300)
        self.assertIsNone(h['approval'])


class Releases(unittest.TestCase):
    def setUp(self):
        reset()

    def test_first_seen_is_kept(self):
        S.note_release('o/r#1', 'testers')
        first = S.release_times('o/r#1')['testers_at']
        self.assertIsNotNone(first)
        S.note_release('o/r#1', 'testers')
        S.note_release('o/r#1', 'done')
        t = S.release_times('o/r#1')
        self.assertEqual(t['testers_at'], first)
        self.assertIsNotNone(t['everyone_at'])
        S.note_release('o/r#2', 'waiting')
        self.assertEqual(S.release_times('o/r#2'), {'testers_at': None, 'everyone_at': None})


class Page(unittest.TestCase):
    def test_stats_use_current_stages(self):
        self.assertIn('function stageStat(v, key)', JS)
        for k in ('james:', 'answer:', 'show:', 'relwait:', 'testers:', 'shipping:'):
            self.assertIn(k, JS[JS.index('function stageStat'):JS.index('function stageStat') + 3000])
        self.assertIn('flow(d, groups, doneN, st, hist, bins)', JS)
        self.assertIn('function drawStageFlow(f, v)', JS)
        self.assertNotIn('then an AI check by their agent', JS)


if __name__ == '__main__':
    unittest.main()
