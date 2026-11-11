# WizardOS Tracker — notes for agents

**This repo is outside the pipeline (Miguel, 11 Nov 2026).** A broken pipeline can't fix itself, so the Tracker and the builder pipeline (`humanitylabs-org/wizardos-builder`) are the one exception to "everything goes through the builder". The builder never picks up issues here and the board doesn't show them. **Miguel or Jan, or their agents, change the Tracker directly:** branch, change, open a PR, merge it yourself. No AI review, no Human review, no Tracker step, no feature switch required. Issues in this repo are a to-do list for Miguel and Jan; a Report or request that names the Tracker lands here.

Don't file Tracker changes through the Tracker's Report or request and wait: that's the pipeline. Make the change.

## Ship a change

1. `git fetch` and branch from `origin/main` (another agent may be shipping a version too; if your number is taken, rebase and bump again).
2. Make the change. Server: `app/server.py` (+ `app/report.py`, `app/feedback_inbox.py`). Page: `web/`.
3. Bump the version everywhere (a test checks they agree): `VERSION` in `app/server.py`, `version:` in `wizard.md` and `skill/SKILL.md`, `version` in `runtipi/config.json` and `openapi.json` (`info.version`), and in `web/app.js` both `PAGE_VERSION` and the literal in `WizardApp.ready({ name: 'wizardos-tracker', version: '…' })`. Leave `tipi_version` alone (the store index bumps it). Add a line to the changelog in `wizard.md`.
4. Test: `python3 -m unittest discover -s tests` and `node --check web/app.js`.
5. Package: `wam package-inline "$PWD"` (absolute path; `.` fails), then `python3 tools/compress_compose.py`. Commit the updated `runtipi/docker-compose.yml`.
6. Open a PR. Its body needs a Reuse block, for Tracker-only UI just:

   ```
   Reuse:
   - App kit: REUSE `WizardApp`
   ```

   Merge it once CI is green. The Publish workflow puts the new version in the App Store.
7. On each box the Tracker shows **A new version of the Tracker is ready · Update**; one tap updates it. An agent can run `wam app-updates --apply wizardos-tracker`.

Style: no hex/rgba colour literals (use `color-mix` with kit vars like `--wz-warning`), rem not px for font sizes.
