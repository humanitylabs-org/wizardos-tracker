"""0.18 unit tests: Goals | Core features | App features | Bugs, core vs app from the repo, the filer tests, core features
wait for James and get his show-and-tell, goal status comments, and Shipping -> Done from releases.
Run: python3 -m unittest discover -s tests"""
import unittest

from test_013 import GH, S, reset
from test_017 import people, BODY


class Classify(unittest.TestCase):
    def setUp(self):
        reset()

    def test_core_vs_app_from_repo(self):
        self.assertEqual(S.category('humanitylabs-org/wizard-os', ['feature']), 'core')
        self.assertEqual(S.category('humanitylabs-org/try-wizard', ['feature']), 'core')
        self.assertEqual(S.category('humanitylabs-org/wizard-messenger', ['feature']), 'app')
        self.assertEqual(S.category('humanitylabs-org/wizard-os', ['bug']), 'bug')
        self.assertEqual(S.category('humanitylabs-org/wizard-messenger', ['goal', 'feature']), 'goal')
        self.assertTrue(S.view_keeps('core', 'humanitylabs-org/wizard-ux'))
        self.assertFalse(S.view_keeps('apps', 'humanitylabs-org/wizard-ux'))
        self.assertTrue(S.view_keeps('bugs', 'humanitylabs-org/anything'))

    def test_core_list_lives_in_policy(self):
        reset({'core_repos': ['wizard-messenger']})
        self.assertEqual(S.category('humanitylabs-org/wizard-messenger', ['feature']), 'core')
        self.assertEqual(S.category('humanitylabs-org/wizard-os', ['feature']), 'app')
        reset()
        self.assertEqual(S.policy_base()['core_repos'], list(S.CORE_REPOS))

    def test_stages(self):
        g = S.item_group
        self.assertEqual(g('o/wizard-os', ['feature']), 'james')                       # core: waits for James
        self.assertEqual(g('o/wizard-os', ['feature', 'james-approved']), 'queued')
        self.assertEqual(g('o/wizard-os', ['feature', 'james-approved', 'building']), 'building')
        self.assertEqual(g('o/wizard-messenger', ['feature']), 'queued')               # app: builder starts
        self.assertEqual(g('o/wizard-os', ['feature', 'ready-to-test']), 'test')
        self.assertEqual(g('o/wizard-os', ['feature', 'show-and-tell']), 'show')
        self.assertEqual(g('o/wizard-os', ['feature', 'approved', 'switch-default']), 'shipping')
        self.assertEqual(g('o/x', ['bug', 'ai-review']), 'airev')


class James(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset()
        people()

    def test_only_james_approves_core(self):   # 0.18.2: James or Miguel (test_0182 covers Miguel)
        GH.issues[30] = {'user': 'mistermizel', 'labels': {'feature'}, 'comments': []}
        with self.assertRaises(S.Problem) as e:
            S.james_decide('n', {'repo': 'wizard-ux', 'number': 30, 'decision': 'approve'})
        self.assertEqual((e.exception.code, str(e.exception.message)), (403, 'Only James or Miguel can approve core features.'))
        try:
            S.james_decide('j', {'repo': 'wizard-ux', 'number': 30, 'decision': 'approve'})
        except S.Problem:
            pass
        self.assertIn('james-approved', GH.issues[30]['labels'])
        self.assertTrue(GH.issues[30]['comments'][-1][1].startswith('James: approved'))

    def test_core_works_goes_to_show_and_tell(self):
        GH.issues[31] = {'user': 'mistermizel', 'labels': {'feature', 'james-approved', 'ready-to-test'}, 'comments': []}
        r = S.tested('m', {'repo': 'wizard-ux', 'number': 31}, True)
        self.assertEqual(r['stage'], 'show')
        self.assertEqual(GH.issues[31]['labels'], {'feature', 'james-approved', 'show-and-tell'})
        with self.assertRaises(S.Problem) as e:
            S.show_and_tell('m', {'repo': 'wizard-ux', 'number': 31})
        self.assertEqual(str(e.exception.message), 'Only James approves show-and-tell.')
        r = S.show_and_tell('j', {'repo': 'wizard-ux', 'number': 31})
        self.assertIn('approved', GH.issues[31]['labels'])
        self.assertNotIn('show-and-tell', GH.issues[31]['labels'])
        self.assertFalse(r['switch_default'])

    def test_show_and_tell_with_switch_asks_builder_to_default_it(self):
        GH.issues[32] = {'user': 'mistermizel', 'labels': {'feature', 'show-and-tell'}, 'body': 'Switch: FancyThing',
                         'comments': [('defleur-agents', 'Switch: FancyThing')]}
        r = S.show_and_tell('j', {'repo': 'wizard-ux', 'number': 32})
        self.assertTrue(r['switch_default'])
        self.assertIn('switch-default', GH.issues[32]['labels'])


class GoalStatus(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset()
        people()
        GH.issues[40] = {'user': 'jdefleur', 'assignees': ['JanMesaric'], 'labels': {'goal'}, 'comments': [], 'body': BODY}

    def test_parse_latest_and_stale(self):
        rows = [('JanMesaric', 'Status: green\n\nAll good.', '2026-11-01T00:00:00Z'), ('x', 'just a comment', '2026-11-02T00:00:00Z'),
                ('mistermizel', '**Status: Red**\nStuck on review.', '2026-11-03T00:00:00Z')]
        h = S.status_of(rows)
        self.assertEqual([x['color'] for x in h], ['red', 'green'])
        self.assertEqual((h[0]['word'], h[0]['text'], h[0]['by_person']), ('Blocked', 'Stuck on review.', 'Miguel'))
        now = S._ts('2026-11-05T00:00:00Z')
        self.assertFalse(S.latest_status(rows, now=now)['stale'])
        self.assertTrue(S.latest_status(rows, now=now + 8 * 86400)['stale'])
        self.assertIsNone(S.latest_status([('x', 'hello', '2026-11-01T00:00:00Z')]))

    def test_owner_or_james_posts_others_refused(self):
        with self.assertRaises(S.Problem) as e:
            S.goal_status_set('m', {'repo': 'wizard-ux', 'number': 40, 'color': 'green', 'text': 'Fine'})
        self.assertEqual((e.exception.code, str(e.exception.message)), (403, 'Only the goal\u2019s owners or James update this.'))
        S.goal_status_set('n', {'repo': 'wizard-ux', 'number': 40, 'color': 'yellow', 'text': 'Slipping a day.'})
        self.assertEqual(GH.issues[40]['comments'][-1], ('JanMesaric', 'Status: yellow\n\nSlipping a day.'))
        S.goal_status_set('j', {'repo': 'wizard-ux', 'number': 40, 'color': 'green', 'text': 'Back on track.'})
        with self.assertRaises(S.Problem):
            S.goal_status_set('j', {'repo': 'wizard-ux', 'number': 40, 'color': 'blue', 'text': 'Back on track.'})

    def test_mcp_tools_listed(self):
        names = {t['name'] for t in S.TOOLS}
        self.assertTrue({'goal_status_set', 'goal_status_get'} <= names)
        self.assertIn('goal_status_set', S.CALLS)


class Shipping(unittest.TestCase):
    def test_states(self):
        saved = (S.release_pointer, S.release_manifest, S.release_commit, S.contains, S.store_listing, S.mac_release, S.code_commit, S._write)
        try:
            S._write = lambda *a, **k: None
            S.release_pointer = lambda t, ch: {'stable': '0.3.130', 'latest': '0.3.134'}[ch]
            S.release_manifest = lambda t, v: v
            S.release_commit = lambda m, repo: 'pin-' + m if repo.endswith('wizard-ux') else None
            S.contains = lambda t, repo, sha, ref: {('a', 'pin-0.3.130'): True, ('b', 'pin-0.3.134'): True}.get((sha, ref), False)
            S.store_listing = lambda repo: {'name': 'Messenger', 'version': '0.5.1', 'commit': 'c'}
            S.code_commit = lambda t, repo, c: c
            S.mac_release = lambda t, repo: None
            one = lambda repo, sha: S.ship_one('t', {'repo': 'humanitylabs-org/' + repo, 'sha': sha})
            self.assertEqual(one('wizard-ux', 'a')[:2], ('done', 'Shipped in 0.3.130'))
            self.assertEqual(one('wizard-ux', 'b')[:2], ('testers', 'In For testers 0.3.134'))
            self.assertEqual(one('wizard-ux', 'c')[:2], ('waiting', 'Waiting for release'))
            self.assertEqual(one('try-wizard', 'x')[:2], ('mac', 'Waiting for Mac app build'))
            self.assertEqual(one('wizard-messenger', 'x')[:2], ('app', 'Waiting for Messenger release'))
            st = S.ship_status('t', 'o/r#1', [{'repo': 'humanitylabs-org/wizard-ux', 'sha': 'c'}], [], 'closed', None, ['approved'])
            self.assertEqual((st['state'], st['text']), ('shipping', 'Waiting for release'))
            st = S.ship_status('t', 'o/r#2', [{'repo': 'humanitylabs-org/wizard-ux', 'sha': 'a'}], [], 'closed', None, ['approved'])
            self.assertEqual((st['state'], st['text']), ('done', 'Shipped in 0.3.130'))
        finally:
            (S.release_pointer, S.release_manifest, S.release_commit, S.contains, S.store_listing, S.mac_release, S.code_commit, S._write) = saved


if __name__ == '__main__':
    unittest.main()
