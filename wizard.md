---
wizard: 0.2
id: board
name: Wizard OS Tracker
type: service
category: app
version: 0.3.0
summary: Wizard OS Goals and Bugs on GitHub, with what is ready to test on top.
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

In the app (0.3): one small **Goals | Bugs** switch. Each view has **Ready to test** on top (open issues of that kind labelled `ready-to-test` that someone else wrote: one line on what to check from the builder `wizardosbuilder`, else the description's first line; a Settings › Tweaks hint; Works / Doesn't work, which comment, drop `ready-to-test` and on Works add `approved`, never close) and **In progress** below (Goals: title, thin progress bar, owner; Bugs: title and repo). Goals are open issues labelled `goal`; Bugs are open issues without `goal` (labelled `bug` or unlabelled). Tapping a row opens it on GitHub. No create, filter, refresh or account UI: new goals and bugs are filed by the agent in chat; the view refreshes on focus and every minute. Agents use the MCP tools (`board_list`, `board_get`, `board_report_bug`, `board_comment`; `board_add_goal`, `board_accept_bug`, `board_close`, `board_reopen` only on a human's explicit request, and never to close or reopen goals).

Built from the hello-wizard template (stdlib Python, vanilla view, shared Wizard kit and `/wizard-os-home/core/app-client.js`).
