# Board: plan and Reuse

One sentence: humans manage Wizard development as GitHub Goals and Bugs in one screen; agents report bugs, comment and write PRs.

Visible actions (0.2): sign in with your own GitHub token; three tabs (Goals, To test, Issues); + New (Issue, or Goal for GOAL_AUTHORS); Works / Doesn't work on To test cards; repo filter on Issues. Everything else (raw states, PR lists, done-list ticking, accept/close) lives on GitHub.

Reuse:
- Back in app: REUSE `WizardApp` (back.register at root; the sheet step through WzSheet.open and back.push)
- Skin, tokens and mode: REUSE `WizardApp.theme.get` (kit --wz-* roles; no app colours or theme storage)
- App kit rows, sections, sheet, pill, meter, chips, connector card: REUSE `WizardApp` (web/kit/wizard-ui.css pinned snapshot)
- Protect unsaved work from updates: REUSE `WizardApp.update.hold` (add goal, report bug and comment drafts)
- Finishing-action confirmation: REUSE `WizardApp` (shell.toast, in-app status fallback)

Checked against wizard-ux `docs/COMPONENTS.md` at b1334120 with `tools/reuse-check-app.mjs` (no problems).

App domain, not shell capabilities: the per-person GitHub token sign-in (0600 on the box, connector pattern from APP-DESIGN-RULES rule 5) and the GitHub REST/GraphQL client. Issue text is plain text via `textContent` (apps are offered no markdown renderer). Not used: agent chat, share, capture, upload, transcription, reading place.

Visual: no new drawn element; goal progress is the kit `.wz-meter`, statuses are `.wz-pill`. Tabs sit in a bottom bar on phones (thumb reach) and under the top bar on wide windows; the top bar (identity, refresh, + New) never wraps.
