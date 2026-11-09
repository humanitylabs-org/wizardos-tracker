---
name: wizardos-tracker
description: Use when working with Wizard development Goals, Features and Bugs on GitHub.
version: 0.17.1
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

## Kinds
- **Goal** (label `goal`): a long-running outcome with a done-list (`- [ ]` items in the body). James opens goals and only James closes them, once every done-list item is ticked.
- **Feature** (label `feature`): an idea to try, any size. File with `board_report_feature`. When the owner asks to try an idea, file a feature, not a bug.
- **Bug** (label `bug`): something that should clearly work. File with `board_report_bug` (what happens, what should happen, how to see it).

Anyone on the allowlist files, and the item is ready to work at once: Miguel/Oscar (`mistermizel`, `oscarhenrycollins`), James/Archimedes (`jdefleur`, `defleur-agents`), DeFleur agents, Jan (`JanMesaric`), Robert/Nebula (`hacalastudio`). A person and their own agent count as one person. Roster: `GET /api/policy`.

## One flow (bugs and features; goals differ at Human review)
1. **Filed** → ready to work.
2. **Building** (label `building`): only the builder `wizardosbuilder`. Features ship behind an off-by-default switch; bug fixes are live once released. Hand-over comment = one short "What to check" paragraph; if behind a shell switch, end it with `Switch: <author>/<id>` (tweak id from wizard-ux `wizard-os-home/tweaks/catalog.json`). No line = nothing to switch.
3. **AI review** (label `ai-review`): the opener's agent reviews (goals: the owners' agent; openers without an agent, e.g. Jan: any team agent). Check the build against the issue's scope (a goal slice: does it move the next done-list item forward?), then `ai_review_pass {issue, note}` or `ai_review_fail {issue, note}` (→ back to Building; say what is missing). In a pass note, write the person's steps after `Human test:` — the card shows that line as "To test".
4. **Human review** (label `ready-to-test`), bugs and features: someone other than the filer tests it. The card shows whether the change is on the tester's Wizard (a Mac app change says "Needs the Mac app update" unless the viewer's Mac app contains it), with an Update button. Works / Doesn't work live in the detail and ask first. **Works** → Done. **Doesn't work** → back to Building.
5. **Human review, goals**: no Works / Doesn't work. The goal's owners or James say **Keep going** (the builder takes the next done-list item: back to Building) or **Change direction** (a note is required: back to Building), and tick the done-list items the slice finished. Only James closes a goal: **Close goal** appears for everyone, enabled for James once every item is ticked (or with an explicit "close anyway"). Never answer for a person.

Oscar's box runs a 30-minute cron doing its own AI reviews: re-read the item (`board_get`) right before reviewing so you don't double-review.

## Same screen for everyone
Every person sees the exact same UI: the same tabs, lists, items, buttons and switches. Nothing is hidden or added per person; anything a viewer can't do is greyed out with the reason in place ("Only James closes a goal.", "You filed this, so someone else tests it.", "Only Jan or James review this goal."). Human review lists your own items too. Keep it that way in every change.

## Switches
Name the switch in the hand-over with one `Switch:` line. A shell tweak (`Switch: <author>/<id>`) becomes a real toggle on the card, in the detail and in Settings › Try changes. Anything else is shown as the exact place to flip it: a Mac user default (write the full `defaults write …` command in the hand-over; the Tracker shows it with Copy), a setting inside an app (`Switch: Settings › <place>`, with an Open <app> button), or a box knob for whoever runs the box.

## Wizards view
The Wizards tab shows this Wizard's WizardOS (version, channel, last failed update) and every app, installed vs latest, with Update and Update all through the box's own App Manager (the same exact-release update the Store runs). Only this Wizard is listed: no list of team Wizards exists yet.

## Rules for agents
- Read freely: `board_list` (`repo`, `type` all|goal|bug — features come with `all`, `state` open|closed), `board_get` (`issue` "owner/repo#123" or `repo` + `number`), `board_flow` (time per stage, kick-backs), `builder_status`, `try_status`.
- Write: `board_report_bug`, `board_report_feature`, `board_comment`, `ai_review_pass` / `ai_review_fail`. Write a clear first paragraph (rows show it, cut at `---`) and assign the owner on GitHub. Link PRs with `Fixes owner/repo#123`.
- Goals: never open, close or reopen on your own. `board_add_goal` only when a human asked, with their exact words as `owner_request`.
- `board_close` / `board_reopen`: only for the opener's side; goals are always refused for agents (only James closes a goal).
- `builder_set`, `targets_set` (view goals|features|bugs, step queued|building|ai|review|done, seconds or '4h'), `try_set`: only when a human asked, with their words as `owner_request`.
- Confirm every write from the returned issue; on error report the exact message, never claim it saved.
- Stats are label-driven (counted since `since` in `/api/policy`): label promptly and honestly.

## Pitfalls
- Tools act as the GitHub account first connected on this box. None connected → ask the owner to open WizardOS Tracker and sign in. Never ask for a token or secret in chat or put one in the repo.
- The human UI lets in only `humanitylabs-org` members with their own account; agent/builder accounts are refused. If someone is refused, they need org membership or must sign in as themselves; never sign in for them with an agent token.
- Signing out the account the agent uses also stops the agent's tools.
- A token that can't read org membership isn't "bad": recreate it with Resource owner humanitylabs-org. `reason: token_dead` = revoked/expired; sign in again.
