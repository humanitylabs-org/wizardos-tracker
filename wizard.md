---
wizard: 0.2
id: board
name: Wizard OS Tracker
type: service
category: app
version: 0.7.0
summary: Wizard OS Goals and Bugs on GitHub, grouped by status, with the full issue on tap.
tags: [developer, productivity]
license: GPL-3.0-only
source: https://github.com/humanitylabs-org/wizard-board
runtime:
  kind: runtipi
  config: runtipi/config.json
  compose: runtipi/docker-compose.yml
api:
  port: 8799
  path: /api
  spec: openapi.json
mcp:
  path: /mcp
  port: 8799
  transport: streamable-http
skill: skill/SKILL.md
view:
  path: /
  port: 8799
  source:
    path: web
    build: python3 app/build_view.py
    dist: web
provides: [project-board]
system: false
uses: []
needs: []
health: /healthz
---

# Wizard OS Tracker

Display name "Wizard OS Tracker"; the app id stays `board` and the path `/board/`, so installs and sign-ins carry over.

Humans manage the work; agents write the PRs. Board shows two kinds of GitHub issue across one organisation (default `humanitylabs-org`):

- **Goal** (label `goal`): a big outcome with a short done-list (a markdown task list). Only humans open and close goals.
- **Bug** (label `bug`): small and specific. Anyone may report one; agents start only after a human accepts it (label `accepted`).

Each person connects their own GitHub account with a personal access token. The token is kept on the box only (file mode 0600), validated with `GET /user`, never returned to the view or MCP. Board sees exactly what that token can see. GitHub is the only backend: the app keeps no copy of issues, only a 60-second read cache.

In the app (0.7, minimalist: numbers and arrows first), top to bottom: a small **Goals | Bugs** switch with a small **Builder** switch on the same row (Paused / Running; a mock-up stored at `GET/POST /api/builder`, default Paused; trying to turn it on shows a small anchored note "Not connected to the builder yet" and it stays Paused; if it was Running it can be paused); the **assembly line**, one row of four bins **Queued → Building → Review → Done**, each a big number with one word, clear arrows between, and a small curved return arrow (no text) from Review back to Building (Doesn't work). Queued = open, not `building` or `ready-to-test`; Building = label `building`; Review = label `ready-to-test`; Done = closed, all time. Tapping a bin shows a small anchored popover: who does that step and one sentence (Queued: Goals = James, Bugs = anyone on the team; Building: Wizard OS Builder `wizardosbuilder`; Review: the team, not whoever opened it, a person and their own agent counting as one; Done: the opener closes it once it works). The team roster and who opens each view are defaults in code, overridable in `DATA_DIR/policy.json` (keys `team`, `builder`, `open`), served at `GET /api/policy`. Then one small row of bottleneck stats from GitHub label history (Queued for = opened → first `building`; Build time = first `building` → first `ready-to-test`; In review = average and longest age of items now `ready-to-test`; Tries = times labelled `ready-to-test`; Kicked back = `ready-to-test` removed without a close or `approved`), cached 5 minutes, — until there is data. Then two identical filter pills, **Everyone ▾** and **All repos ▾**: each opens a compact checklist right under it (multi-select with counts and an All reset row; tap outside, Esc or the pill again closes it), remembered per view on the device (`board.who.goals|bugs`, `board.repos.goals|bugs`). Bins, stats and lists honour both filters. Lists are grouped **Review** (cards: what to check from the builder, repo · opener · comments, Works / Doesn't work: comment, drop `ready-to-test`, on Works add `approved`, never close; hidden on items you or your own agent opened, and refused by the server), **Building** and **Queued**. Goal rows: title, comment count, description (2–3 lines), progress bar, owners · repo. Bug rows: title, one line of description, repo · opener · comment count. Titles are shown as written. Every row and Review card has a small **Try it** switch on the right (mock-up): greyed except in Review, where flipping it records the choice per signed-in person (`GET/POST /api/try {repo, number, on}`, `DATA_DIR/private/try.json`) and shows "Mock-up: this will switch the change on in your Wizard once it runs a build with it"; a greyed one says "Can be switched on once it's in Review". The switch never opens the row. Rows are not links: tapping opens the issue in an in-app sheet (body and comments as GitHub renders them, cleaned on the box), and only its Open on GitHub link leaves the app. No create, refresh or account UI. Agents use the MCP tools (`board_list`, `board_get`, `board_report_bug`, `board_comment`, `builder_status`, `try_status`; `board_add_goal`, `board_accept_bug`, `board_close`, `board_reopen`, `builder_set`, `try_set` only on a human's explicit request, and never to close or reopen goals).

Built from the hello-wizard template (stdlib Python, vanilla view, shared Wizard kit and `/wizard-os-home/core/app-client.js`).
