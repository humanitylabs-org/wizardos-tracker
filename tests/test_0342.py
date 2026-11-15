"""Tracker 0.34.2 (Miguel, 15 Nov): 'Update <app> first' must never pair with an Update that says 'already the latest'.
Is it on my Wizard? takes installed versions from the App Manager (the Update buttons' source), /healthz only as fallback."""
import re
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / 'web' / 'app.js').read_text()


class InstalledVersionSource(unittest.TestCase):
    def body(self):
        m = re.search(r'async function appVersion\(id\) \{(.*?)\n\}', JS, re.S)
        self.assertIsNotNone(m)
        return m.group(1)

    def test_app_manager_first(self):
        b = self.body()
        self.assertIn('await loadCatalog()', b)
        self.assertLess(b.index('loadCatalog'), b.index('/healthz'))
        self.assertIn('facts.apps[id] = a.version; return;', b)

    def test_healthz_is_fallback(self):
        self.assertIn("'/healthz'", self.body())


if __name__ == '__main__':
    unittest.main()
