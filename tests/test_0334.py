"""0.33.4: a Store recipe PR (pins an image, changes only runtipi/ and notes) counts as in the release that carries it."""
import unittest

from test_013 import S


class RecipeOnly(unittest.TestCase):
    def setUp(self):
        self.saved = (S.contains, S.code_commit, S.gh, S.store_listing, S.version_commit)
        S._forever.clear()
        # main: code1 (image built here) -> pin (recipe PR merge, pins code1) ; code2 is a later code change
        S.code_commit = lambda t, repo, c: {'pin': 'code1', 'pin2': 'code1'}.get(c, c)
        order = ['code0', 'code1', 'pin', 'code2', 'pin2']
        S.contains = lambda t, repo, sha, ref: order.index(sha) <= order.index(ref)
        files = {('code1', 'pin'): ['runtipi/docker-compose.yml', 'runtipi/config.json', 'wizard.md', 'UNIFIED-INBOX.md'],
                 ('code1', 'pin2'): ['runtipi/docker-compose.yml', 'app.py'], ('code1', 'code2'): ['app.py']}
        S.gh = lambda t, m, path: {'status': 'ahead', 'files': [{'filename': f} for f in files[tuple(path.split('/compare/')[1].split('?')[0].split('...'))]]}

    def tearDown(self):
        (S.contains, S.code_commit, S.gh, S.store_listing, S.version_commit) = self.saved
        S._forever.clear()

    def test_recipe_pr_is_in_its_own_release(self):
        self.assertTrue(S.in_build('t', 'o/r', 'pin', 'pin'))
        self.assertTrue(S.in_build('t', 'o/r', 'code1', 'pin'))

    def test_code_not_in_the_image_stays_out(self):
        self.assertFalse(S.in_build('t', 'o/r', 'code2', 'pin2'))
        self.assertFalse(S.in_build('t', 'o/r', 'pin2', 'pin2'))   # app.py changed after the image: not recipe only
        self.assertIsNone(S.in_build('t', 'o/r', 'pin', None))

    def test_where_offers_the_update(self):
        S.store_listing = lambda repo: {'id': 'messenger', 'name': 'Messenger', 'version': '16.38', 'commit': 'pin'}
        S.version_commit = lambda t, repo, v: {'16.38': 'pin', '16.35': 'code0'}.get(v)
        d = {'repo': 'humanitylabs-org/wizard-messenger', 'sha': 'pin'}
        self.assertEqual(S.where('t', d, {'apps': {'messenger': '16.35'}}), ('no', 'Update Messenger', 'messenger'))
        self.assertEqual(S.where('t', d, {'apps': {'messenger': '16.38'}}), ('yes', None, 'messenger'))


if __name__ == '__main__':
    unittest.main()
