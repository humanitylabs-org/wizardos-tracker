"""0.18.1 unit tests: an item labelled both `bug` and `feature` (wam#524) is a bug everywhere: category, stage, the
legacy `type`, the view queries, and the Bugs search that merges the bug+feature items in.
Run: python3 -m unittest discover -s tests"""
import unittest

from test_013 import S, reset


def node(repo, number, labels, updated):
    return {'repository': {'nameWithOwner': repo}, 'number': number, 'updatedAt': updated, 'createdAt': updated,
            'labels': {'nodes': [{'name': l} for l in labels]}, 'title': 't', 'url': 'u', 'state': 'OPEN'}


class BugWins(unittest.TestCase):
    def setUp(self):
        reset()

    def test_category_and_stage(self):
        self.assertEqual(S.category('humanitylabs-org/wizard-app-manager', ['bug', 'feature']), 'bug')
        self.assertEqual(S.category('humanitylabs-org/wizard-messenger', ['Feature', 'Bug']), 'bug')
        self.assertEqual(S.category('humanitylabs-org/wizard-app-manager', ['feature']), 'core')
        self.assertEqual(S.category('humanitylabs-org/wizard-os', ['goal', 'bug', 'feature']), 'goal')
        # a core bug+feature never waits for James (that is for core features only)
        self.assertEqual(S.item_group('humanitylabs-org/wizard-app-manager', ['bug', 'feature']), 'queued')

    def test_shape_type(self):
        n = node('humanitylabs-org/wizard-app-manager', 524, ['bug', 'feature'], '2026-11-09T00:00:00Z')
        n.update(author={'login': 'x'}, comments={'totalCount': 0}, body='')
        self.assertEqual(S.shape(n)['type'], 'bug')
        self.assertEqual(S.shape(n)['category'], 'bug')

    def test_queries_keep_bug_out_of_features(self):
        for v in ('core', 'apps', 'features'):
            self.assertIn('-label:bug', S.VIEW_Q[v])
        self.assertIn('label:bug label:feature', S.VIEW_ALSO['bugs'])

    def test_bugs_search_merges_bug_feature_items(self):
        a = node('o/x', 1, ['bug'], '2026-11-01T00:00:00Z')
        b = node('o/wizard-app-manager', 524, ['bug', 'feature'], '2026-11-05T00:00:00Z')
        seen = []

        def fake(token, q, heavy=False, limit=None, query=None):
            seen.append(q)
            return ([b, a] if 'label:bug label:feature' in q else [a]), (1 if 'label:bug label:feature' in q else 1)
        saved = S._view_nodes
        S._view_nodes = fake
        try:
            got, total = S._view_search('t', 'bugs', f"org:o is:issue is:open {S.VIEW_Q['bugs']} sort:updated-desc")
            self.assertEqual([n['number'] for n in got], [524, 1])   # newest updated first, no duplicate
            self.assertEqual(total, 2)
            seen.clear()
            S._view_search('t', 'core', f"org:o is:issue is:open {S.VIEW_Q['core']} sort:updated-desc")
            self.assertEqual(len(seen), 1)                            # features: one search
        finally:
            S._view_nodes = saved


if __name__ == '__main__':
    unittest.main()
