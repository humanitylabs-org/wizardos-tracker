# Wizard OS Tracker (app id `board`): plan and Reuse

One sentence: humans manage Wizard development as GitHub Goals and Bugs in one screen; agents report bugs, comment and write PRs.

Visible actions (0.3): sign in with your own GitHub token (one centred card, nothing else); a small centred Goals | Bugs switch; Works / Doesn't work (with a short note) on Ready to test cards; tap any row to open it on GitHub. Each view: Ready to test (only when non-empty; someone else's `ready-to-test` issues of that kind) above In progress (Goals: title, thin progress bar, owner; Bugs: title, repo as plain text). No header, identity line, New, repo filter or refresh button: the owner asks the agent in chat to file goals and bugs (MCP), and the view refreshes on focus and every 60 s. `/api/new` stays for back-compat but the view never calls it. Everything else (raw states, PR lists, done-list ticking, accept/close) lives on GitHub.

Why 0.3: Miguel rejected 0.2 (Issues tab and repo filter pointless, Goals tab off to the side, no New button wanted, no logged-in line). He asked for "just goals and then bugs", each with things to test.

Reuse:
- Back in app: REUSE `WizardApp` (back.register at root; no sheets in 0.3)
- Skin, tokens and mode: REUSE `WizardApp.theme.get` (kit --wz-* roles; no app colours or theme storage)
- App kit rows, sections, sheet, pill, meter, chips, connector card: REUSE `WizardApp` (web/kit/wizard-ui.css pinned snapshot)
- Protect unsaved work from updates: REUSE `WizardApp.update.hold` (the Doesn't work note)
- Finishing-action confirmation: REUSE `WizardApp` (shell.toast, in-app status fallback)

Checked against wizard-ux `docs/COMPONENTS.md` at b1334120 with `tools/reuse-check-app.mjs` (no problems).

App domain, not shell capabilities: the per-person GitHub token sign-in (0600 on the box, connector pattern from APP-DESIGN-RULES rule 5) and the GitHub REST/GraphQL client. Issue text is plain text via `textContent` (apps are offered no markdown renderer). Not used: agent chat, share, capture, upload, transcription, reading place.

Visual: no new drawn element. The switch is a two-button segmented control on kit roles (`--fill`, `--accent`); goal progress is a 4 px bar on `--fill-2`/`--accent`; cards and rows use `--line`, `--fill`, `--wz-surface-raised`, so every skin and light/dark mode applies. One 680 px centred column; on phones the full-width 48 px Works / Doesn't work buttons sit within thumb reach.