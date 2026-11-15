"""Tracker 0.35.0 (Miguel, 15 Nov): a Human review item that waits on someone else first (a Mac build, a phone
release, a question to another person) stays off the filer's Needs you count, is listed under `waiting`, and its card
says 'Waiting on James: Mac build'.
Run: python3 -m unittest discover -s tests"""
import unittest
from pathlib import Path

from test_013 import S
from test_034 import Fixture
from test_0182 import node

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
CSS = (ROOT / 'web/styles.css').read_text()
B = 'wizardos-builder'
TW = 'humanitylabs-org/try-wizard'
UX = 'humanitylabs-org/wizard-ux'

MAC_HANDOVER = ("What changed: the Mac app can now show the PWA/phone app icon.\n\nMerged: https://github.com/humanitylabs-org/try-wizard/pull/97\n\n"
                "Switch: try-wizard/PWAIcon (Mac user default, off by default: `defaults write org.humanitylabs.wizard.mvp PWAIcon -bool YES`)\n\n"
                "This only reaches testers in the next Mac app build, which a person cuts on a Mac.")
PHONE_HANDOVER = ("What changed: behind a new off switch, the WizardOS Android app can clear LINE's own tray notification.\n\nMerged:\n"
                  "- https://github.com/humanitylabs-org/wizard-ux/pull/1458 : Android listener (app 0.10.46, versionCode 110)\n"
                  "- Released in Messenger 0.2.0-unified.16.50\n\nWhat to check:\n"
                  "1. Update Messenger to 0.2.0-unified.16.50 and the WizardOS Android app to 0.10.46.")
PHONE_REVIEW = ("AI review: pass — Oscar (agent of Miguel)\n\nNote: the phone part works only once WizardOS Android 0.10.46 is "
                "published (latest published is 0.10.18), so the test waits on that release.")
NORMAL_HANDOVER = "What changed: the desktop chat sidebar follows Settings.\n\nSwitch: wizard/chat-sidebar\n\nWhat to check:\n1. Open Chats."


def comments(*rows):
    return {'totalCount': len(rows), 'nodes': [{'author': {'login': w}, 'body': b, 'createdAt': '2026-11-15T03:00:00Z'} for w, b in rows]}


def mac_pr(sha='a' * 40):
    return {'nodes': [{'source': {'__typename': 'PullRequest', 'repository': {'nameWithOwner': TW}, 'number': 97, 'merged': True,
                                  'mergeCommit': {'oid': sha}, 'url': 'https://github.com/humanitylabs-org/try-wizard/pull/97'}}]}


ITEMS = [
    node(86, ['feature', 'james-approved', 'ready-to-test'], author='oscarhenrycollins', repo=TW, title='Mac icon',
         comments=comments((B, MAC_HANDOVER), ('mistermizel', 'AI review: pass — Oscar (agent of Miguel)')), timelineItems=mac_pr()),
    node(1276, ['feature', 'james-approved', 'ready-to-test'], author='oscarhenrycollins', title='Android clears notifications',
         comments=comments((B, PHONE_HANDOVER), ('mistermizel', PHONE_REVIEW))),
    node(1443, ['feature', 'james-approved', 'ready-to-test'], author='oscarhenrycollins', title='Chat sidebar',
         comments=comments((B, NORMAL_HANDOVER))),
    node(1500, ['feature', 'james-approved', 'ready-to-test'], author='mistermizel', title='Needs Jan',
         comments=comments((B, NORMAL_HANDOVER), ('mistermizel', '@JanMesaric can you turn on the notes box knob for me first?'))),
]


class Fixture035(Fixture):
    def setUp(self):
        super().setUp()
        self.saved35 = (S._view_search, S.phone_latest, S.mac_built, S._view_nodes)
        S._view_nodes = lambda token, q, **kw: ([], 0)   # no goals: only the Human review fixtures

        def search(token, view, q, **kw):
            return (ITEMS, len(ITEMS)) if view == 'core' else ([], 0)
        S._view_search = search
        S.phone_latest = lambda token: '0.10.18'
        S.mac_built = lambda token, delivers: False

    def tearDown(self):
        S._view_search, S.phone_latest, S.mac_built, S._view_nodes = self.saved35
        super().tearDown()


class NeedsYouWaiting(Fixture035):
    def test_mac_and_phone_items_leave_the_count(self):
        d = S.needs_you('m')
        ids = [i['id'] for i in d['items']]
        self.assertEqual(ids, [UX + '#1443'])                      # the normal item still counts
        self.assertEqual(d['count'], 1)
        w = {i['id']: i for i in d['waiting']}
        self.assertEqual(w[TW + '#86'], {'id': TW + '#86', 'title': 'Mac icon', 'who': 'James', 'what': 'Mac build',
                                         'link': '/wizardos-tracker/#item/humanitylabs-org/try-wizard/86'})
        self.assertEqual((w[UX + '#1276']['who'], w[UX + '#1276']['what']), ('James', 'Android app 0.10.46'))
        self.assertEqual(w[UX + '#1500']['who'], 'Jan')            # an @-mention of another person with a question
        self.assertIn('notes box knob', w[UX + '#1500']['what'])

    def test_card_stores_waiting_on(self):
        d = S.board_split('m', {'view': 'core'})
        cards = {c['id']: c for c in d['groups']['test']}
        self.assertEqual(cards[TW + '#86']['waiting_on'], {'who': ['James'], 'kind': 'person', 'stuck': False,
                                                           'what': 'Mac build', 'why': 'mac'})
        self.assertEqual(cards[UX + '#1276']['waiting_on']['why'], 'phone')
        self.assertNotIn('what', cards[UX + '#1443']['waiting_on'])
        self.assertEqual(cards[UX + '#1443']['waiting_on']['who'], ['Miguel'])

    def test_released_unblocks(self):
        S.phone_latest = lambda token: '0.10.46'
        S.mac_built = lambda token, delivers: True
        d = S.needs_you('m', {'refresh': True})
        self.assertEqual({i['id'] for i in d['items']}, {TW + '#86', UX + '#1276', UX + '#1443'})
        self.assertEqual([i['id'] for i in d['waiting']], [UX + '#1500'])

    def test_james_own_mac_item_still_counts_for_him(self):
        items = [dict(ITEMS[0], author={'login': 'jdefleur'})]
        S._view_search = lambda token, view, q, **kw: (items, 1) if view == 'core' else ([], 0)
        d = S.needs_you('j')
        self.assertEqual([i['id'] for i in d['items']], [TW + '#86'])
        self.assertEqual(d['waiting'], [])


class Rule(unittest.TestCase):
    def base(self):
        return S.policy_base()

    def test_phone_version_parsing(self):
        self.assertEqual(S.phone_needed([PHONE_HANDOVER]), '0.10.46')
        self.assertEqual(S.phone_needed(['Update Messenger to 0.2.0-unified.16.50.']), None)
        self.assertEqual(S.phone_needed(['Android Companion 1.0.2 is out']), None)
        self.assertEqual(S.phone_needed(['needs phone app v0.10.50 or newer']), '0.10.50')

    def test_mac_text_in_other_repo_and_release_check(self):
        rows = [(B, 'Merged. This reaches testers only in the next Mac app build.')]
        self.assertEqual(S.other_wait(UX, [], rows, 'mistermizel', self.base())['what'], 'Mac build')
        # a Mac-repo change already in a published Mac build waits on nobody
        self.assertIsNone(S.other_wait(TW, [{'repo': TW, 'sha': 'a' * 40}], [(B, MAC_HANDOVER)], 'mistermizel', self.base(),
                                       mac=lambda: True))

    def test_mention_rules(self):
        b = self.base()
        # a mention of the filer themself, or a mention without a question, is not a wait
        self.assertIsNone(S.other_wait(UX, [], [(B, NORMAL_HANDOVER), ('jdefleur', '@mistermizel does it work for you?')], 'mistermizel', b))
        self.assertIsNone(S.other_wait(UX, [], [(B, NORMAL_HANDOVER), ('mistermizel', 'Thanks @jdefleur, looks good.')], 'mistermizel', b))
        got = S.other_wait(UX, [], [(B, NORMAL_HANDOVER), ('mistermizel', 'This waits on @jdefleur.')], 'mistermizel', b)
        self.assertEqual(got['who'], ['James'])
        # an older question that the newest comment moved past does not count
        self.assertIsNone(S.other_wait(UX, [], [('mistermizel', '@jdefleur can you sign it?'), (B, NORMAL_HANDOVER)], 'mistermizel', b))

    def test_release_people_policy(self):
        from test_013 import reset
        reset({'release_people': {'mac': ['Jan']}})
        try:
            got = S.other_wait(TW, [], [(B, MAC_HANDOVER)], 'mistermizel', S.policy_base())
            self.assertEqual(got['who'], ['Jan'])
            self.assertEqual(S.policy_base()['release_people']['phone'], ['James'])
        finally:
            reset()

    def test_pure_split(self):
        cards = {'test': [{'id': 'a#1', 'turn': True, 'waiting_on': {'who': ['James'], 'what': 'Mac build'}},
                          {'id': 'a#2', 'turn': True, 'waiting_on': {'who': ['Miguel']}}]}
        items, waiting = S.needs_you_split([{'me_person': 'Miguel', 'groups': cards}])
        self.assertEqual([i['id'] for i in items], ['a#2'])
        self.assertEqual(waiting[0]['who'], 'James')
        self.assertEqual([i['id'] for i in S.needs_you_items([{'me_person': 'Miguel', 'groups': cards}])], ['a#2'])


class Page(unittest.TestCase):
    def test_card_line(self):
        self.assertIn("if (g === 'test' && wo.what)", JS)
        self.assertIn("make('span', 'bd-waiton-x', ': ' + wo.what)", JS)
        self.assertIn('bd-waiton-other', JS)

    def test_versions_agree(self):
        v = S.VERSION
        self.assertEqual(v, '0.35.0')
        self.assertIn(f"PAGE_VERSION = '{v}'", JS)
        self.assertIn(f"version: '{v}' }})", JS)
        self.assertIn(f'**{v}**', (ROOT / 'wizard.md').read_text())


if __name__ == '__main__':
    unittest.main()
