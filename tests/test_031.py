"""0.31 (Miguel, 12 Nov; wizard-os#548): a bug in its check with no merged fix says No fix yet, not 'Does it work now?'."""
import unittest

from test_013 import S, reset
from test_017 import people, FIXED
from test_0182 import node


class NoFixNoCheck(unittest.TestCase):
    def setUp(self):
        reset()
        people()
        self.saved = (S._view_search, S.view_stats, S.org_repos)
        nodes = [node(1, ['bug', 'ready-to-test'], author='JanMesaric', timelineItems={'nodes': []}),
                 node(2, ['bug', 'ready-to-test'], author='JanMesaric', timelineItems={'nodes': [FIXED(2)]}),
                 node(3, ['bug', 'ai-review'], author='mistermizel', timelineItems={'nodes': []})]
        S._view_search = lambda token, view, q, **kw: (nodes, len(nodes))
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []

    def tearDown(self):
        S._view_search, S.view_stats, S.org_repos = self.saved

    def test_no_fix(self):
        by = {i['number']: i for l in S.board_split('m', {'view': 'bugs'})['groups'].values() for i in l}
        for n in (1, 3):
            self.assertTrue(by[n]['no_fix'], n)
            self.assertFalse(by[n]['shipped'] or by[n]['can_review'] or by[n]['turn'], n)
            self.assertTrue(by[n]['can_fail'], n)   # anyone on the team may send it back
        self.assertTrue(by[2]['shipped'] and by[2]['can_review'])
        self.assertNotIn('no_fix', by[2])

    def test_page(self):
        js = (S.ROOT / 'web' / 'app.js').read_text() if hasattr(S, 'ROOT') else open(__file__.rsplit('/', 2)[0] + '/web/app.js').read()
        self.assertIn("'No fix yet'", js)
        self.assertIn('Send back to the builder', js)


if __name__ == '__main__':
    unittest.main()
