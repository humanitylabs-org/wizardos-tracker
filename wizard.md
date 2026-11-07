---
wizard: 0.2
id: board
name: Wizard OS Tracker
type: service
category: app
version: 0.10.0
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

In the app (0.7, minimalist: numbers and arrows first), top to bottom: a small **Goals | Bugs** switch with a small **Builder** switch on the same row (Paused / Running; a mock-up stored at `GET/POST /api/builder`, default Paused; trying to turn it on shows a small anchored note "Not connected to the builder yet" and it stays Paused; if it was Running it can be paused); the **assembly line**, one row of four bins **Queued → Building → Review → Done**, each a big number with one word, clear arrows between, and a small curved return arrow (no text) from Review back to Building (Doesn't work). Queued = open, not `building` or `ready-to-test`; Building = label `building`; Review = label `ready-to-test`; Done = closed, all time. Tapping a bin shows a small anchored popover: who does that step and one sentence (Queued: Goals = James, Bugs = anyone on the team; Building: Wizard OS Builder `wizardosbuilder`; Review: the team, not whoever opened it, a person and their own agent counting as one; Done: the opener closes it once it works). The team roster and who opens each view are defaults in code, overridable in `DATA_DIR/policy.json` (keys `team`, `builder`, `open`), served at `GET /api/policy`. Then one small row of bottleneck stats from GitHub label history (Queued for = opened → first `building`; Build time = first `building` → first `ready-to-test`; In review = average and longest age of items now `ready-to-test`; Tries = times labelled `ready-to-test`; Kicked back = `ready-to-test` removed without a close or `approved`), cached 5 minutes, — until there is data. Then (0.9, Bugs only) Who and Repo chip rows, remembered on the device (`board.who.bugs`, `board.repos.bugs`); bins, stats and lists honour both. Lists are grouped **Review** (cards: what to check from the builder, repo · opener · comments, Works / Doesn't work: comment, drop `ready-to-test`, on Works add `approved`, never close; hidden on items you or your own agent opened, and refused by the server), **Building** and **Queued**. Goal rows: title, comment count, description (2–3 lines), progress bar, owners · repo. Bug rows: title, one line of description, repo · opener · comment count. Titles are shown as written. Every row and Review card has a small **Try it** switch on the right (mock-up): greyed except in Review, where flipping it records the choice per signed-in person (`GET/POST /api/try {repo, number, on}`, `DATA_DIR/private/try.json`) and shows "Mock-up: this will switch the change on in your Wizard once it runs a build with it"; a greyed one says "Can be switched on once it's in Review". The switch never opens the row. Rows are not links: tapping opens the issue in an in-app sheet (body and comments as GitHub renders them, cleaned on the box), and only its Open on GitHub link leaves the app. No create, refresh or account UI. Agents use the MCP tools (`board_list`, `board_get`, `board_report_bug`, `board_comment`, `builder_status`, `try_status`; `board_add_goal`, `board_accept_bug`, `board_close`, `board_reopen`, `builder_set`, `try_set` only on a human's explicit request, and never to close or reopen goals).

0.8 (Miguel: keep it minimal, numbers and arrows first): the separate stats row is gone; each bin carries its own tiny stat under its word: Queued = avg time queued (opened → first `building`), Building = avg build time (first `building` → `ready-to-test`), Review = avg time in review (`ready-to-test` → close or kick-back, per stint), Done = avg total time (opened → closed), each with a tiny inline-SVG box-and-whisker (min, p25, median, p75, max, log scale, kit colours) from 3 data points, else just the avg or —. The return arrow Review → Building carries the kick-back label `rate · per-item` (e.g. `40% · 1.5×`: share of reviewed items kicked back at least once, average kick-backs among those); tapping it says so plus the average time from first kick-back to done. A small ⓘ next to each bin word shows the who/what popover; tapping the bin itself filters the list to that stage (toggle, the bin highlighted and the others dimmed, a `Stage ✕` pill clears it). The Done bin lists the most recently closed items of that view (`GET /api/done`, up to 50, newest first) in a Done group. Everyone/repo filters recompute the counts and stats (client-side over `/api/stats` items); the stage filter never changes the line. The issue sheet shows the same mini line for that one item from its label timeline (`GET /api/flow`, GitHub timeline API on demand, cached 2 minutes): time spent in Queued, Building and Review, the Done date, kick-backs on the return arrow, the current stage highlighted; with no stage history it says `Queued for Nd` with the rest dimmed. MCP `board_flow` returns the same for agents.

0.9 (Miguel: the box-and-whisker was hard to read): each bin's stat is now a readable mini range: three small numbers (p25 left, the median bold in the middle, p75 right; one point or two shows just the median), a thin bar from p25 to p75 with a dot at the median, and a short line `target 1h`. A thin accent tick on the bar marks the step's **target time**; the median turns green-ish (kit `--wz-success`, `--wz-success-light` in light) within target and amber (`--wz-warning`/`--wz-warning-light`) over. Targets default in code (Bugs: Queued 1h, Building 4h, Review 1d, Done 2d; Goals: Queued 1d, Building 3d, Review 3d, Done 14d), overridable in `DATA_DIR/policy.json` key `targets` ({"bugs": {"queued": "30m"}}, seconds or 30m/4h/3d/2w), served in `GET /api/policy` and per view in `GET /api/split` (`targets`). The ⓘ popover adds `Typical 2h–9d (middle half), median 5d.` and `Target: under 1h.` Filters are chip rows, **Bugs only** (Goals has no filters): a Who row (Everyone + each submitter with a count) and a Repo row (All repos + every non-archived org repo, including ones with 0 open bugs, dimmed; repo list from the GitHub API cached an hour, `repos` in `/api/split?view=bugs`), sorted by count then name, multi-select, each row's counts honouring the other row; the Repo row shows the top repos with bugs (10 on wide screens, 5 on phones) plus any picked and a `+N more` chip that expands the rest inline (`Less` collapses). A tiny segmented sort on Bugs: **Oldest** (default, long-waiting bugs first), Newest, Most discussed, Recently active, remembered on the device (`board.sort.bugs`); it hides while the Done stage is shown (newest closed first). Bug rows and Review cards show the bug's age (`12d`). Done rows have no Try it switch.

0.10 (Miguel's feedback on 0.9): **Bugs chips hold still.** Each chip row is sorted once by its unfiltered total (then name) and keeps that order whatever the other row selects; only the numbers change (a 0 dims, never disappears or moves). Numbers are tabular with a min-width sized for the unfiltered total, so changing counts never reflow the row, and `+N more`/`Less` keeps its state on selection (the collapsed Repo row's top few are chosen by unfiltered totals too). **Goal owners are as prominent as the title:** each GitHub assignee is a small accent name chip (initial + name) right after the title (Review goal cards too); "No owner" is a dashed chip. Logins map to people's names from the policy roster (jdefleur → James, mistermizel → Miguel, JanMesaric → Jan, hacalastudio → Robert, oscarhenrycollins → Oscar, defleur-agents → Archimedes; served as `names` in `/api/split` and `/api/policy`); bug rows keep repo · opener · age · comments in the meta line, with the same names. **Targets are editable and shared:** a thin row directly under the four bins holds, per bin column, `target 1h ✎` and ⓘ (nothing clickable sits inside a tappable bin any more; the bin keeps count, word, the three numbers and the bar). Tapping the target opens a small anchored editor with 15m, 1h, 4h, 1d, 3d, 1w, 2w and a custom field (`6h`, `2d`, `45m`); saving calls `POST /api/targets {view, step, seconds}`, stored in `DATA_DIR/policy.json` `targets` (who and when in `targets_changed`), the same for everyone. Any signed-in person may change targets for now (permissions later). Agents: MCP `targets_set` (view, step, seconds, owner_request). Default Queued target is now 1h for both Goals and Bugs (queue wait is builder pickup, the same for both); other defaults unchanged.

Built from the hello-wizard template (stdlib Python, vanilla view, shared Wizard kit and `/wizard-os-home/core/app-client.js`).
