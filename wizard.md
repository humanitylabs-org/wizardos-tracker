---
wizard: 0.2
id: board
name: Wizard OS Tracker
type: service
category: app
version: 0.5.0
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

In the app (0.5), top to bottom: a small **Goals | Bugs** switch; a **Wizard OS Builder** on/off switch (Paused / Running; a mock-up stored on the box at `GET/POST /api/builder`, default Paused, which the builder host will poll later; flipping it says "Not connected to the builder yet") and the policy (Goals: written by jdefleur, defleur-agents · Bugs: anyone in the org, people + their agents · Builds: wizardosbuilder only; defaults in code, editable in `DATA_DIR/policy.json`, collapsed on phones); a pipeline of three stage chips with counts, **Queued → Building → Waiting for human**, plus **Done** (closed, all time, for that view); one calm row of bottleneck stats from GitHub label history (Wait before builder starts = opened → first `building`; Build time = first `building` → first `ready-to-test`; Waiting for human = average and longest age of items now `ready-to-test`; Tries per item = times labelled `ready-to-test`; Kicked back = `ready-to-test` removed without a close or `approved`, i.e. Doesn't work), cached 5 minutes and shown as — ("starts once the builder runs") until there is data; then **Everyone ▾** (who wrote it) and **All repos ▾** (pick one or several repos in a small sheet; remembered per view on the device). Pipeline, stats and lists all honour both filters. Lists are grouped **Waiting for human** (label `ready-to-test`; someone else's get what to check from the builder `wizardosbuilder`, Works / Doesn't work, which comment, drop `ready-to-test` and on Works add `approved`, never close; the human who did not file it tests), **Building** (label `building`) and **Queued** (every other open one). Each row: title, comment count on the right, the description (first paragraph of the body as plain text, cut at a `---` line, 2–3 lines), then `Owner: login` / `Owners: a, b` (GitHub assignees) and the repo, small. Goals are open issues labelled `goal`; Bugs are open issues without `goal` (PRs excluded). Rows are not links: tapping opens the issue in an in-app sheet (body and comments as GitHub renders them, cleaned on the box), and only its Open on GitHub link leaves the app. No create, refresh or account UI. Agents use the MCP tools (`board_list`, `board_get`, `board_report_bug`, `board_comment`, `builder_status`; `board_add_goal`, `board_accept_bug`, `board_close`, `board_reopen`, `builder_set` only on a human's explicit request, and never to close or reopen goals).

Built from the hello-wizard template (stdlib Python, vanilla view, shared Wizard kit and `/wizard-os-home/core/app-client.js`).
