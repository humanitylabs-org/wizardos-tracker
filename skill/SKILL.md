---
name: wizardos-tracker
description: Use when working with Wizard development Goals, Features and Bugs on GitHub.
version: 0.16.2
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
- **Goal** (label `goal`): big outcome with a done-list. Only humans open and close goals.
- **Feature** (label `feature`): an idea to try, any size. File with `board_report_feature`. When the owner asks to try an idea, file a feature, not a bug.
- **Bug** (label `bug`): something that should clearly work. File with `board_report_bug` (what happens, what should happen, how to see it).

Anyone on the allowlist files, and the item is ready to work at once: Miguel/Oscar (`mistermizel`, `oscarhenrycollins`), James/Archimedes (`jdefleur`, `defleur-agents`), DeFleur agents, Jan (`JanMesaric`), Robert/Nebula (`hacalastudio`). A person and their own agent count as one person. Roster: `GET /api/policy`.

## One flow (bugs and features; goals the same)
1. **Filed** → ready to work.
2. **Building** (label `building`): only the builder `wizardosbuilder`. Features ship behind an off-by-default switch; bug fixes are live once released. Hand-over comment = one short "What to check" paragraph; if behind a shell switch, end it with `Switch: <author>/<id>` (tweak id from wizard-ux `wizard-os-home/tweaks/catalog.json`). No line = nothing to switch.
3. **AI review** (label `ai-review`): the opener's agent reviews (goals: the owners' agent; openers without an agent, e.g. Jan: any team agent). Check the build against the issue's scope, then `ai_review_pass {issue, note}` or `ai_review_fail {issue, note}` (→ back to Building; say what is missing). In a pass note, write the person's steps after `Human test:` — the card shows that line as "To test".
4. **Human review** (label `ready-to-test`): someone other than the filer tests it (goals: the goal's owners or James). The card shows whether the change is on the tester's Wizard, and the fix if not. Works / Doesn't work each ask for a confirm. Never answer for a person.
5. **Works** → the opener closes it (Done). **Doesn't work** → back to Building.

Oscar's box runs a 30-minute cron doing its own AI reviews: re-read the item (`board_get`) right before reviewing so you don't double-review.

## Rules for agents
- Read freely: `board_list` (`repo`, `type` all|goal|bug — features come with `all`, `state` open|closed), `board_get` (`issue` "owner/repo#123" or `repo` + `number`), `board_flow` (time per stage, kick-backs), `builder_status`, `try_status`.
- Write: `board_report_bug`, `board_report_feature`, `board_comment`, `ai_review_pass` / `ai_review_fail`. Write a clear first paragraph (rows show it, cut at `---`) and assign the owner on GitHub. Link PRs with `Fixes owner/repo#123`.
- Goals: never open, close or reopen on your own. `board_add_goal` only when a human asked, with their exact words as `owner_request`.
- `board_close` / `board_reopen`: only for the opener's side; goals are always refused for agents.
- `builder_set`, `targets_set` (view goals|features|bugs, step queued|building|ai|review|done, seconds or '4h'), `try_set`: only when a human asked, with their words as `owner_request`.
- Confirm every write from the returned issue; on error report the exact message, never claim it saved.
- Stats are label-driven (counted since `since` in `/api/policy`): label promptly and honestly.

## Pitfalls
- Tools act as the GitHub account first connected on this box. None connected → ask the owner to open WizardOS Tracker and sign in. Never ask for a token or secret in chat or put one in the repo.
- The human UI lets in only `humanitylabs-org` members with their own account; agent/builder accounts are refused. If someone is refused, they need org membership or must sign in as themselves; never sign in for them with an agent token.
- Signing out the account the agent uses also stops the agent's tools.
- A token that can't read org membership isn't "bad": recreate it with Resource owner humanitylabs-org. `reason: token_dead` = revoked/expired; sign in again.
