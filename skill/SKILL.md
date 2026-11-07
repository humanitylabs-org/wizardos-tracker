---
name: board
description: Use when working with Wizard development Goals and Bugs on GitHub.
version: 0.10.1
author: Humanity Labs, Hermes Agent
license: GPL-3.0-only
platforms: [linux, macos]
metadata:
  hermes:
    tags: [github, goals, bugs, project-board]
    related_skills: []
---
# Wizard OS Tracker (app id `board`): Goals and Bugs

Humans manage the work; agents write the PRs. There are exactly two kinds of GitHub issue:

- **Goal** (label `goal`): a big outcome with a done-list (markdown task list). **Only humans open and close goals.**
- **Bug** (label `bug`): small and specific. **Anyone may report.** Agents start work only after a human accepts it (label `accepted`).

People see the app as **Wizard OS Tracker** (0.7): Goals | Bugs with a small Builder switch (Paused, mock-up), the assembly line **Queued → Building → Review → Done** as big numbers with arrows and a return arrow from Review to Building, per-step stats, Who and Repo chip filters plus a sort on Bugs (0.9; Goals has no filters), and a mock-up **Try it** switch on each item that only works in Review (`try_status`, `try_set` with the human's words; records the wish, nothing runs yet). **Open** (queued): Goals only by James (`jdefleur`, his agent `defleur-agents`); Bugs by anyone on the team. The opener also closes it once it works. **Build** = label `building`, only the Wizard OS Builder (`wizardosbuilder`). **Review** = label `ready-to-test`: anyone on the team except whoever opened it; a person and their own agent count as one person (team roster: Miguel = mistermizel + oscarhenrycollins; James = jdefleur + defleur-agents; Jan = JanMesaric; Robert = hacalastudio; see `GET /api/policy`). Works comments, removes `ready-to-test` and adds `approved` (then the opener closes it); Doesn't work comments what failed and removes `ready-to-test`, sending it back to Build (counted as a kick back). The app hides the buttons from the opener's side and the server refuses them. Rows show the body's first paragraph (cut at a `---` line) and the GitHub assignees as owners, so write a clear first paragraph and assign the owner. The app has no New button: when the owner asks in chat for a goal or bug, file it with these tools. When you start work on an issue, add the `building` label on GitHub; when you finish, swap it for `ready-to-test` and comment one short paragraph saying what to check (that paragraph is what testers see). An `approved` label means a human tested it. `builder_status` reads the builder switch; `builder_set` (running true/false) only when a human asked, with their words as `owner_request`. The switch is not wired to the builder yet.

**0.8 stats**: each bin shows its own average (Queued = opened → first `building`; Building = first `building` → `ready-to-test`; Review = each `ready-to-test` stint until close or kick-back; Done = opened → closed) with a tiny box-and-whisker, and the return arrow shows the kick-back rate and average kick-backs per kicked item. Labels drive all of it, so label honestly and promptly. `board_flow` (`issue` or `repo` + `number`) returns one item's own line: seconds in each stage, kick-backs, current stage.

**0.9 targets**: each bin shows its typical range (p25 · **median** · p75) on a thin bar with a target tick; the median is green within target, amber over. Defaults: Bugs Queued 1h, Building 4h, Review 1d, Done 2d; Goals Queued 1h, Building 3d, Review 3d, Done 14d. **0.10: targets are shared and editable** by anyone signed in (tap `target 1h ✎` under a bin; permissions later): `POST /api/targets {view, step, seconds}` or MCP `targets_set` (view goals|bugs, step queued|building|review|done, seconds or '4h'/'3d', plus the human's words as `owner_request`; only when a human asked). Stored in `DATA_DIR/policy.json` `targets`; `GET /api/targets` or `GET /api/policy` shows the current values. Goal owners show as name chips on the title line (GitHub assignees mapped to roster names), so assign the owner on GitHub. Bugs Who/Repo chips keep a stable order (unfiltered totals). Bugs default to oldest first, so label `building` promptly when you pick one up.

## Rules for agents
1. Read freely: `board_list` (filters `repo`, `type` all|goal|bug, `state` open|closed, `accepted` any|yes|no) and `board_get` (`issue` "owner/repo#123", or `repo` + `number`).
2. You may `board_report_bug` (repo, title, body: what happens, what should happen, how to see it) and `board_comment`.
3. Never open, close or reopen a goal on your own. `board_add_goal` exists only for when a human explicitly asks you to type a goal in for them: pass their exact words as `owner_request`. Closing/reopening goals is refused for agents; ask the human to do it on GitHub.
4. Never accept a bug on your own. `board_accept_bug` requires the human's words in `owner_request`.
5. Work only on bugs with `accepted: true`, or on an open goal's unchecked done-list items. Link your PR to the issue (`Fixes owner/repo#123` for bugs; mention the goal for goal work) so Board counts it.
6. Confirm every write by reading the result (the tools return the issue as GitHub now has it). On an error, report the exact message; never claim it was saved.

Board acts with the GitHub account of the first person who connected on this box; it sees only what that token can see. If no account is connected, ask the owner to open Wizard OS Tracker and connect GitHub. Never ask for the token in chat.
