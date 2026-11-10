"""Tracker 0.23: one switch catalog for core and apps (the box's App Manager merges installed apps' own switches)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()

import sys
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402


class Version(unittest.TestCase):
    def test_version(self):
        self.assertEqual(S.VERSION, '0.23.0')
        self.assertIn("version: '0.23.0'", JS)
        self.assertIn("PAGE_VERSION = '0.23.0'", JS)


class OneCatalog(unittest.TestCase):
    def test_items_adopt_the_catalog_switch_that_names_their_issue(self):
        self.assertIn('function adoptSwitch(i)', JS)
        self.assertIn('box.byIssue[String(i.id', JS)
        # every view's items adopt, both when the catalog arrives and when a view renders
        self.assertRegex(JS, r'function render\(d\) \{\n  if \(d.view !== view\) return;\n  for \(const g of Object.values\(d.groups')

    def test_app_switches_are_not_locked_by_the_channel(self):
        self.assertIn("sw.kind === 'app' ? sw.locked : (box.locked || sw.locked)", JS)
        self.assertNotIn("sw.on && !box.locked", JS)

    def test_flip_goes_through_the_box_catalog_not_the_app(self):
        # trySwitch posts {id, on} to the one catalog route; an adopted app switch is '<app>:<switch>'
        self.assertIn("takeSwitches(await switchApi({ id: i.switch, on: next }))", JS)
        self.assertIn("const SWITCH_API = '/wizard-os-home/store-install/_feature-switches'", JS)

    def test_an_adopted_switch_counts_as_on_the_box(self):
        self.assertIn('const hit = (i.switch_adopted && box && box.ok && box.switches[i.switch])', JS)


if __name__ == '__main__':
    unittest.main()
