"""0.16 unit tests: 'Is it on my Wizard?' (merged PRs -> box build -> GitHub compare), test steps from the AI
review note, review rules worded for the card, and the optional Doesn't work note. GitHub is faked in-process.
Run: python3 -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-016-'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import server as S  # noqa: E402

A = '1' * 40   # merge commit of the PR under test
OLD, NEW = '2' * 40, '3' * 40   # builds without / with it
UX, MSG, MAC = 'humanitylabs-org/wizard-ux', 'humanitylabs-org/wizard-messenger', 'humanitylabs-org/try-wizard'


def manifest(ux):
    return {'components': {'wizard-ux': {'repo': UX, 'commit': ux}}}


class FakeGitHub:
    """compare: a build contains A when it is NEW (or A itself). Releases: 0.3.1 has OLD, 0.3.2 has NEW."""
    def __init__(self, stable='0.3.1', latest='0.3.2', mac_tag=None):
        self.stable, self.latest, self.mac_tag, self.calls = stable, latest, mac_tag, []

    def __call__(self, token, method, path, body=None, cache=True, **_):
        self.calls.append(path)
        if '/compare/' in path:
            build = path.split('...')[1].split('?')[0]
            return {'status': 'ahead' if build in (NEW, 'v-new') else 'behind'}
        if path.startswith('/repos/' + S.RELEASES_REPO + '/contents/releases/'):
            name = path.split('/releases/')[1].split('?')[0]
            content = {'stable': self.stable, 'latest': self.latest,
                       '0.3.1.json': json.dumps(manifest(OLD)), '0.3.2.json': json.dumps(manifest(NEW))}.get(name)
            if content is None:
                raise S.Problem(404, 'nope')
            import base64
            return {'encoding': 'base64', 'content': base64.b64encode(content.encode()).decode()}
        if path.startswith(f'/repos/{MSG}/contents/runtipi/docker-compose.yml'):
            ref = path.split('ref=')[1]
            import base64
            img = {'recipe-new': NEW, 'recipe-old': OLD}.get(ref, OLD)
            return {'encoding': 'base64', 'content': base64.b64encode(f'image: ghcr.io/{MSG}:sha-{img}@sha256:x'.encode()).decode()}
        if path.startswith(f'/repos/{MSG}/commits?path=runtipi/config.json'):
            return [{'sha': 'recipe-new'}, {'sha': 'recipe-old'}]
        if path.startswith(f'/repos/{MSG}/contents/runtipi/config.json'):
            import base64
            ref = path.split('ref=')[1]
            v = {'recipe-new': '1.1', 'recipe-old': '1.0'}[ref]
            return {'encoding': 'base64', 'content': base64.b64encode(json.dumps({'version': v}).encode()).decode()}
        if path.startswith(f'/repos/{MAC}/releases'):
            return [{'tag_name': self.mac_tag, 'published_at': '2026-11-01T00:00:00Z'}] if self.mac_tag else []
        raise S.Problem(404, 'nope')


class OnBox(unittest.TestCase):
    def setUp(self):
        for c in (S._forever, S._timed, S._verdicts):
            c.clear()
        self.fake = FakeGitHub()
        self.real_gh, self.real_store = S.gh, S.store_listing
        S.gh = self.fake
        S.store_listing = lambda repo: {'id': 'messenger', 'name': 'Messenger', 'version': '1.1', 'commit': 'recipe-new'} if repo == MSG else None

    def tearDown(self):
        S.gh, S.store_listing = self.real_gh, self.real_store

    def v(self, repo, box, open_prs=0):
        return S.verdict('t', [{'repo': repo, 'number': 1, 'sha': A}] if repo else [], open_prs, box)

    def test_core_component_on_box(self):
        v = self.v(UX, {'release': '0.3.2', 'channel': 'latest', 'apps': {}})
        self.assertEqual((v['state'], v['text'], v['fix']), ('yes', 'On your Wizard ✓', None))

    def test_core_component_needs_update(self):
        v = self.v(UX, {'release': '0.3.1', 'channel': 'latest', 'apps': {}})
        self.assertEqual((v['state'], v['text'], v['fix']), ('no', 'Not on your Wizard yet', 'Update WizardOS in Settings'))

    def test_core_component_only_for_testers(self):
        v = self.v(UX, {'release': '0.3.1', 'channel': 'stable', 'apps': {}})
        self.assertEqual(v['fix'], 'Switch to For testers in Settings')

    def test_core_component_not_released(self):
        self.fake.latest = '0.3.1'
        v = self.v(UX, {'release': '0.3.1', 'channel': 'latest', 'apps': {}})
        self.assertEqual(v['fix'], 'Not released yet')

    def test_core_component_unknown_without_release(self):
        v = self.v(UX, {'release': None, 'channel': None, 'apps': {}})
        self.assertEqual((v['state'], v['text']), ('unknown', 'Can’t tell if this is on your Wizard'))

    def test_app_asks_for_its_version_first(self):
        v = self.v(MSG, {'release': '0.3.2', 'channel': 'latest', 'apps': {}})
        self.assertEqual((v['state'], v['apps']), ('unknown', ['messenger']))

    def test_app_current_and_old(self):
        self.assertEqual(self.v(MSG, {'release': None, 'channel': None, 'apps': {'messenger': '1.1'}})['state'], 'yes')
        v = self.v(MSG, {'release': None, 'channel': None, 'apps': {'messenger': '1.0'}})
        self.assertEqual((v['state'], v['fix']), ('no', 'Update Messenger'))

    def test_app_not_released(self):
        # messenger#133 on oscar-main before 9 Nov: the box and the Store both run a build behind the merge
        S.store_listing = lambda repo: {'id': 'messenger', 'name': 'Messenger', 'version': '1.0', 'commit': 'recipe-old'}
        v = self.v(MSG, {'release': None, 'channel': None, 'apps': {'messenger': '1.0'}})
        self.assertEqual((v['state'], v['text'], v['fix']), ('no', 'Not on your Wizard yet', 'Not released yet'))

    def test_mac_app(self):
        # 0.17: a Mac change needs the Mac app update unless the viewer's Mac app is known to contain it
        self.assertEqual(self.v(MAC, {'apps': {}})['fix'], 'Needs the Mac app update')
        self.fake.mac_tag = 'v-new'
        S._timed.clear()
        self.assertEqual(self.v(MAC, {'apps': {}})['fix'], 'Needs the Mac app update')   # released, but this viewer's Mac app is unknown
        self.assertEqual(self.v(MAC, {'apps': {}, 'mac': 'old'})['state'], 'no')
        self.assertEqual(self.v(MAC, {'apps': {}, 'mac': '-new'})['state'], 'no')      # mac-mvp--new is behind: not in your Mac app
        real = S.contains
        try:
            S.contains = lambda tok, repo, sha, b: True if b == 'mac-mvp-0.8.0' else False if b == 'mac-mvp-0.7.0' else None
            self.assertEqual(self.v(MAC, {'apps': {}, 'mac': '0.8.0'})['state'], 'yes')      # release tags are mac-mvp-<version>
            self.assertEqual(self.v(MAC, {'apps': {}, 'mac': '0.7.0'})['fix'], 'Needs the Mac app update')
        finally:
            S.contains = real

    def test_mac_pr_without_merge_commit_still_counts(self):
        # try-wizard#19: the GitHub App token sees try-wizard PRs with mergeCommit null; they must not vanish
        node = {'timelineItems': {'nodes': [
            {'source': {'__typename': 'PullRequest', 'number': 712, 'merged': True, 'mergeCommit': {'oid': A}, 'repository': {'nameWithOwner': UX}}},
            {'source': {'__typename': 'PullRequest', 'number': 78, 'merged': True, 'mergeCommit': None, 'repository': {'nameWithOwner': MAC}}}]}}
        ds, _ = S.delivered(node)
        self.assertEqual([(d['repo'], d['sha']) for d in ds], [(UX, A), (MAC, '')])
        v = S.verdict('t', ds, 0, {'release': '0.3.2', 'channel': 'latest', 'apps': {}})
        self.assertEqual((v['state'], v['fix']), ('no', 'Needs the Mac app update'))

    def test_mixed_item_takes_the_blocking_fix(self):
        box = {'release': '0.3.2', 'channel': 'latest', 'apps': {}}
        v = S.verdict('t', [{'repo': UX, 'number': 1, 'sha': A}, {'repo': MAC, 'number': 2, 'sha': A}], 0, box)
        self.assertEqual((v['state'], v['fix']), ('no', 'Needs the Mac app update'))
        self.assertEqual([p['state'] for p in v['parts']], ['yes', 'no'])

    def test_docs_only_and_open_pr(self):
        self.assertEqual(self.v('humanitylabs-org/wizard-os', {'apps': {}})['state'], 'unknown')
        v = self.v(None, {'apps': {}}, open_prs=1)
        self.assertEqual((v['state'], v['fix']), ('no', 'Not released yet'))

    def test_compare_cached_for_good(self):
        box = {'release': '0.3.2', 'channel': 'latest', 'apps': {}}
        self.v(UX, box)
        n = len(self.fake.calls)
        self.v(UX, box)
        self.assertEqual(len(self.fake.calls), n)

    def test_on_box_route_sanitizes(self):
        real = S.account_for
        S.account_for = lambda person=None, agent=False: ('owner', {'token': 'tok', 'login': 'x'})
        try:
            out = S.on_box(None, {'box': {'release': '0.3.2; rm', 'channel': 'evil', 'apps': {'Bad Id': '1', 'messenger': '1.1'}},
                                  'items': [{'id': 'a#1', 'delivers': [{'repo': UX, 'number': 1, 'sha': A}, {'repo': 'x', 'sha': 'zz'}]}, 'junk']})
        finally:
            S.account_for = real
        self.assertEqual(out['box'], {'release': None, 'channel': None, 'apps': {'messenger': '1.1'}, 'mac': None})
        self.assertEqual(list(out['items']), ['a#1'])
        self.assertEqual(out['items']['a#1']['state'], 'unknown')   # no release: can't tell


class Delivered(unittest.TestCase):
    def test_merged_prs_from_timeline(self):
        node = {'timelineItems': {'nodes': [
            {'source': {'__typename': 'PullRequest', 'number': 136, 'merged': True, 'mergeCommit': {'oid': A.upper()}, 'repository': {'nameWithOwner': MSG}, 'url': 'u'}},
            {'source': {'__typename': 'PullRequest', 'number': 136, 'merged': True, 'mergeCommit': {'oid': A}, 'repository': {'nameWithOwner': MSG}, 'url': 'u'}},
            {'source': {'__typename': 'PullRequest', 'number': 140, 'merged': False, 'state': 'OPEN', 'repository': {'nameWithOwner': MSG}}},
            {'source': {'__typename': 'Issue', 'number': 9}},
            {'subject': {'__typename': 'PullRequest', 'number': 7, 'merged': True, 'mergeCommit': {'oid': NEW}, 'repository': {'nameWithOwner': UX}}},
        ]}}
        ds, n = S.delivered(node)
        self.assertEqual([(d['repo'], d['number'], d['sha']) for d in ds], [(MSG, 136, A), (UX, 7, NEW)])
        self.assertEqual(n, 1)


class Steps(unittest.TestCase):
    def test_human_test_block(self):
        body = 'AI review: pass — Oscar\n\nThe slice is sound.\n\nHuman test: open `Settings`, pick **Bug**, and check the five fields.\n\nNext slice: more.'
        self.assertEqual(S.test_steps([('a', body)]), 'open Settings, pick Bug, and check the five fields.')

    def test_inline_forms_and_newest_pass(self):
        old = 'AI review: pass — X\nHuman: old steps.'
        new = 'AI review: pass — Y\nChecked: fine. For the person checking: Settings › Drafts at top › On, then follow the hand-over.'
        self.assertEqual(S.test_steps([('a', old), ('b', 'unrelated'), ('c', new)]), 'Settings › Drafts at top › On, then follow the hand-over.')

    def test_numbered_and_none(self):
        body = 'AI review: pass\n\nHuman test (needs a Mac):\n1. Build it.\n2. Run WIZARD_TRAIN_HOTFIX_LANE.'
        self.assertEqual(S.test_steps([('a', body)]), 'Build it. Run WIZARD_TRAIN_HOTFIX_LANE.')
        self.assertEqual(S.test_steps([('a', 'AI review: pass\nAll good.')]), '')
        self.assertEqual(S.test_steps([('a', 'AI review: fail\nHuman test: x')]), '')


class Rules(unittest.TestCase):
    def test_card_wording(self):
        self.assertEqual(S.human_rule('bug', 'mistermizel', [], 'mistermizel'), (True, ''))   # 0.18: the filer tests
        self.assertEqual(S.human_rule('bug', 'mistermizel', [], 'jdefleur'), (False, 'Only Miguel tests this: they filed it.'))
        ok, rule = S.human_rule('goal', 'jdefleur', ['JanMesaric'], 'mistermizel')
        self.assertFalse(ok)
        self.assertTrue(rule.endswith('review this goal.'), rule)


if __name__ == '__main__':
    unittest.main()
