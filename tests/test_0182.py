"""0.18.2 unit tests (wizard-os#423): core features are approved by James OR Miguel (show-and-tell stays James's),
the viewer's turn flags behind the default 'Your turn first' sort, and the 'Still not working' count.
Run: python3 -m unittest discover -s tests"""
import unittest

from test_013 import GH, S, reset
from test_017 import people


def node(number, labels, author='JanMesaric', repo='humanitylabs-org/wizard-ux', **kw):
    n = {'repository': {'nameWithOwner': repo}, 'number': number, 'title': 't%d' % number, 'url': 'u', 'state': 'OPEN',
         'createdAt': '2026-11-0%dT00:00:00Z' % (number % 9 + 1), 'updatedAt': '2026-11-09T00:00:00Z', 'body': '',
         'author': {'login': author}, 'labels': {'nodes': [{'name': l} for l in labels]}, 'comments': {'totalCount': 0, 'nodes': []},
         'assignees': {'nodes': []}}
    n.update(kw)
    return n


class Approvers(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset()
        people()

    def test_policy_default_and_override(self):
        self.assertEqual(S.policy_base()['core_approvers'], ['James', 'Miguel'])
        self.assertTrue(S.is_core_approver('mistermizel') and S.is_core_approver('jdefleur'))
        self.assertTrue(S.is_core_approver('oscarhenrycollins'))   # Miguel's own agent is Miguel
        self.assertFalse(S.is_core_approver('JanMesaric'))
        reset({'core_approvers': ['James']})
        self.assertFalse(S.is_core_approver('mistermizel'))
        reset()

    def test_miguel_approves_and_declines_core(self):
        GH.issues[50] = {'user': 'JanMesaric', 'labels': {'feature'}, 'comments': []}
        S.james_decide('m', {'repo': 'wizard-ux', 'number': 50, 'decision': 'approve'})
        self.assertIn('james-approved', GH.issues[50]['labels'])
        self.assertTrue(GH.issues[50]['comments'][-1][1].startswith('Miguel: approved'))
        GH.issues[51] = {'user': 'JanMesaric', 'labels': {'feature'}, 'comments': []}
        S.james_decide('m', {'repo': 'wizard-ux', 'number': 51, 'decision': 'decline', 'note': 'Not now'})
        self.assertTrue(GH.issues[51]['comments'][-1][1].startswith('Miguel: declined'))

    def test_others_refused_with_reason(self):
        GH.issues[52] = {'user': 'mistermizel', 'labels': {'feature'}, 'comments': []}
        with self.assertRaises(S.Problem) as e:
            S.james_decide('n', {'repo': 'wizard-ux', 'number': 52, 'decision': 'approve'})
        self.assertEqual((e.exception.code, str(e.exception.message)), (403, 'Only James or Miguel can approve core features.'))

    def test_show_and_tell_stays_james(self):
        GH.issues[53] = {'user': 'JanMesaric', 'labels': {'feature', 'james-approved', 'show-and-tell'}, 'comments': []}
        with self.assertRaises(S.Problem) as e:
            S.show_and_tell('m', {'repo': 'wizard-ux', 'number': 53})
        self.assertEqual(str(e.exception.message), 'Only James approves show-and-tell.')


class BoardFlags(unittest.TestCase):
    """The board gives Miguel and James enabled approval; show-and-tell only James; flags drive 'Your turn first'."""
    def setUp(self):
        GH.issues.clear()
        reset()
        people()
        self.saved = (S._view_search, S.view_stats, S.org_repos)
        nodes = [node(1, ['feature']), node(2, ['feature', 'james-approved', 'show-and-tell']),
                 node(3, ['feature', 'james-approved', 'ready-to-test'], author='mistermizel')]
        S._view_search = lambda token, view, q, **kw: (nodes, len(nodes))
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []

    def tearDown(self):
        S._view_search, S.view_stats, S.org_repos = self.saved

    def flags(self, who):
        d = S.board_split(who, {'view': 'core'})
        g = d['groups']
        return {i['number']: (i['group'], i.get('can_james'), i.get('can_review'), i.get('turn'), i.get('james_rule')) for l in g.values() for i in l}

    def test_miguel(self):
        f = self.flags('m')
        self.assertEqual(f[1][:2], ('james', True))
        self.assertTrue(f[1][3])
        self.assertEqual(f[2][:2], ('show', False))
        self.assertEqual(f[2][4], 'Only James approves show-and-tell.')
        self.assertEqual(f[3][0], 'test')
        self.assertTrue(f[3][2])                      # Miguel filed #3: his Human review turn

    def test_james(self):
        f = self.flags('j')
        self.assertEqual(f[1][:2], ('james', True))
        self.assertEqual(f[2][:2], ('show', True))

    def test_jan_greyed_with_reason(self):
        f = self.flags('n')
        self.assertEqual(f[1][:2], ('james', False))
        self.assertFalse(f[1][3])
        self.assertEqual(f[1][4], 'Only James or Miguel can approve core features.')
        self.assertFalse(f[3][2])


class GoalTurn(unittest.TestCase):
    def setUp(self):
        reset()

    def goal(self, comments, assignees=('JanMesaric',)):
        n = node(9, ['goal'], author='jdefleur', comments={'totalCount': len(comments), 'nodes': [
            {'author': {'login': w}, 'body': b, 'createdAt': at} for w, b, at in comments]},
            assignees={'nodes': [{'login': a} for a in assignees]})
        return n

    def test_owner_needs_status(self):
        base = S.policy_base()
        self.assertTrue(S.goal_card(self.goal([]), 'JanMesaric', base)['turn'])                   # no status yet
        self.assertFalse(S.goal_card(self.goal([]), 'jdefleur', base)['turn'])                    # James can, but doesn't own it
        old = [('JanMesaric', 'Status: green\n\nfine', '2020-01-01T00:00:00Z')]
        self.assertTrue(S.goal_card(self.goal(old), 'JanMesaric', base)['turn'])                  # status is old
        fresh = [('JanMesaric', 'Status: green\n\nfine', S.datetime.now(S.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))]
        self.assertFalse(S.goal_card(self.goal(fresh), 'JanMesaric', base)['turn'])


class StillNotWorking(unittest.TestCase):
    def test_count(self):
        items = [{'kicks': 0, 'tries': 1, 'state': 'open', 'wait': None, 'build': None, 'waiting_for': None},
                 {'kicks': 1, 'tries': 2, 'state': 'open', 'wait': None, 'build': None, 'waiting_for': None},
                 {'kicks': 2, 'tries': 3, 'state': 'closed', 'wait': None, 'build': None, 'waiting_for': None},
                 {'kicks': 4, 'tries': 5, 'state': 'open', 'wait': None, 'build': None, 'waiting_for': None}]
        self.assertEqual(S.summarize(items)['still_not_working'], 2)

    def test_history_counts_two_doesnt_work(self):
        h, d = 3600, 86400
        ev = [(1 * h, 'LabeledEvent', 'building'), (2 * h, 'LabeledEvent', 'ready-to-test'), (3 * h, 'UnlabeledEvent', 'ready-to-test'),
              (4 * h, 'LabeledEvent', 'ready-to-test'), (5 * h, 'UnlabeledEvent', 'ready-to-test')]
        self.assertEqual(S.history_of(ev, 0, None, 'open', now=d)['kicks'], 2)


if __name__ == '__main__':
    unittest.main()
