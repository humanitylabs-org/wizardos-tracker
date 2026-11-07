# Wizard OS Tracker (app id `board`): plan and Reuse

One sentence: humans manage Wizard development as GitHub Goals and Bugs in one screen; agents report bugs, comment and write PRs.

Visible actions (0.6): sign in with your own GitHub token; Goals | Bugs switch; the Wizard OS Builder switch (mock-up, `GET/POST /api/builder`, `data/private/builder.json`, default Paused); the workflow row of three hand-off steps 1 Open (count queued) → 2 Build (building) → 3 Review (ready-to-test), then Done (closed, all time), each with a role line and a tap-for-who sheet, with "Doesn't work → back to Build" (return arrow) and "Works → the opener closes it" under it; five bottleneck stats (third is "Waiting for review"); Everyone ▾ and All repos ▾ (multi-select sheet, per-view localStorage `board.repos.goals|bugs`); Works / Doesn't work on Waiting for review cards opened by someone else (cards you or your own agent opened say "Someone else reviews this"); tap any row to read the issue in a sheet with "Opened by X · reviewed by anyone else on the team". Rows are NOT links (`tapTarget()`), because the native Wizard app sends any tap on an external href to the browser; only Open on GitHub in the sheet links out. The 0.5 policy strip is gone.

Policy (0.6): `POLICY_DEFAULT` in server.py = `team` [{name, logins, agents:[{login,name}]}], `builder` {name, logins}, `open` {goals: ['James'], bugs: 'team'}; `DATA_DIR/policy.json` overrides any key. `person_of(login)` maps a login (person or agent, case-insensitive) to a team name; `same_person()` drives `mine` in `/api/split` and the 403 in `/api/test/works|fails`. `/api/split` returns `steps` (built by `steps_for(view)`) and each card's `opener`; `/api/detail` returns `opener`. `GET /api/policy` returns team, builder, open, steps {goals, bugs}, me {login, person} and the 0.5 keys (goals.authors, builds.builders, lines).

Data (0.5): `GET /api/split` uses the same paged search, now also asking `assignees(first: 10)` and `comments { totalCount }` (so rows carry owners, comment count and `desc` without extra calls). Bottleneck stats (`GET /api/stats?view=&author=&repos=`): one search over every issue of that kind (open and closed, 100 a page, up to 600) with `timelineItems(LABELED_EVENT, UNLABELED_EVENT, CLOSED_EVENT, REOPENED_EVENT)`, reduced per item to wait/build/tries/kicks/waiting_for and cached 5 minutes per account and view. `/api/split` includes them when cached, else `stats: {pending: true}` and the view calls `/api/stats` right after (bugs history takes ~8 s cold). The view filters items by author and repos and averages itself, so the pipeline, stats and lists always agree.

Why 0.6: Miguel found the 0.5 policy strip unclear; he wanted the workflow itself shown as three steps, a hot potato passed between people and the builder, merged with the stage counts into one row, with exactly who may do each step and the "not the opener" review rule enforced. He will use this screen to explain the workflow to the team.
Why 0.5: Miguel wanted the goal rows readable at a glance (description, owners, comments), James's workflow stages named Queued → Building → Waiting for human with where work waits, the who-may-do-what policy, a builder on/off switch to wire later, and a repo filter beside Everyone.

Why 0.3: Miguel rejected 0.2 (Issues tab and repo filter pointless, Goals tab off to the side, no New button wanted, no logged-in line). He asked for "just goals and then bugs", each with things to test.
Why 0.4: Miguel liked 0.3 and the flat Bugs list but wanted to read issues without leaving the app, see real status (building vs queued) with counts, filter by who wrote it, and never lose items past 80.

Reuse:
- Back in app: REUSE `WizardApp` (back.register at root; the detail sheet pushes onto WizardApp.back via wizard-sheet.js)
- The one pop-up: REUSE `WzSheet` (web/wizard-sheet.js; the detail sheet, a right side panel at ≥900 px)
- Skin, tokens and mode: REUSE `WizardApp.theme.get` (kit --wz-* roles; no app colours or theme storage)
- App kit rows, sections, sheet, pill, meter, chips, connector card: REUSE `WizardApp` (web/kit/wizard-ui.css pinned snapshot)
- Protect unsaved work from updates: REUSE `WizardApp.update.hold` (the Doesn't work note)
- Finishing-action confirmation: REUSE `WizardApp` (shell.toast, in-app status fallback)

Checked against wizard-ux `docs/COMPONENTS.md` at b1334120 with `tools/reuse-check-app.mjs` (no problems).

App domain, not shell capabilities: the per-person GitHub token sign-in (0600 on the box, connector pattern from APP-DESIGN-RULES rule 5) and the GitHub REST/GraphQL client. List text is plain text via `textContent`; the detail shows GitHub's own rendered HTML, cleaned twice (server whitelist, then view DOMParser whitelist), because apps are offered no markdown renderer. Not used: agent chat, share, capture, upload, transcription, reading place.

Visual: no new drawn element. The switch is a two-button segmented control on kit roles (`--fill`, `--accent`); goal progress is a 4 px bar on `--fill-2`/`--accent`; cards and rows use `--line`, `--fill`, `--wz-surface-raised`, so every skin and light/dark mode applies. One 680 px centred column; on phones the full-width 48 px Works / Doesn't work buttons sit within thumb reach.