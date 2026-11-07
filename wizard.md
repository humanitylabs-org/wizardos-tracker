---
wizard: 0.2
id: board
name: Wizard OS Tracker
type: service
category: app
version: 0.6.0
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

In the app (0.6), top to bottom: a small **Goals | Bugs** switch; a **Wizard OS Builder** on/off switch (Paused / Running; a mock-up stored on the box at `GET/POST /api/builder`, default Paused, which the builder host will poll later; flipping it says "Not connected to the builder yet"); the workflow as **three hand-off steps in one row**, the same layout in both views: **1 Open** (count = queued; who may open and close: Goals = James only, i.e. `jdefleur` + his agent `defleur-agents`; Bugs = anyone on the team, people + their own agents) → **2 Build** (count = label `building`; Wizard OS Builder `wizardosbuilder` only, writes the code until it is ready for review) → **3 Review** (count = label `ready-to-test`; anyone on the team except whoever opened it, a person and their own agent counting as one person), then a small **Done N** (closed, all time). Each step shows a short role line (James / Anyone on the team, Wizard OS Builder, Team, not the opener); tapping it opens a small sheet listing exactly who (logins grouped as person + agent) and one sentence of what the step means. Under the row: "Doesn't work → back to Build" (a return arrow from Review to Build) and "Works → the opener closes it". The team roster (Miguel: mistermizel + agent oscarhenrycollins (Oscar); James: jdefleur + agent defleur-agents (Archimedes); Jan: JanMesaric; Robert: hacalastudio; Builder: wizardosbuilder) and who opens each view are defaults in code, overridable in `DATA_DIR/policy.json` (keys `team`, `builder`, `open`) and served at `GET /api/policy`; one calm row of bottleneck stats from GitHub label history (Wait before builder starts = opened → first `building`; Build time = first `building` → first `ready-to-test`; Waiting for review = average and longest age of items now `ready-to-test`; Tries per item = times labelled `ready-to-test`; Kicked back = `ready-to-test` removed without a close or `approved`, i.e. Doesn't work), cached 5 minutes and shown as — ("starts once the builder runs") until there is data; then **Everyone ▾** (who wrote it) and **All repos ▾** (pick one or several repos in a small sheet; remembered per view on the device). Steps, stats and lists all honour both filters. Lists are grouped **Waiting for review** (label `ready-to-test`; each card shows what to check from the builder `wizardosbuilder` and who opened it; Works / Doesn't work comment, drop `ready-to-test` and on Works add `approved`, never close; on items you or your own agent opened the buttons are hidden and the card says "Someone else reviews this", and the server refuses it too), **Building** (label `building`) and **Queued** (every other open one). Each row: title, comment count on the right, the description (first paragraph of the body as plain text, cut at a `---` line, 2–3 lines), then `Owner: login` / `Owners: a, b` (GitHub assignees) and the repo, small. Goals are open issues labelled `goal`; Bugs are open issues without `goal` (PRs excluded). Rows are not links: tapping opens the issue in an in-app sheet (a line "Opened by James · reviewed by anyone else on the team", then body and comments as GitHub renders them, cleaned on the box), and only its Open on GitHub link leaves the app. No create, refresh or account UI. Agents use the MCP tools (`board_list`, `board_get`, `board_report_bug`, `board_comment`, `builder_status`; `board_add_goal`, `board_accept_bug`, `board_close`, `board_reopen`, `builder_set` only on a human's explicit request, and never to close or reopen goals).

Built from the hello-wizard template (stdlib Python, vanilla view, shared Wizard kit and `/wizard-os-home/core/app-client.js`).
