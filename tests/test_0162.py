"""0.16.2: bugs need no human acceptance (removed 6 Nov 2026). The agent-facing tools, MCP instructions,
skill and wizard.md must not tell agents to wait for or ask for acceptance.
Run: python3 -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-0162-'))
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402


class NoAcceptance(unittest.TestCase):
    def test_accept_tool_retired(self):
        names = {t['name'] for t in S.TOOLS}
        self.assertNotIn('board_accept_bug', names)
        self.assertNotIn('board_accept_bug', S.CALLS)
        self.assertEqual(names, set(S.CALLS))

    def test_list_has_no_accepted_filter(self):
        self.assertNotIn('accepted', S.FILTERS)

    def test_tool_texts_and_instructions(self):
        init = S.rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})['result']['instructions']
        texts = [init] + [t['description'] for t in S.TOOLS]
        for text in texts:
            low = text.lower()
            self.assertNotIn('accepts it', low)
            self.assertNotIn('accept bugs', low)
        report = next(t for t in S.TOOLS if t['name'] == 'board_report_bug')['description']
        self.assertIn('ready to work', report)

    def test_docs(self):
        for name in ('skill/SKILL.md', 'wizard.md'):
            text = (ROOT / name).read_text()
            self.assertNotIn('board_accept_bug`', text.replace('the `board_accept_bug` tool is gone', ''), name)
            self.assertNotIn('`accepted` any|yes|no', text, name)
            self.assertNotIn('after a human accepts it', text, name)

    def test_no_accept_route_or_wording(self):
        src = (ROOT / 'app/server.py').read_text()
        self.assertNotIn('/api/issue/accept', src)
        self.assertNotIn('def accept_bug', src)
        self.assertNotIn('/api/issue/accept', json.loads((ROOT / 'openapi.json').read_text())['paths'])
        skill = (ROOT / 'skill/SKILL.md').read_text().lower()
        self.assertNotIn('accept', skill)
        self.assertNotIn('In the app (0.7', (ROOT / 'wizard.md').read_text())

    def test_versions_agree(self):
        v = S.VERSION
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], v)
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], v)
        self.assertIn(f"version: '{v}'", (ROOT / 'web/app.js').read_text())


if __name__ == '__main__':
    unittest.main()
