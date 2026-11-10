"""Tracker 0.24.0: install and go. One Sign in with GitHub, plain refusals, a one-tap Update on the main screen,
and an agent skill that sends the owner to that button (never wam, never config)."""
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
HTML = (ROOT / 'web' / 'index.html').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
SKILL = (ROOT / 'skill' / 'SKILL.md').read_text()
CONFIG = json.loads((ROOT / 'runtipi' / 'config.json').read_text())
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402


def fn(name):
    a = JS.index('function ' + name + '(')
    b = min(x for x in (JS.find('\nfunction ', a + 10), JS.find('\nasync function ', a + 10)) if x > 0)
    return JS[a:b]


def section(id_):
    a = HTML.index(f'<section id="{id_}"')
    return HTML[a:HTML.index('</section>', a)]


class Version(unittest.TestCase):
    def test_version_everywhere(self):
        self.assertTrue(S.VERSION >= '0.24.0')
        self.assertIn("PAGE_VERSION = '" + S.VERSION + "'", JS)
        self.assertIn("version: '" + S.VERSION + "'", JS)
        self.assertIn('version: ' + S.VERSION, (ROOT / 'wizard.md').read_text())
        self.assertEqual(CONFIG['version'], S.VERSION)
        self.assertIn('version: ' + S.VERSION, SKILL)


class StoreInstall(unittest.TestCase):
    def test_no_form_fields_and_plain_listing(self):
        self.assertEqual(CONFIG['form_fields'], [])
        text = (CONFIG['short_desc'] + ' ' + CONFIG['description']).lower()
        for jargon in ('token', 'client id', 'device flow', 'mock-up', 'wam'):
            self.assertNotIn(jargon, text)
        self.assertIn('sign in with github', text)


class FirstOpen(unittest.TestCase):
    def test_one_obvious_sign_in(self):
        card = section('signin')
        self.assertEqual(card.count('Sign in with GitHub'), 1)   # the button only; the heading is the app name
        self.assertIn('<h1 class="bd-h1">WizardOS Tracker</h1>', card)
        self.assertIn('For the WizardOS team. Sign in with your own GitHub account to start.', card)
        self.assertNotIn('Use a token instead', HTML + JS)
        self.assertNotRegex(card, r'client.?id')
        self.assertNotIn('.bd-signin:has(#oauth:not([hidden])) .bd-h1 { display: none; }', CSS)

    def test_token_way_hidden_until_github_sign_in_fails(self):
        self.assertRegex(HTML, r'<button[^>]*id="oauth-token"[^>]*hidden>Other ways to sign in</button>')
        self.assertIn("el('oauth-token').hidden = !(tokenWanted || otherWays);", fn('signinMode'))
        go = JS[JS.index("el('oauth-go').onclick"):JS.index("el('oauth-copy').onclick")]
        self.assertIn('otherWays = true', go)
        self.assertIn('otherWays = true', fn('pollDevice'))

    def test_code_steps_and_github_link(self):
        card = section('signin')
        self.assertIn('1. Copy this code:', card)
        self.assertIn('href="https://github.com/login/device"', card)
        self.assertIn('signs you in by itself', card)

    def test_built_in_client_needs_no_setup(self):
        with mock.patch.object(S, '_policy_file', return_value={}), mock.patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('GITHUB_CLIENT_ID', None)
            self.assertEqual(S.github_client_id(), 'Iv23li1x6wuDUDj6Herx')
            self.assertTrue(S.device_public(None)['oauth'])


class PlainRefusals(unittest.TestCase):
    def test_not_member_is_one_plain_line(self):
        p = S.not_member_problem('ghu_x' + 'a' * 30, 'stranger')
        self.assertEqual(p.reason, 'not_member')
        self.assertEqual(p.message, S.NOT_MEMBER)
        self.assertNotIn('token', p.message.lower())
        self.assertNotIn('\n', p.message)
        self.assertLess(len(p.message), 140)

    def test_github_sign_in_never_gets_token_advice(self):
        tok = 'ghu_' + 'b' * 36
        S._limited.add((S._tid(tok), S.TEAM_ORG.lower(), 'jan'))
        try:
            self.assertNotIn('token', S.not_member_problem(tok, 'jan').message.lower())
            pat = 'github_pat_' + 'c' * 30
            S._limited.add((S._tid(pat), S.TEAM_ORG.lower(), 'jan'))
            self.assertIn('Resource owner', S.not_member_problem(pat, 'jan').message)
        finally:
            S._limited.clear()

    def test_pending_invite_says_accept_it(self):
        tok = 'ghu_' + 'd' * 36
        body = {'state': 'pending', 'user': {'login': 'robert'}}
        with mock.patch.object(S, '_gh_code', side_effect=lambda t, path: (200, body) if 'memberships' in path else (404, None)), \
                mock.patch.object(S, '_gql_member', return_value=False):
            self.assertFalse(S.team_member(tok, 'robert', fresh=True))
        p = S.not_member_problem(tok, 'robert')
        self.assertEqual(p.message, S.INVITE_PENDING)
        self.assertIn('https://github.com/orgs/humanitylabs-org/invitation', p.message)
        S._pending.clear()


class OneTapUpdate(unittest.TestCase):
    def test_banner_on_main_screen_before_sign_in(self):
        self.assertIn('id="selfupd"', HTML)
        self.assertLess(HTML.index('id="selfupd"'), HTML.index('<section id="signin"'))
        self.assertLess(HTML.index('id="selfupd"'), HTML.index('<div id="board"'))

    def test_banner_uses_the_app_manager_update(self):
        f = fn('selfUpdate')
        self.assertIn("a.id === 'wizardos-tracker'", f)
        self.assertIn('runningSelf(a0)', f)
        self.assertIn('A new version of the Tracker is ready', f)
        self.assertIn("'Update'", f)
        self.assertIn("updateApp('wizardos-tracker', go)", f)
        self.assertNotIn('askPop', f)   # one tap
        self.assertIn('updPanel(r, null)', f)
        self.assertIn("STORE_INSTALL + encodeURIComponent(id)", fn('updateApp'))

    def test_checked_at_open_and_periodically(self):
        self.assertIn('setTimeout(() => checkSelfUpdate(false)', JS)
        self.assertIn('setInterval(() => { if (!document.hidden) checkSelfUpdate(true); }, 30 * 60000)', JS)
        self.assertIn('selfUpdate()', fn('repaintRuns'))


class AgentSkill(unittest.TestCase):
    def test_skill_sends_owner_to_the_button(self):
        self.assertIn('A new version of the Tracker is ready · Update', SKILL)
        self.assertIn('Sign in with GitHub', SKILL)

    def test_skill_never_tells_anyone_to_run_wam_or_edit_config(self):
        for line in SKILL.splitlines():
            if re.search(r'\bwam\b', line):
                self.assertIn('Never run `wam`', line)
            self.assertNotIn('policy.json', line)
            self.assertNotRegex(line.lower(), r'\b(edit|set) (the )?(config|env)')
            self.assertNotIn('Resource owner', line)

    def test_first_run_text_has_no_wam_or_config(self):
        for t in (section('signin'), section('refused'), S.NOT_MEMBER, S.INVITE_PENDING, S.NOT_HUMAN):
            self.assertNotRegex(t, r'\bwam\b|policy\.json|client.?id|GITHUB_CLIENT_ID')


if __name__ == '__main__':
    unittest.main()
