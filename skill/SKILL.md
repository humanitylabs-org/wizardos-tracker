---
name: wizardos-tracker
description: Use when working with Wizard development Goals, Features and Bugs on GitHub.
version: 0.21.3
author: Humanity Labs, Hermes Agent
license: GPL-3.0-only
platforms: [linux, macos]
metadata:
  hermes:
    tags: [github, goals, bugs, project-board]
    related_skills: []
---
# WizardOS Tracker (app id `wizardos-tracker`): Goals, Features, Bugs

Repo: `humanitylabs-org/wizardos-tracker` (was `oscarhenrycollins/wizard-board`, then `oscarhenrycollins/wizardos-tracker`). Agent tools: `mcp__wizard__wizardos_tracker__<tool>`.

## Tabs and kinds (0.18)
Goals (own header button; its number = all open goals) | Core features | App features | Bugs (0.19.1: items of `wizardos-tracker` and `wizardos-builder` never show on the board; Oscar fixes those directly). Human review, Shipping and Done cards name the release that has the change ('In For testers 0.3.x', 'In For everyone 0.3.y', 'Shipped in <App> <version>'); an item with both `bug` and `feature` labels counts as a bug. Labels stay `goal` / `feature` / `bug`; **core vs app comes from the repo**: core = `wizard-os`, `wizard-ux`, `wizard-app-manager`, `wizard-agent-service`, `try-wizard` (Mac app) — the list is `core_repos` in `/api/policy` (DATA_DIR/policy.json overrides). Every other repo (wizard-messenger, app repos) is an app.
- **Goal**: human-led, never built by the builder. Owners (assignees) post status; only James closes it.
- **Feature**: an idea to try. File with `board_report_feature`. When the owner asks to try an idea, file a feature, not a bug.
- **Bug**: something that should clearly work. File with `board_report_bug` (what happens, what should happen, how to see it).
- **Report or request** (0.20): when the owner just says what's broken or what they'd like, `report_or_request {kind: bug|feature, about: home|mac|updates|agent|<app repo>|unsure, text}` files it like the app's form (picks the repo, fills version/device) and returns where it landed.

Anyone on the allowlist files: Miguel/Oscar (`mistermizel`, `oscarhenrycollins`), James/Archimedes (`jdefleur`, `defleur-agents`), DeFleur agents, Jan (`JanMesaric`), Robert/Nebula (`hacalastudio`). A person and their own agent count as one person. Roster: `GET /api/policy`.

## Flows (agreed with James, 9 Nov)
- **Bugs** (0.20, Miguel: shipping never waits on humans): Queued → Building → **Shipped** (merged switched on, in For testers within minutes; AI check by the filer's agent) → **Human check** (the filer's quick sanity check, any time after Shipped; never holds up shipping) → **Checked** (said Works, or 7 days with no Doesn't work: 'Checked (no problems in 7 days)'). Cards show release and check apart: 'Shipped in For testers 0.3.150 · Human check pending' / 'Shipped in For everyone 0.3.152 · Checked by Miguel'. Doesn't work at any point (also after it closed) reopens it to Building. Promotion to For everyone never waits on a bug's human check. Hotfix: the same, plus the front of the queue.
- **App features**: Queued → Building → AI review → Human review by the filer (with its switch) → Shipping → Done. No James step.
- **Core features**: Queued → **Waiting for approval** (0.18.2, wizard-os#423: **James or Miguel** approves — policy `core_approvers`; the builder must not start until the issue has label `james-approved`; Approve / Decline, Decline closes it as not planned; others see 'Only James or Miguel can approve core features.') → Building → AI review → Human review by the filer → **Show-and-tell** (label `show-and-tell`; James approves: no switch → closed, with a switch → label `switch-default`, the builder removes the switch / turns it on for everyone, merges and closes) → Shipping → Done.
- **Kick-backs** (AI review fail, Human Doesn't work) go back to Building and are counted in stats. Stats also show **Still not working**: items where a human said Doesn't work more than once (`summary.still_not_working`; `board_flow` returns `still_not_working` per item, the detail shows a badge).

Labels: `building`, `ai-review`, `ready-to-test` (Human review), `show-and-tell`, `james-approved`, `approved`, `switch-default`.

Queued cards say why they wait: 'Next for the builder', or 'Oscar builds this one' (wizardos-tracker and wizardos-builder: the builder skips them).

## Shipping and Done (the board stays truthful)
Works on a bug or app feature (or James's show-and-tell without a switch) adds `approved` and **closes the issue at once** (the builder never sees it as work again). The Tracker then shows it as **Shipping** until every merged PR that delivered it is in a release that reaches everyone, with the wait it is in: `Waiting for release` (merged, not in a For testers release), `In For testers <version>`, `Waiting for Mac app build` (try-wizard), `Waiting for <App> release` (Store). **Done** = in the stable (For everyone) WizardOS release / a published Mac release / the app's latest Store release; the card says `Shipped in <version>` (kept once seen). Specs and tools (`wizard-os`, `wizard-app-index`) ship on merge.

## Goals: status
Each goal card shows a light — green On track / yellow At risk / red Blocked — with a one-or-two-sentence human status, who wrote it and when; older than 7 days shows "Status is old". A status is a **GitHub comment on the goal whose first line is `Status: green|yellow|red`**, then the text; the comment thread is the history. Post with `goal_status_set {repo, number, color, text}` (only for the goal's owners or James; as an agent, only when your person is one of them and asked you); read with `goal_status_get`. Never post a status the owner didn't give you.
Linked bugs/features: the builder adds one line `Goal: owner/repo#N` to an item's body or hand-over comment **only on a clear match**; the goal card counts linked items by stage.

Oscar's box runs a 30-minute cron doing its own AI reviews: re-read the item (`board_get`) right before reviewing so you don't double-review.

## Same screen for everyone
Every person sees the exact same UI: the same tabs, lists, items, buttons and switches. Nothing is hidden or added per person; anything a viewer can't do is greyed out with the reason in place ("Only James closes a goal.", "Only Miguel tests this: they filed it.", "Only Jan or James review this goal."). Human review lists your own items too. Keep it that way in every change.

## Switches
Name the switch in the hand-over with one `Switch:` line. A shell tweak (`Switch: <author>/<id>`) becomes a real toggle on the card, in the detail and in Settings › Try changes. Anything else is shown as the exact place to flip it: a Mac user default (write the full `defaults write …` command in the hand-over; the Tracker shows it with Copy), a setting inside an app (`Switch: Settings › <place>`, with an Open <app> button), or a box knob for whoever runs the box.

## Your turn first (0.18.2)
The default list sort is **Your turn first**: what the viewer can act on now (their Human review, approvals for James or Miguel, show-and-tell for James, goals they own with no status or an old one) sits on top under a small 'Your turn' divider, then everything else oldest first. Oldest, Newest, Most discussed and Recently active stay in the Sort menu.

## Updates
The Update manager and Try changes live only in the Tracker's **Settings** (WizardOS and every app, installed vs latest, Update / Update all). Cards show Update or the switch just in time, in their one action area.

## Rules for agents
- Read freely: `board_list` (`repo`, `type` all|goal|bug — features come with `all`, `state` open|closed), `board_get` (`issue` "owner/repo#123" or `repo` + `number`), `board_flow` (time per stage, kick-backs), `builder_status`, `try_status`.
- Write: `board_report_bug`, `board_report_feature`, `board_comment`, `ai_review_pass` / `ai_review_fail`. Write a clear first paragraph (rows show it, cut at `---`) and assign the owner on GitHub. Link PRs with `Fixes owner/repo#123`.
- Goals: never open, close or reopen on your own. `board_add_goal` only when a human asked, with their exact words as `owner_request`.
- `board_close` / `board_reopen`: only for the opener's side; goals are always refused for agents (only James closes a goal).
- Builder: never pick up a goal; never start a core feature without `james-approved`; after `switch-default` remove the switch and close it once merged.
- `builder_set`, `targets_set` (view goals|features|bugs (core/apps use features), step queued|building|ai|review|done, seconds or '4h'), `try_set`: only when a human asked, with their words as `owner_request`.
- Confirm every write from the returned issue; on error report the exact message, never claim it saved.
- Stats are label-driven (counted since `since` in `/api/policy`): label promptly and honestly.

## Pitfalls
- Tools act as the GitHub account first connected on this box. None connected → ask the owner to open WizardOS Tracker and sign in. Never ask for a token or secret in chat or put one in the repo.
- The human UI lets in only `humanitylabs-org` members with their own account; agent/builder accounts are refused. If someone is refused, they need org membership or must sign in as themselves; never sign in for them with an agent token.
- Signing out the account the agent uses also stops the agent's tools.
- A token that can't read org membership isn't "bad": recreate it with Resource owner humanitylabs-org. `reason: token_dead` = revoked/expired; sign in again.
