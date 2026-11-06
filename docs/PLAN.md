# Wizard OS Tracker (app id `board`): plan and Reuse

One sentence: humans manage Wizard development as GitHub Goals and Bugs in one screen; agents report bugs, comment and write PRs.

Visible actions (0.4): sign in with your own GitHub token (one centred card); a small centred Goals | Bugs switch; one small Everyone ▾ picker (authors present in the view); Works / Doesn't work (with a short note) on others' Ready to test cards; tap any row or card title to read the issue in a sheet (Back, Esc, × or tap outside closes it; cmd/ctrl-click still opens GitHub). Each view: status groups Ready to test (`ready-to-test`) → Building (`building`) → Queued (every other open one), each with a count, and a tiny totals line under the switch (queued · building · to test · closed this week). No header, identity line, New, repo filter or refresh button. `/api/new` stays for back-compat but the view never calls it.

Data (0.4): `GET /api/split?view=goals|bugs` pages through GitHub search (Bugs: light rows 100 per page plus one heavy search for the `ready-to-test` ones; Goals: 40 per page with linked-issue progress) up to 300 items, and asks for "closed in the last 7 days" in the same first call. It returns `groups` {test, building, queued}, `counts`, `closed_week` {count, since, authors}, `total`, `shown`, `more`, and the 0.3 `test`/`doing` keys for older views. `GET /api/detail?repo=&number=` reads the issue and its comments from REST with `Accept: application/vnd.github.html+json` and returns GitHub's `body_html` through a whitelist cleaner (`_Clean`); the view parses that inertly with DOMParser and strips anything off-list again before inserting it. Images are not loaded (CSP `img-src 'self'`, and user-attachments need auth): they show as "Image ↗" links.

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