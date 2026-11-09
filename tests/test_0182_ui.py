"""0.18.2 UI checks: the default sort is 'Your turn first', the menu keeps the other options, and myTurn() picks the
viewer's own actions (runs the real function from web/app.js in node). Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / 'web/app.js').read_text()


def fn(name):
    m = re.search(r'^function ' + name + r'\(.*?^}', JS, re.S | re.M)
    return m.group(0)


class Sorts(unittest.TestCase):
    def test_menu_and_default(self):
        self.assertIn("const SORTS = [['turn', 'Your turn first'], ['oldest', 'Oldest'], ['newest', 'Newest'], ['discussed', 'Most discussed'], ['active', 'Recently active']]", JS)
        self.assertIn(": 'turn';", JS)
        self.assertIn("'Your turn'", JS)
        self.assertIn("Waiting for approval", JS)
        self.assertIn("James or Miguel approves before the builder starts", JS)
        self.assertNotIn("'Waiting for James'", JS)

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_my_turn(self):
        cases = [({'group': 'test', 'can_review': True}, True), ({'group': 'test', 'can_review': False}, False),
                 ({'group': 'james', 'can_james': True}, True), ({'group': 'james', 'can_james': False}, False),
                 ({'group': 'show', 'can_james': True}, True), ({'group': 'building', 'can_james': True}, False),
                 ({'group': 'goals', 'category': 'goal', 'turn': True}, True), ({'group': 'goals', 'turn': False}, False),
                 ({'group': 'test', 'can_review': True, 'state': 'closed'}, False)]
        src = fn('myTurn') + '\nconsole.log(JSON.stringify(' + json.dumps([c for c, _ in cases]) + '.map(myTurn)));'
        out = subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [w for _, w in cases])


if __name__ == '__main__':
    unittest.main()
