"""Tracker 0.24.1: a stock agent is told the owner-taps rule by the MCP server itself (sign in, Update button,
never wam/config), and tools called before anyone signed in say what to do in plain words."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402


class Version(unittest.TestCase):
    def test_version(self):
        self.assertTrue(S.VERSION >= '0.24.1')
        self.assertEqual(json.loads((ROOT / 'runtipi' / 'config.json').read_text())['version'], S.VERSION)


class AgentInstructions(unittest.TestCase):
    def init(self):
        return S.rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})['result']['instructions']

    def test_instructions_lead_with_owner_taps(self):
        ins = self.init()
        self.assertTrue(ins.startswith(S.AGENT_UPDATE))
        for must in ('tap Sign in with GitHub', 'Update button', 'Never run wam', 'never ask for a token', 'config files'):
            self.assertIn(must, ins)

    def test_nobody_signed_in_message(self):
        with mock.patch.object(S, 'accounts', return_value={'people': {}}):
            with self.assertRaises(S.Problem) as cm:
                S.account_for(None, agent=True)
            self.assertEqual(cm.exception.code, 401)
            self.assertEqual(cm.exception.message, S.NOBODY_AGENT)
            with self.assertRaises(S.Problem) as cm:
                S.account_for('someone')
            self.assertEqual(cm.exception.message, 'Sign in with GitHub first.')
        self.assertIn('tap Sign in with GitHub', S.NOBODY_AGENT)
        self.assertNotIn('Board', S.NOBODY_AGENT)
        src = (ROOT / 'app' / 'server.py').read_text()
        self.assertNotIn('No GitHub account is connected in Board', src)
        self.assertIn("raise Problem(401, NOBODY_AGENT if agent else 'Sign in with GitHub first.')", src)


if __name__ == '__main__':
    unittest.main()
