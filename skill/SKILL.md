---
name: board
description: Use when working with Wizard development Goals and Bugs on GitHub.
version: 0.2.0
author: Humanity Labs, Hermes Agent
license: GPL-3.0-only
platforms: [linux, macos]
metadata:
  hermes:
    tags: [github, goals, bugs, project-board]
    related_skills: []
---
# Board: Goals and Bugs

Humans manage the work; agents write the PRs. There are exactly two kinds of GitHub issue:

- **Goal** (label `goal`): a big outcome with a done-list (markdown task list). **Only humans open and close goals.**
- **Bug** (label `bug`): small and specific. **Anyone may report.** Agents start work only after a human accepts it (label `accepted`).

People see three tabs in the app: **Goals**, **To test** (issues labelled `ready-to-test`; a person taps Works, which comments, removes `ready-to-test` and adds `approved`, or Doesn't work, which comments what failed and removes `ready-to-test`) and **Issues** (bugs and unlabelled issues). When you finish work, label the issue `ready-to-test` and comment one short paragraph saying what to check; an `approved` label means a human tested it.

## Rules for agents
1. Read freely: `board_list` (filters `repo`, `type` all|goal|bug, `state` open|closed, `accepted` any|yes|no) and `board_get` (`issue` "owner/repo#123", or `repo` + `number`).
2. You may `board_report_bug` (repo, title, body: what happens, what should happen, how to see it) and `board_comment`.
3. Never open, close or reopen a goal on your own. `board_add_goal` exists only for when a human explicitly asks you to type a goal in for them: pass their exact words as `owner_request`. Closing/reopening goals is refused for agents; ask the human to do it in Board.
4. Never accept a bug on your own. `board_accept_bug` requires the human's words in `owner_request`.
5. Work only on bugs with `accepted: true`, or on an open goal's unchecked done-list items. Link your PR to the issue (`Fixes owner/repo#123` for bugs; mention the goal for goal work) so Board counts it.
6. Confirm every write by reading the result (the tools return the issue as GitHub now has it). On an error, report the exact message; never claim it was saved.

Board acts with the GitHub account of the first person who connected on this box; it sees only what that token can see. If no account is connected, ask the owner to open Board and connect GitHub. Never ask for the token in chat.
