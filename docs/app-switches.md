# App switches (`wizard.app-switches/1`)

The full contract lives in wizard-os `docs/APP_SWITCHES.md`. This page is the Tracker's side.

Tracker 0.23 (Miguel, 10 Nov 2026): **one catalog**. The box's App Manager (`_feature-switches`) lists the WizardOS core
switches AND the switches of every installed app that declares `switches:` in its `wizard.md` (ids `<app>:<switch>`,
`kind: "app"`, each with the `issues` it delivers). Flipping an app switch goes to the App Manager, which calls the app
server-side with the owner's authority (the platform owner proof, or the box's own Tailscale Serve), so it works the
same in every browser and never depends on an app cookie in the viewer's browser.

## The Tracker
- Every Human review item whose issue (`owner/repo#N`) a catalog switch names gets a real **Try it** toggle on its card,
  in the detail and in Settings › Try changes (core or app alike). An item's own `Switch: <author>/<id>` line still wins.
- An app switch is never locked by the box channel (For everyone / For testers); a core one is.
- Fallback (a box whose App Manager predates 0.23's catalog, or an app the App Manager can't reach): the 0.21 browser
  path, `/<app-id>/api/switches` then `/<app-id>/api/view/switches`, same origin; else the place in words + **Open <app>**.

## The app (summary)
- `wizard.md`: `switches: {contract: wizard.app-switches/1, path: /api/switches}` (or `/api/view/switches`).
- `GET <path>` → `{"contract": "wizard.app-switches/1", "switches": [{"id", "name", "description", "on", "default",
  "issues": ["owner/repo#N"]}]}`; `POST <path>` with JSON `{"id", "on"}`, header `X-Wizard-Switch: 1` and the box's
  `Origin` → the same listing. Owner only; state on the box; off by default.
