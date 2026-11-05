---
wizard: 0.2
id: board
name: Board
type: service
category: app
version: 0.1.0
summary: Project board for Wizard development on GitHub. Humans set Goals and accept Bugs; agents write the PRs.
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

# Board

Humans manage the work; agents write the PRs. Board shows two kinds of GitHub issue across one organisation (default `humanitylabs-org`):

- **Goal** (label `goal`): a big outcome with a short done-list (a markdown task list). Only humans open and close goals.
- **Bug** (label `bug`): small and specific. Anyone may report one; agents start only after a human accepts it (label `accepted`).

Each person connects their own GitHub account with a personal access token. The token is kept on the box only (file mode 0600), validated with `GET /user`, never returned to the view or MCP. Board sees exactly what that token can see. GitHub is the only backend: the app keeps no copy of issues, only a 60-second read cache.

In the app: add a goal, report a bug, accept a bug, close/reopen, tick done-list items and comment, without opening GitHub. Agents use the MCP tools (`board_list`, `board_get`, `board_report_bug`, `board_comment`; `board_add_goal`, `board_accept_bug`, `board_close`, `board_reopen` only on a human's explicit request, and never to close or reopen goals). The Boxes panel shows wizard-ux `main`; this box's own version is marked coming soon because it is outside the app's container.

Built from the hello-wizard template (stdlib Python, vanilla view, shared Wizard kit and `/wizard-os-home/core/app-client.js`).
