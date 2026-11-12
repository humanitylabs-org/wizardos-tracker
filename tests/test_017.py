"""0.17 unit tests: goals steer (Keep going / Change direction + done-list ticks) instead of Works / Doesn't work, only
James closes a goal, everyone sees the same items and controls, and where to flip a switch the Tracker can't flip.
Run: python3 -m unittest discover -s tests"""
import json
import re
import unittest

from test_013 import GH, S, reset

JAMES, JAN, MIGUEL = 'tok_james_aaaaaaaaaaaaaaaaaaaaaaa', 'tok_jan_aaaaaaaaaaaaaaaaaaaaaaaaa', 'tok_miguel_aaaaaaaaaaaaaaaaaaaaaa'
BODY = 'Goal.\n\n- [x] one\n- [ ] two\n- [ ] three\n'

# The 0.13 mock knows no issue bodies or PATCH: add both for goals.
_old_issue = GH._issue


def _issue(self, n):
    out = _old_issue(self, n)
    out['body'] = self.issues[n].get('body', '')
    out['state'] = self.issues[n].get('state', 'open')
    return out


def do_PATCH(self):
    body = self._body()
    m = re.match(r'^/repos/humanitylabs-org/wizard-ux/issues/(\d+)$', self.path)
    if not m:
        return self._send(404, {})
    it = self.issues[int(m.group(1))]
    if 'body' in body:
        it['body'] = body['body']
    if 'state' in body:
        it['state'] = body['state']
    return self._send(200, _issue(self, int(m.group(1))))


GH._issue = _issue
GH.do_PATCH = do_PATCH


def people():
    S._write('accounts.json', {'people': {'j': {'token': JAMES, 'login': 'jdefleur'}, 'n': {'token': JAN, 'login': 'JanMesaric'},
                                          'm': {'token': MIGUEL, 'login': 'mistermizel'}}, 'default': 'm'})


class GoalStep(unittest.TestCase):
    """0.18: Keep going / Change direction is gone; goals never take Works / Doesn't work."""
    def setUp(self):
        GH.issues.clear()
        reset()
        people()
        GH.issues[20] = {'user': 'jdefleur', 'assignees': ['JanMesaric'], 'labels': {'goal', 'ready-to-test'}, 'comments': [], 'body': BODY}

    def test_goal_step_is_gone(self):
        self.assertFalse(hasattr(S, 'goal_step'))

    def test_goals_never_take_works(self):
        with self.assertRaises(S.Problem) as e:
            S.tested('j', {'repo': 'wizard-ux', 'number': 20}, True)
        self.assertEqual(e.exception.reason, 'goal')
        with self.assertRaises(S.Problem):
            S.tested('n', {'repo': 'wizard-ux', 'number': 20}, False)
        self.assertIn('ready-to-test', GH.issues[20]['labels'])


class CloseGoal(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset()
        people()
        GH.issues[21] = {'user': 'jdefleur', 'assignees': ['JanMesaric'], 'labels': {'goal'}, 'comments': [], 'body': BODY}

    def test_only_james_closes_and_only_when_all_ticked(self):
        with self.assertRaises(S.Problem) as e:
            S.set_state('n', {'repo': 'wizard-ux', 'number': 21}, 'closed')   # an owner, still not James
        self.assertEqual((e.exception.code, e.exception.reason), (403, 'not_goal_closer'))
        with self.assertRaises(S.Problem) as e:
            S.set_state('j', {'repo': 'wizard-ux', 'number': 21}, 'closed')
        self.assertEqual(e.exception.reason, 'not_all_done')
        try:
            S.set_state('j', {'repo': 'wizard-ux', 'number': 21, 'anyway': True}, 'closed')
        except S.Problem as e:   # the mock has no GraphQL read-back; the close itself went through
            self.assertEqual(e.code, 404)
        self.assertEqual(GH.issues[21]['state'], 'closed')

    def test_goal_flags_are_the_same_shape_for_everyone(self):
        a = S.goal_flags(BODY, ['JanMesaric'], 'jdefleur', 'jdefleur')
        b = S.goal_flags(BODY, ['JanMesaric'], 'jdefleur', 'mistermizel')
        self.assertEqual(set(a), set(b))
        self.assertEqual((a['can_close_goal'], b['can_close_goal']), (True, False))
        self.assertEqual(b['close_rule'], 'Only James closes a goal.')
        self.assertEqual(b['steer_rule'], 'Only Jan or James review this goal.')
        self.assertFalse(a['all_done'])


def FIXED(n):
    """0.31: a merged PR that fixed item n (bugs in their check need one, or they say No fix yet)."""
    return {'source': {'__typename': 'PullRequest', 'number': 900 + n, 'url': f'https://github.com/humanitylabs-org/wizard-ux/pull/{900 + n}',
                       'state': 'MERGED', 'merged': True, 'mergeCommit': {'oid': 'a' * 40}, 'repository': {'nameWithOwner': 'humanitylabs-org/wizard-ux'}}}


def _node(n, author, labels, body='', assignees=()):
    return {'number': n, 'title': f'Item {n}', 'url': f'https://github.com/humanitylabs-org/wizard-ux/issues/{n}', 'body': body,
            'createdAt': '2026-11-01T00:00:00Z', 'updatedAt': '2026-11-02T00:00:00Z', 'author': {'login': author},
            'assignees': {'nodes': [{'login': a} for a in assignees]}, 'repository': {'nameWithOwner': 'humanitylabs-org/wizard-ux'},
            'labels': {'nodes': [{'name': l} for l in labels]}, 'comments': {'totalCount': 0, 'nodes': []}, 'timelineItems': {'nodes': [FIXED(n)] if 'bug' in labels else []}}


class SameForEveryone(unittest.TestCase):
    """Two different signed-in people get the same items and the same controls; only enabled/disabled differs."""
    def setUp(self):
        reset()
        people()
        self.saved = (S._view_nodes, S.view_stats, S.org_repos)
        nodes = {'bugs': [_node(1, 'mistermizel', ['bug', 'ready-to-test']), _node(2, 'jdefleur', ['bug', 'ready-to-test']),
                          _node(3, 'JanMesaric', ['bug', 'building'])],
                 'goals': [_node(4, 'jdefleur', ['goal', 'ready-to-test'], BODY, ['JanMesaric']), _node(5, 'jdefleur', ['goal'], BODY)]}
        S._view_nodes = lambda token, q, heavy=False, limit=None, query=None: (nodes['goals' if ' label:goal' in q else 'bugs'], 3)
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: ['humanitylabs-org/wizard-ux']

    def tearDown(self):
        S._view_nodes, S.view_stats, S.org_repos = self.saved

    def shape(self, d):
        """(id, sorted control keys) per group: what is shown, not whether it is enabled."""
        return {g: [(i['id'], tuple(sorted(k for k in i if k.startswith(('can_', 'review_rule', 'close_rule', 'steer_rule'))))) for i in v]
                for g, v in d['groups'].items()}

    def test_same_items_and_controls(self):
        for view in ('bugs', 'goals'):
            a, b = S.board_split('m', {'view': view}), S.board_split('j', {'view': view})
            self.assertEqual(self.shape(a), self.shape(b), view)
        bugs_m = S.board_split('m', {'view': 'bugs'})
        self.assertIn('humanitylabs-org/wizard-ux#1', [i['id'] for i in bugs_m['groups']['test']])   # your own item is listed
        mine = next(i for i in bugs_m['groups']['test'] if i['number'] == 1)
        self.assertTrue(mine['can_review'])            # 0.18: the filer tests
        jb = next(i for i in S.board_split('j', {'view': 'bugs'})['groups']['test'] if i['number'] == 1)
        self.assertEqual((jb['can_review'], jb['review_rule']), (True, ''))   # 0.26: anyone on the team checks a bug
        g_m, g_j = S.board_split('m', {'view': 'goals'}), S.board_split('j', {'view': 'goals'})
        self.assertEqual([i['can_close'] for i in g_m['groups']['goals']], [False, False])
        self.assertEqual([i['can_close'] for i in g_j['groups']['goals']], [True, True])
        self.assertEqual(g_m['groups']['goals'][0]['progress'], {'done': 1, 'total': 3, 'of': 'done-list items'})

    def test_just_filed_item_shows_for_everyone(self):
        card = {'id': 'humanitylabs-org/wizard-ux#9', 'repo': 'humanitylabs-org/wizard-ux', 'number': 9, 'title': 'New', 'author': 'mistermizel'}
        S._made[('someone-elses-token', card['id'])] = (S.time.time(), 'issues', card)
        try:
            a, b = S.board_split('m', {'view': 'bugs'}), S.board_split('j', {'view': 'bugs'})
            self.assertEqual(self.shape(a), self.shape(b))
            qa = next(i for i in a['groups']['queued'] if i['number'] == 9)
            qb = next(i for i in b['groups']['queued'] if i['number'] == 9)
            self.assertEqual((qa['mine'], qb['mine']), (True, False))
            self.assertEqual([i['id'] for i in a['test']], [i['id'] for i in b['test']])  # 0.3 shape: same for everyone
        finally:
            S._made.clear()

    def test_test_tab_query_has_no_author_filter(self):
        src = open(str(S.__file__)).read()
        self.assertNotIn("-author:{login}", src)


class SwitchPlace(unittest.TestCase):
    def test_mac_default_gets_the_terminal_command(self):
        p = S.switch_place('TitleBarDoubleClick', ['Switch: TitleBarDoubleClick (Mac user default, off by default)\n'
                           'run `defaults write org.humanitylabs.wizard.mvp TitleBarDoubleClick -bool YES` and relaunch'],
                           'humanitylabs-org/try-wizard')
        self.assertEqual(p['kind'], 'mac')
        self.assertEqual(p['cmd'], 'defaults write org.humanitylabs.wizard.mvp TitleBarDoubleClick -bool YES')

    def test_mac_repo_without_command(self):
        p = S.switch_place('ImportConnectPrompt', ['Switch: ImportConnectPrompt'], 'humanitylabs-org/try-wizard')
        self.assertEqual(p['cmd'], 'defaults write org.humanitylabs.wizard.mvp ImportConnectPrompt -bool YES')

    def test_app_setting_and_box_knob(self):
        self.assertEqual(S.switch_place('Settings › Drafts at top', [], 'humanitylabs-org/wizard-messenger'),
                         {'kind': 'app', 'text': 'Settings › Drafts at top', 'repo': 'humanitylabs-org/wizard-messenger'})
        self.assertEqual(S.switch_place('env WIZARD_TRAIN_HOTFIX_LANE=1', [], 'humanitylabs-org/wizard-os')['kind'], 'box')
        self.assertIsNone(S.switch_place(None, [], 'x/y'))


if __name__ == '__main__':
    unittest.main()
