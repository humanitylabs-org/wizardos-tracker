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

    def test_blocked_waits_on_whom_the_builder_asked(self):
        # 0.28: a builder question is its own stage (answer); it waits on whom the builder @-mentioned, else the filer
        self.assertEqual(self.who(group='answer', blocked=True, opener='James')['who'], ['James'])
        self.assertEqual(self.who(group='answer', blocked=True, opener='James', asked=['Miguel', 'Oscar'])['who'], ['Miguel', 'Oscar'])

    def test_builder_and_stuck(self):
        self.assertEqual(self.who(group='queued', wait_reason='Next for the builder')['who'], ['WizardOS Builder'])
        w = self.who(group='answer', blocked=True)
        self.assertEqual((w['who'], w['kind'], w['stuck']), (['Oscar'], 'person', False))   # no filer known: a person's turn

    def test_summary(self):
        cards = [{'waiting_on': {'who': ['Miguel']}}, {'waiting_on': {'who': ['Miguel']}}, {'waiting_on': {'who': ['Jan']}},
                 {'waiting_on': {'who': ['Oscar'], 'stuck': True}}]
        s = S.waiting_summary({'test': cards, 'queued': []})
        self.assertEqual(s['test']['by'], [['Miguel', 2], ['Jan', 1], ['Oscar', 1]])
        self.assertEqual((s['test']['n'], s['test']['stuck'], s['queued']['n']), (4, 1, 0))


class BugCheck(unittest.TestCase):
    def test_check_line_and_shots(self):
        at, shots = S.bug_check_info(['Fixed it.\n\nCheck: wizard-notes open a long note and scroll\n'
                                      'Before: https://x/a.png\n**After:** ![after](https://x/b.png)'])
        self.assertEqual(at['app'], 'wizard-notes')
        self.assertEqual(at['where'], 'open a long note and scroll')
        self.assertEqual(shots, [{'kind': 'before', 'url': 'https://x/a.png'}, {'kind': 'after', 'url': 'https://x/b.png'}])

    def test_handover_plain_words(self):
        fx = S.bug_handover(['Fixed and merged.\n\nWhat changed: Messenger now swaps only that `bubble`. It used to '
                             'rebuild the list. Third sentence.\n\nMerged: https://x/pull/1\n\nWhat to check:\n'
                             'For the person who filed this: @mistermizel, open a chat and react.\n\nWhat is left: nothing.'])
        self.assertEqual(fx['changed'], 'Messenger now swaps only that bubble. It used to rebuild the list.')
        self.assertEqual(fx['how'], 'open a chat and react.')
        self.assertEqual(S.bug_handover(['no sections here']), {})

    def test_shipped_bug_waits_on_nobody(self):
        self.assertEqual(S.waiting_on({'group': 'test', 'category': 'bug', 'opener': 'James'})['who'], [])


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
