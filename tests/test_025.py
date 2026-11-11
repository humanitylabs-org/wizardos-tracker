"""Tracker 0.25: every open card says whose move it is (waiting_on), stages sum it (waiting_summary), and the Repo
filter of Core/App features only lists that view's repos.
Run: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402


class WaitingOn(unittest.TestCase):
    def setUp(self):
        self.base = S.policy_base()

    def who(self, **card):
        return S.waiting_on(card, self.base)

    def test_human_review_waits_on_filer(self):
        self.assertEqual(self.who(group='test', opener='James')['who'], ['James'])
        self.assertEqual(self.who(group='test', opener='stranger')['who'], ['Anyone on the team'])

    def test_core_approval_and_show(self):
        self.assertEqual(self.who(group='james')['who'], ['James', 'Miguel'])
        self.assertEqual(self.who(group='show')['who'], ['James'])

    def test_ai_review_names_the_agent(self):
        w = self.who(group='airev', ai_reviewer='Archimedes')
        self.assertEqual((w['who'], w['kind']), (['Archimedes'], 'agent'))

    def test_any_team_agent_lists_agents(self):
        w = self.who(group='airev', ai_reviewer='any team agent')
        self.assertIn('Archimedes', w['who'])

    def test_blocked_waits_on_filer(self):
        self.assertEqual(self.who(group='queued', blocked=True, opener='James')['who'], ['James'])

    def test_builder_and_stuck(self):
        self.assertEqual(self.who(group='queued', wait_reason='Next for the builder')['who'], ['WizardOS Builder'])
        w = self.who(group='queued', blocked=True)
        self.assertEqual((w['who'], w['stuck']), (['Oscar'], True))   # no filer known

    def test_summary(self):
        cards = [{'waiting_on': {'who': ['Miguel']}}, {'waiting_on': {'who': ['Miguel']}}, {'waiting_on': {'who': ['Jan']}},
                 {'waiting_on': {'who': ['Oscar'], 'stuck': True}}]
        s = S.waiting_summary({'test': cards, 'queued': []})
        self.assertEqual(s['test']['by'], [['Miguel', 2], ['Jan', 1], ['Oscar', 1]])
        self.assertEqual((s['test']['n'], s['test']['stuck'], s['queued']['n']), (4, 1, 0))


class RepoFilter(unittest.TestCase):
    def test_view_keeps_splits_core_and_apps(self):
        base = S.policy_base()
        core = next(iter(base['core_repos']))
        self.assertTrue(S.view_keeps('core', 'humanitylabs-org/' + core, base))
        self.assertFalse(S.view_keeps('apps', 'humanitylabs-org/' + core, base))
        self.assertTrue(S.view_keeps('apps', 'humanitylabs-org/movies', base))
        self.assertTrue(S.view_keeps('bugs', 'humanitylabs-org/movies', base))

    def test_view_repos(self):
        base = S.policy_base()
        core = 'o/' + next(iter(base['core_repos']))
        names = [core, 'o/movies', 'o/aiwizards.com']
        old = S.org_repos
        try:
            S.org_repos = lambda token, org: names
            S._app_repos.update({'o/movies': True, 'o/aiwizards.com': False, core.lower(): False})
            self.assertEqual(S.view_repos('t', 'o', 'core', base), [core])
            self.assertEqual(S.view_repos('t', 'o', 'apps', base), ['o/movies'])
            self.assertEqual(S.view_repos('t', 'o', 'bugs', base), names)
        finally:
            S.org_repos = old


if __name__ == '__main__':
    unittest.main()
